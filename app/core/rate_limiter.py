# =============================================================================
# PrivateForm - Rate Limiting
# =============================================================================
# In-memory rate limiting (without Redis).
# Sufficient for this application's expected volume.
# =============================================================================

# PrivateForm - Privacy-first medical forms
# Copyright (C) 2026 Juan Manuel SUÁREZ - Arrakis IT Services
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# See LICENSE file for full terms.

import time
from collections import defaultdict
from datetime import date as _date
from fastapi import Request
from app.core.settings import settings


class RateLimiter:
    """
    Generic IP-based rate limiter.
    Stores attempt timestamps in memory.
    Automatically cleans expired entries.
    """

    def __init__(self):
        # {ip: [timestamp1, timestamp2, ...]}
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def _clean_expired(self, ip: str, window_seconds: int) -> None:
        """Removes attempts outside the time window."""
        now = time.time()
        cutoff = now - window_seconds
        self._attempts[ip] = [t for t in self._attempts[ip] if t > cutoff]

    def is_allowed(self, ip: str, max_attempts: int, window_seconds: int) -> bool:
        """
        Checks if attempt is allowed according to limits.
        Returns True if allowed, False if exceeds limit.
        """
        self._clean_expired(ip, window_seconds)

        if len(self._attempts[ip]) >= max_attempts:
            return False

        # Register the attempt
        self._attempts[ip].append(time.time())
        return True

    def get_remaining(self, ip: str, max_attempts: int, window_seconds: int) -> int:
        """Returns how many attempts remain in current window."""
        self._clean_expired(ip, window_seconds)
        return max(0, max_attempts - len(self._attempts[ip]))


# --- Specific instances ---

# Patient form submissions: maximum 2 per hour per IP
patient_submission_limiter = RateLimiter()

# Password recovery requests: maximum 3 per hour per IP
password_reset_limiter = RateLimiter()

# Verification email resend: maximum 3 per day per IP
verification_resend_limiter = RateLimiter()

# Error alerts: maximum 10 per hour (global, not per IP)
alert_limiter = RateLimiter()

# Login attempts: per IP and per email (15-minute window)
login_ip_limiter = RateLimiter()
login_email_limiter = RateLimiter()
register_ip_limiter = RateLimiter()


def get_client_ip(request: Request) -> str:
    """
    Gets client's real IP set by nginx from the TCP connection ($remote_addr).
    X-Real-IP cannot be spoofed by the client — nginx overwrites it.
    Falls back to direct connection IP for local development (no proxy).
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


# --- Specific verification functions ---

def check_patient_submission(request: Request) -> bool:
    """Checks if patient can submit a form."""
    ip = get_client_ip(request)
    return patient_submission_limiter.is_allowed(
        ip,
        max_attempts=settings.PATIENT_SUBMISSIONS_PER_HOUR,
        window_seconds=3600  # 1 hour
    )


def check_password_reset(request: Request) -> bool:
    """Checks if password recovery can be requested."""
    ip = get_client_ip(request)
    return password_reset_limiter.is_allowed(
        ip,
        max_attempts=settings.PASSWORD_RESET_ATTEMPTS_PER_HOUR,
        window_seconds=3600  # 1 hour
    )


def check_verification_resend(request: Request) -> bool:
    """Checks if verification email can be resent."""
    ip = get_client_ip(request)
    return verification_resend_limiter.is_allowed(
        ip,
        max_attempts=settings.VERIFICATION_RESEND_PER_DAY,
        window_seconds=86400  # 24 hours
    )


def check_alert_limit() -> bool:
    """Checks if an error alert can be sent."""
    return alert_limiter.is_allowed(
        "global",  # Single key for all alerts
        max_attempts=settings.ALERT_MAX_PER_HOUR,
        window_seconds=3600
    )

def check_login(request: Request, email: str) -> bool:
    """
    Checks login rate limits by IP and by email.
    Both must pass — returns False if either limit is exceeded.
    """
    ip = get_client_ip(request)
    window = settings.LOGIN_WINDOW_MINUTES * 60

    ip_allowed = login_ip_limiter.is_allowed(
        ip,
        max_attempts=settings.LOGIN_ATTEMPTS_PER_IP,
        window_seconds=window,
    )
    email_allowed = login_email_limiter.is_allowed(
        email,
        max_attempts=settings.LOGIN_ATTEMPTS_PER_EMAIL,
        window_seconds=window,
    )
    return ip_allowed and email_allowed

class BrevoQuotaTracker:
    """
    Tracks daily Brevo email quota in memory.
    Resets automatically at midnight on the first operation of the new day.
    No external cron needed — reset is triggered lazily on each call.
    """
    _THRESHOLDS = [50, 80, 95]

    def __init__(self):
        self._count: int = 0
        self._day: _date = _date.today()
        self._alerts_sent: set[int] = set()

    def _check_reset(self) -> None:
        today = _date.today()
        if today != self._day:
            self._count = 0
            self._day = today
            self._alerts_sent = set()

    def increment(self) -> int:
        """Increments the counter and returns the new value."""
        self._check_reset()
        self._count += 1
        return self._count

    def get_count(self) -> int:
        self._check_reset()
        return self._count

    def is_blocked(self) -> bool:
        """Returns True when the counter is at or above 99% of the daily limit."""
        self._check_reset()
        return self._count >= int(settings.BREVO_DAILY_LIMIT * 0.99)

    def get_pending_threshold_alerts(self) -> list[int]:
        """Returns threshold percentages crossed but not yet notified."""
        self._check_reset()
        if settings.BREVO_DAILY_LIMIT == 0:
            return []
        pct = (self._count / settings.BREVO_DAILY_LIMIT) * 100
        return [t for t in self._THRESHOLDS if pct >= t and t not in self._alerts_sent]

    def mark_alert_sent(self, threshold: int) -> None:
        self._alerts_sent.add(threshold)


brevo_quota = BrevoQuotaTracker()


def check_register(request: Request) -> bool:
    """
    Checks registration rate limit by IP.
    Stricter than login — registration is a one-time action.
    """
    ip = get_client_ip(request)
    window = settings.REGISTER_WINDOW_MINUTES * 60
    return register_ip_limiter.is_allowed(
        ip,
        max_attempts=settings.REGISTER_ATTEMPTS_PER_IP,
        window_seconds=window,
    )
