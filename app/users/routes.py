# =============================================================================
# PrivateForm - Users / Profile Routes
# =============================================================================
# Doctor profile routes: view, edit personal data,
# change login password and PDF encryption password.
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

import pytz
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.settings import settings
from app.core.models import Doctor, MEDICAL_SPECIALTIES, AVAILABLE_COUNTRIES
from app.auth.utils import (
    get_current_doctor_id, hash_password, verify_password,
    is_password_valid, validate_password_strength,
    clear_auth_cookie,
)
from app.email.service import send_password_changed_email
from app.core.logging import get_logger

logger = get_logger("users.routes")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

LUX_TZ = pytz.timezone("Europe/Luxembourg")


# =============================================================================
# Helpers
# =============================================================================

def get_doctor(db: Session, doctor_id: str) -> Doctor | None:
    return db.query(Doctor).filter(Doctor.id == doctor_id).first()


def doctor_to_dict(doctor: Doctor) -> dict:
    """Serializes doctor data for template (without passwords)."""
    return {
        "id": doctor.id,
        "email": doctor.email,
        "last_name": doctor.last_name,
        "first_name": doctor.first_name,
        "specialty": doctor.specialty,
        "phone": doctor.phone or "",
        "country": doctor.country or "",
        "newsletter": doctor.newsletter,
        "created_at": doctor.created_at,
    }


# =============================================================================
# GET /doctor/profile — Profile page
# =============================================================================

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    doctor_id: str = Depends(get_current_doctor_id),
    db: Session = Depends(get_db),
):
    doctor = get_doctor(db, doctor_id)
    if not doctor:
        return RedirectResponse(url="/login")

    # Format registration date in Luxembourg timezone
    created_str = ""
    if doctor.created_at:
        created_lux = doctor.created_at.astimezone(LUX_TZ)
        created_str = created_lux.strftime("%d/%m/%Y à %H:%M (CET)")

    return templates.TemplateResponse(request, "forms/profile.html", {
        "doctor": doctor_to_dict(doctor),
        "created_at_formatted": created_str,
        "specialties": MEDICAL_SPECIALTIES,
        "countries": AVAILABLE_COUNTRIES,
    })


# =============================================================================
# POST /doctor/profile — Update profile data
# =============================================================================

@router.post("/profile/update", response_class=JSONResponse)
async def profile_update(
    request: Request,
    doctor_id: str = Depends(get_current_doctor_id),
    db: Session = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Données invalides."}, status_code=400)

    doctor = get_doctor(db, doctor_id)
    if not doctor:
        return JSONResponse({"success": False, "error": "Médecin non trouvé."}, status_code=404)

    # Editable fields
    last_name = (body.get("last_name") or "").strip()
    first_name = (body.get("first_name") or "").strip()
    specialty = (body.get("specialty") or "").strip()
    phone = (body.get("phone") or "").strip()
    country = (body.get("country") or "").strip()
    newsletter = bool(body.get("newsletter", False))

    # Basic validations
    if not last_name or not first_name:
        return JSONResponse({"success": False, "error": "Nom et prénom sont obligatoires."}, status_code=400)

    # Validate specialty
    valid_specs = [s for s in MEDICAL_SPECIALTIES]
    if specialty and specialty not in valid_specs:
        return JSONResponse({"success": False, "error": "Spécialité invalide."}, status_code=400)

    # Validate country
    valid_countries = [c[0] for c in AVAILABLE_COUNTRIES]
    if country and country not in valid_countries:
        return JSONResponse({"success": False, "error": "Pays invalide."}, status_code=400)

    # Apply changes
    doctor.last_name = last_name
    doctor.first_name = first_name
    doctor.specialty = specialty if specialty else None
    doctor.phone = phone if phone else None
    doctor.country = country if country else None
    doctor.newsletter = newsletter

    db.commit()
    logger.info(f"Profile updated for doctor {doctor_id}")

    return JSONResponse({"success": True, "message": "Profil mis à jour avec succès."})


# =============================================================================
# POST /doctor/profile/change-password — Change login password
# =============================================================================

@router.post("/profile/change-password", response_class=JSONResponse)
async def change_password(
    request: Request,
    doctor_id: str = Depends(get_current_doctor_id),
    db: Session = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Données invalides."}, status_code=400)

    doctor = get_doctor(db, doctor_id)
    if not doctor:
        return JSONResponse({"success": False, "error": "Médecin non trouvé."}, status_code=404)

    current_password = body.get("current_password", "")
    new_password = body.get("new_password", "")
    confirm_password = body.get("confirm_password", "")

    # Verify current password
    if not verify_password(current_password, doctor.password_hash):
        return JSONResponse({"success": False, "error": "Mot de passe actuel incorrect."}, status_code=400)

    # Verify match
    if new_password != confirm_password:
        return JSONResponse({"success": False, "error": "Les mots de passe ne correspondent pas."}, status_code=400)

    # Validate new password
    if not is_password_valid(new_password):
        return JSONResponse({"success": False, "error": "Le mot de passe doit contenir au moins 8 caractères, une lettre majuscule, une minuscule et un chiffre."}, status_code=400)

    # Apply
    doctor.password_hash = hash_password(new_password)
    db.commit()

    # Send confirmation email
    try:
        now_lux = datetime.now(LUX_TZ)
        await send_password_changed_email(doctor.email, now_lux.strftime("%d/%m/%Y à %H:%M (CET)"))
    except Exception as e:
        logger.warning(f"Error sending password change email: {e}")

    logger.info(f"Login password changed for doctor {doctor_id}")

    # Close current session (client must logout)
    return JSONResponse({"success": True, "message": "Mot de passe modifié. Vous allez être déconnecté.", "logout": True})


# =============================================================================
# POST /doctor/profile/change-pdf-password — Change PDF password
# =============================================================================

@router.post("/profile/change-pdf-password", response_class=JSONResponse)
async def change_pdf_password(
    request: Request,
    doctor_id: str = Depends(get_current_doctor_id),
    db: Session = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Données invalides."}, status_code=400)

    doctor = get_doctor(db, doctor_id)
    if not doctor:
        return JSONResponse({"success": False, "error": "Médecin non trouvé."}, status_code=404)

    new_pdf_password = body.get("new_pdf_password", "")
    confirm_pdf_password = body.get("confirm_pdf_password", "")

    if not new_pdf_password:
        return JSONResponse({"success": False, "error": "Le mot de passe PDF est obligatoire."}, status_code=400)

    if new_pdf_password != confirm_pdf_password:
        return JSONResponse({"success": False, "error": "Les mots de passe PDF ne correspondent pas."}, status_code=400)

    # Apply (stored in plain text as per spec)
    doctor.pdf_encryption_password = new_pdf_password
    db.commit()

    logger.info(f"PDF password changed for doctor {doctor_id}")

    return JSONResponse({"success": True, "message": "Mot de passe PDF mis à jour avec succès."})
