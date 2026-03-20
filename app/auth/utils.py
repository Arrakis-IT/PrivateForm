# =============================================================================
# PrivateForm - Auth Utilities
# =============================================================================
# Password hashing, JWT tokens, httpOnly cookies.
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

import re
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Request, HTTPException
from fastapi.responses import Response
from app.core.settings import settings
from app.auth.token_denylist import denylist

# --- Hashing context (bcrypt) ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pre-computed dummy hash to prevent user enumeration via timing attacks.
# verify_password() is always called, even when the email doesn't exist.
_DUMMY_HASH = pwd_context.hash("dummy-that-never-matches-any-real-password")

def get_dummy_hash() -> str:
    """Returns a pre-computed dummy hash for timing-safe login checks."""
    return _DUMMY_HASH

# RFC 5322 practical subset — rejects the most common malformed inputs
_EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
)

def is_valid_email(email: str) -> bool:
    """
    Validates email format using a practical regex.
    Does not perform DNS/MX lookup — format only.
    """
    return bool(_EMAIL_REGEX.match(email)) and len(email) <= 254


# =============================================================================
# Passwords
# =============================================================================

def hash_password(password: str) -> str:
    """Generates a bcrypt hash of the password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def validate_password_strength(password: str) -> dict[str, bool]:
    """
    Validates password requirements.
    Returns a dict with each requirement and whether it's met.
    """
    return {
        "min_length": len(password) >= 8,
        "has_uppercase": bool(re.search(r"[A-Z]", password)),
        "has_lowercase": bool(re.search(r"[a-z]", password)),
        "has_number": bool(re.search(r"[0-9]", password)),
    }


def is_password_valid(password: str) -> bool:
    """Returns True if password meets all requirements."""
    checks = validate_password_strength(password)
    return all(checks.values())


# =============================================================================
# JWT Tokens
# =============================================================================

def create_access_token(doctor_id: str) -> str:
    """
    Creates a JWT with the doctor's ID.
    Expires according to JWT_EXPIRATION_MINUTES (2 hours by default).
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": doctor_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """
    Decodes a JWT and returns the doctor_id.
    Returns None if token is invalid, expired, or has been revoked.
    """
    if denylist.is_denied(token):
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
    

def revoke_token(token: str) -> None:
    """
    Adds a token to the denylist using its real expiry from the payload.
    Called on logout to immediately invalidate the session.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        exp = float(payload.get("exp", 0))
        denylist.add(token, exp)
    except JWTError:
        pass  # Already invalid, nothing to revoke


# =============================================================================
# httpOnly Cookies
# =============================================================================

def set_auth_cookie(response: Response, token: str) -> None:
    """Sets authentication cookie (httpOnly, secure, samesite)."""
    response.set_cookie(
        key="privateform_token",
        value=token,
        httponly=True,
        secure=True,                          # HTTPS only
        samesite="lax",
        max_age=settings.JWT_EXPIRATION_MINUTES * 60,  # Same duration as JWT
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """Removes authentication cookie."""
    response.delete_cookie(
        key="privateform_token",
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def get_token_from_cookie(request: Request) -> str | None:
    """Extracts token from request cookie."""
    return request.cookies.get("privateform_token")


# =============================================================================
# Dependency: Get authenticated doctor
# =============================================================================

async def get_current_doctor_id(request: Request) -> str:
    """
    FastAPI dependency that extracts and validates token from cookie.
    Returns doctor_id if valid.
    Raises HTTP 401 if there's no token or it's invalid/expired.
    """
    token = get_token_from_cookie(request)
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")

    doctor_id = decode_access_token(token)
    if not doctor_id:
        raise HTTPException(status_code=401, detail="Session expirée")

    return doctor_id
