# =============================================================================
# PrivateForm - Admin Routes
# =============================================================================
# Internal dashboard: doctor/form metrics from DB + email stats from Brevo.
# Access protected by Nginx HTTP Basic Auth (/etc/nginx/.htpasswd).
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

from datetime import date, timedelta
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from app.core.database import SessionLocal
from app.core.models import Doctor, Form
from app.core.settings import settings
from app.core.logging import get_logger

logger = get_logger("admin.routes")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


async def _fetch_brevo_stats() -> dict:
    """
    Fetches aggregated email statistics from Brevo for the last 30 days.
    Returns a dict with daily sent counts and a 30-day total.
    """
    today = date.today()
    start_date = today - timedelta(days=29)

    headers = {
        "api-key": settings.BREVO_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.brevo.com/v3/smtp/statistics/aggregatedReport",
                headers=headers,
                params={
                    "startDate": start_date.isoformat(),
                    "endDate": today.isoformat(),
                },
            )
            response.raise_for_status()
            data = response.json()
            return {
                "total_sent": data.get("delivered", 0) + data.get("softBounces", 0) + data.get("hardBounces", 0),
                "delivered": data.get("delivered", 0),
                "bounces": data.get("softBounces", 0) + data.get("hardBounces", 0),
                "error": None,
            }
    except Exception as e:
        logger.exception(f"Error fetching Brevo stats: {e}")
        return {"total_sent": None, "delivered": None, "bounces": None, "error": str(e)}


async def _fetch_brevo_today_stats() -> dict:
    """
    Fetches aggregated email statistics from Brevo for today only.
    """
    today = date.today()
    headers = {
        "api-key": settings.BREVO_API_KEY,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.brevo.com/v3/smtp/statistics/aggregatedReport",
                headers=headers,
                params={
                    "startDate": today.isoformat(),
                    "endDate": today.isoformat(),
                },
            )
            response.raise_for_status()
            data = response.json()
            return {
                "total_sent": data.get("delivered", 0) + data.get("softBounces", 0) + data.get("hardBounces", 0),
                "delivered": data.get("delivered", 0),
                "bounces": data.get("softBounces", 0) + data.get("hardBounces", 0),
                "error": None,
            }
    except Exception as e:
        logger.exception(f"Error fetching Brevo today stats: {e!r}")
        return {"total_sent": None, "delivered": None, "bounces": None, "error": str(e)}


async def _fetch_brevo_daily_stats() -> list[dict]:
    """
    Fetches per-day email statistics from Brevo for the last 7 days.
    Returns a list of {date, requests} dicts sorted by date ascending.
    """
    today = date.today()
    start_date = today - timedelta(days=6)

    headers = {"api-key": settings.BREVO_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.brevo.com/v3/smtp/statistics/reports",
                headers=headers,
                params={
                    "startDate": start_date.isoformat(),
                    "endDate": today.isoformat(),
                },
            )
            response.raise_for_status()
            data = response.json()
            reports = data.get("reports", [])
            return [
                {
                    "date": r.get("date", ""),
                    "sent": r.get("delivered", 0) + r.get("softBounces", 0) + r.get("hardBounces", 0),
                }
                for r in sorted(reports, key=lambda x: x.get("date", ""), reverse=True)
            ]
    except Exception as e:
        logger.exception(f"Error fetching Brevo daily stats: {e!r}")
        return []


# =============================================================================
# GET /admin/metrics
# =============================================================================

@router.get("/admin/metrics", response_class=HTMLResponse)
async def admin_metrics(request: Request):
    db = SessionLocal()
    try:
        today = date.today()
        week_ago = today - timedelta(days=7)

        # --- Doctors ---
        total_doctors = db.query(func.count(Doctor.id)).filter(Doctor.is_verified == True).scalar() or 0

        new_doctors_week = db.query(func.count(Doctor.id)).filter(
            Doctor.is_verified == True,
            func.date(Doctor.created_at) >= week_ago,
        ).scalar() or 0

        # --- Forms ---
        total_active_forms = db.query(func.count(Form.id)).filter(
            Form.is_active == True,
            Form.is_example == False,
        ).scalar() or 0

        # --- Brevo ---
        brevo_today = await _fetch_brevo_today_stats()
        brevo_30d = await _fetch_brevo_stats()
        brevo_daily = await _fetch_brevo_daily_stats()

    finally:
        db.close()

    return templates.TemplateResponse(request, "admin/metrics.html", {
        "today": today.strftime("%d/%m/%Y"),
        "total_doctors": total_doctors,
        "new_doctors_week": new_doctors_week,
        "total_active_forms": total_active_forms,
        "brevo_today": brevo_today,
        "brevo_30d": brevo_30d,
        "brevo_daily": brevo_daily,
    })
