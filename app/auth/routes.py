# =============================================================================
# PrivateForm - Auth Routes
# =============================================================================
# Authentication routes: registration, login, logout, email verification,
# password recovery and change.
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

import secrets
from zoneinfo import ZoneInfo
from typing import Annotated
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.settings import settings
from app.core.models import Doctor, VerificationToken, PasswordResetToken, MEDICAL_SPECIALTIES, AVAILABLE_COUNTRIES
from app.auth.utils import (
    hash_password, verify_password, is_password_valid, validate_password_strength,
    create_access_token, set_auth_cookie, clear_auth_cookie,
    get_token_from_cookie, decode_access_token, revoke_token,is_valid_email,
    get_dummy_hash,
)
from app.auth.crypto import encrypt_pdf_password
from app.core.rate_limiter import check_password_reset, check_verification_resend, check_login, check_register, brevo_quota
from app.email.service import (
    send_verification_email, send_password_reset_email,
    send_password_changed_email,
)
from app.core.logging import get_logger, sanitize_log

logger = get_logger("auth.routes")

DOCTOR_HOME_URL = "/doctor/home"
DbSession = Annotated[Session, Depends(get_db)]
REGISTER_TEMPLATE = "auth/register.html"
VERIFY_PENDING_TEMPLATE = "auth/verify_pending.html"
VERIFY_RESULT_TEMPLATE = "auth/verify_result.html"
LOGIN_TEMPLATE = "auth/login.html"
FORGOT_PASSWORD_TEMPLATE = "auth/forgot_password.html"
RESET_PASSWORD_TEMPLATE = "auth/reset_password.html"
RESEND_VERIFICATION_TEMPLATE = "auth/resend_verification.html"

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

LUX_TZ = ZoneInfo("Europe/Luxembourg")


# =============================================================================
# Helpers
# =============================================================================

def generate_token() -> str:
    return secrets.token_urlsafe(32)


def get_doctor_by_email(db: Session, email: str) -> Doctor | None:
    return db.query(Doctor).filter(Doctor.email == email).first()


def get_doctor_by_id(db: Session, doctor_id: str) -> Doctor | None:
    return db.query(Doctor).filter(Doctor.id == doctor_id).first()


def build_url(path: str) -> str:
    protocol = "https" if settings.APP_DOMAIN != "localhost" else "http"
    return f"{protocol}://{settings.APP_DOMAIN}{path}"


# =============================================================================
# Landing Page
# =============================================================================

@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    token = get_token_from_cookie(request)
    if token and decode_access_token(token):
        return RedirectResponse(url=DOCTOR_HOME_URL)
    return templates.TemplateResponse(request, "base/landing.html", {})


# =============================================================================
# Register
# =============================================================================

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    token = get_token_from_cookie(request)
    if token and decode_access_token(token):
        return RedirectResponse(url=DOCTOR_HOME_URL)
    if brevo_quota.is_blocked():
        return templates.TemplateResponse(request, REGISTER_TEMPLATE, {
            "specialties": MEDICAL_SPECIALTIES,
            "countries": AVAILABLE_COUNTRIES,
            "errors": {"general": "Il n'est pas possible de créer un compte en ce moment. Veuillez réessayer dans quelques minutes."},
            "form_data": {},
            "password_checks": {"min_length": False, "has_uppercase": False, "has_lowercase": False, "has_number": False},
        }, status_code=503)
    return templates.TemplateResponse(request, REGISTER_TEMPLATE, {
        "specialties": MEDICAL_SPECIALTIES,
        "countries": AVAILABLE_COUNTRIES,
        "errors": {},
        "form_data": {},
        "password_checks": {"min_length": False, "has_uppercase": False, "has_lowercase": False, "has_number": False},
    })


def _parse_register_form(form_data) -> dict:
    return {
        "last_name": (form_data.get("last_name") or "").strip(),
        "first_name": (form_data.get("first_name") or "").strip(),
        "email": (form_data.get("email") or "").strip().lower(),
        "password": form_data.get("password") or "",
        "pdf_password": form_data.get("pdf_password") or "",
        "specialty": form_data.get("specialty") or "",
        "phone": (form_data.get("phone") or "").strip(),
        "country": form_data.get("country") or "",
        "newsletter": form_data.get("newsletter") == "on",
        "terms_accepted": form_data.get("terms_accepted") == "on",
    }


def _validate_register_fields(fd: dict) -> dict:
    errors = {}
    if not fd["last_name"] or len(fd["last_name"]) < 2:
        errors["last_name"] = "Veuillez indiquer votre nom (minimum 2 caractères)."
    if not fd["first_name"] or len(fd["first_name"]) < 2:
        errors["first_name"] = "Veuillez indiquer votre prénom (minimum 2 caractères)."
    if not fd["email"]:
        errors["email"] = "Veuillez indiquer votre adresse email."
    elif not is_valid_email(fd["email"]):
        errors["email"] = "Le format de votre adresse email est invalide."
    if not fd["password"]:
        errors["password"] = "Veuillez définir un mot de passe."
    elif not is_password_valid(fd["password"]):
        errors["password"] = "Le mot de passe ne respecte pas les critères de sécurité."
    if not fd["pdf_password"]:
        errors["pdf_password"] = "Veuillez définir un mot de passe de chiffrement."
    elif not is_password_valid(fd["pdf_password"]):
        errors["pdf_password"] = "Le mot de passe de chiffrement ne respecte pas les critères de sécurité."
    elif fd["pdf_password"] == fd["password"]:
        errors["pdf_password"] = "Le mot de passe PDF ne peut pas être identique au mot de passe de connexion."
    if fd["phone"] and not fd["phone"].startswith("+"):
        errors["phone"] = "Le format du téléphone doit inclure l'indicatif (ex: +352...)."
    if not fd["terms_accepted"]:
        errors["terms_accepted"] = "Vous devez accepter les CGU et la politique de confidentialité."
    return errors


def _register_error_response(request: Request, fd: dict, errors: dict, status_code: int = 400):
    return templates.TemplateResponse(request, REGISTER_TEMPLATE, {
        "specialties": MEDICAL_SPECIALTIES,
        "countries": AVAILABLE_COUNTRIES,
        "errors": errors,
        "form_data": {
            "last_name": fd["last_name"], "first_name": fd["first_name"], "email": fd["email"],
            "specialty": fd["specialty"], "phone": fd["phone"], "country": fd["country"],
            "newsletter": fd.get("newsletter", False),
        },
        "password_checks": validate_password_strength(fd["password"]),
    }, status_code=status_code)


@router.post("/register", response_class=HTMLResponse)
async def register_submit(request: Request, db: DbSession):
    fd = _parse_register_form(await request.form())

    if brevo_quota.is_blocked():
        return _register_error_response(request, fd, {"general": "Il n'est pas possible de créer un compte en ce moment. Veuillez réessayer dans quelques minutes."}, status_code=503)

    if not check_register(request):
        return _register_error_response(request, fd, {"general": "Trop de tentatives. Réessayez dans 1 heure."}, status_code=429)

    errors = _validate_register_fields(fd)
    if errors:
        logger.warning(f"Validation errors in registration: {sanitize_log(errors)}")
        return _register_error_response(request, fd, errors)

    if get_doctor_by_email(db, fd["email"]):
        return _register_error_response(request, fd, {"email": "Impossible de créer le compte. Veuillez vérifier vos informations."})

    # Create doctor
    doctor = Doctor(
        email=fd["email"],
        password_hash=hash_password(fd["password"]),
        pdf_encryption_password=encrypt_pdf_password(fd["pdf_password"]),
        last_name=fd["last_name"],
        first_name=fd["first_name"],
        specialty=fd["specialty"] if fd["specialty"] else None,
        phone=fd["phone"] if fd["phone"] else None,
        country=fd["country"] if fd["country"] else None,
        newsletter=fd["newsletter"],
        is_verified=False,
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)

    # Verification token
    token = generate_token()
    db.add(VerificationToken(
        doctor_id=doctor.id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    ))
    db.commit()

    # Send email
    verification_url = build_url(f"/verify-email?token={token}")
    await send_verification_email(
        to_email=doctor.email,
        doctor_name=f"{doctor.first_name} {doctor.last_name}",
        verification_url=verification_url,
    )

    logger.info(f"New doctor registered: doctor_id={doctor.id}")
    return RedirectResponse(url="/verify-pending", status_code=302)


# =============================================================================
# Pending verification
# =============================================================================

@router.get("/verify-pending", response_class=HTMLResponse)
async def verify_pending(request: Request):
    return templates.TemplateResponse(request, VERIFY_PENDING_TEMPLATE, {
        "resend_error": None, "resend_success": False,
    })


@router.get("/resend-verification", response_class=HTMLResponse)
async def resend_verification_page(request: Request):
    return templates.TemplateResponse(request, RESEND_VERIFICATION_TEMPLATE, {
        "resend_error": None, "resend_success": False,
    })


@router.post("/resend-verification", response_class=HTMLResponse)
async def resend_verification(request: Request, db: DbSession):
    form_data = await request.form()
    email = (form_data.get("email") or "").strip().lower()

    if brevo_quota.is_blocked():
        return templates.TemplateResponse(request, RESEND_VERIFICATION_TEMPLATE, {
            "resend_error": "Il n'est pas possible d'envoyer l'email en ce moment. Veuillez réessayer dans quelques minutes.",
            "resend_success": False,
        }, status_code=503)

    if not check_verification_resend(request):
        return templates.TemplateResponse(request, RESEND_VERIFICATION_TEMPLATE, {
            "resend_error": "Limite atteinte. Réessayez dans 24 heures.",
            "resend_success": False,
        })

    doctor = get_doctor_by_email(db, email)
    if not doctor or doctor.is_verified:
        return RedirectResponse(url=LOGIN_URL, status_code=302)

    token = generate_token()
    db.add(VerificationToken(
        doctor_id=doctor.id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    ))
    db.commit()

    verification_url = build_url(f"/verify-email?token={token}")
    await send_verification_email(
        to_email=doctor.email,
        doctor_name=f"{doctor.first_name} {doctor.last_name}",
        verification_url=verification_url,
    )

    return templates.TemplateResponse(request, RESEND_VERIFICATION_TEMPLATE, {
        "resend_error": None, "resend_success": True,
    })


# =============================================================================
# Email verification
# =============================================================================

@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email(request: Request, db: DbSession):
    token = request.query_params.get("token", "")

    if not token:
        return templates.TemplateResponse(request, VERIFY_RESULT_TEMPLATE, {
            "success": False, "context": "verification", "expired": False, "email": "",
        })

    vt = db.query(VerificationToken).filter(
        VerificationToken.token == token, VerificationToken.is_used == False
    ).first()

    if not vt:
        return templates.TemplateResponse(request, VERIFY_RESULT_TEMPLATE, {
            "success": False, "context": "verification", "expired": False, "email": "",
        })

    if vt.expires_at < datetime.now(timezone.utc):
        doctor = get_doctor_by_id(db, vt.doctor_id)
        return templates.TemplateResponse(request, VERIFY_RESULT_TEMPLATE, {
            "success": False, "context": "verification", "expired": True,
            "email": doctor.email if doctor else "",
        })

    vt.is_used = True
    doctor = get_doctor_by_id(db, vt.doctor_id)
    if doctor:
        doctor.is_verified = True
    db.commit()

    logger.info(f"Email verified: doctor_id={doctor.id if doctor else 'unknown'}")
    return templates.TemplateResponse(request, VERIFY_RESULT_TEMPLATE, {
        "success": True, "context": "verification", "expired": False, "email": "",
    })


# =============================================================================
# Login
# =============================================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    token = get_token_from_cookie(request)
    if token and decode_access_token(token):
        return RedirectResponse(url=DOCTOR_HOME_URL)
    return templates.TemplateResponse(request, LOGIN_TEMPLATE, {"errors": {}, "form_data": {}})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, db: DbSession):
    form_data = await request.form()
    email = (form_data.get("email") or "").strip().lower()
    password = form_data.get("password") or ""

    errors = {}
    if not email:
        errors["email"] = "Veuillez indiquer votre adresse email."
    elif not is_valid_email(email):
        errors["email"] = "Le format de votre adresse email est invalide."

    if not password:
        errors["password"] = "Veuillez indiquer votre mot de passe."
    if errors:
        return templates.TemplateResponse(request, LOGIN_TEMPLATE, {
            "errors": errors, "form_data": {"email": email},
        }, status_code=400)
    
    # Rate limiting: must be checked before hitting the database
    if not check_login(request, email):
        return templates.TemplateResponse(request, LOGIN_TEMPLATE, {
            "errors": {"general": "Trop de tentatives. Réessayez dans 15 minutes."},
            "form_data": {"email": email},
        }, status_code=429)

    doctor = get_doctor_by_email(db, email)

    # Always run bcrypt regardless of whether the email exists.
    # This prevents user enumeration via response timing differences.
    hash_to_check = doctor.password_hash if doctor else get_dummy_hash()
    password_ok = verify_password(password, hash_to_check)

    if not doctor or not password_ok:
        return templates.TemplateResponse(request, LOGIN_TEMPLATE, {
            "errors": {"general": "Email ou mot de passe incorrect."},
            "form_data": {"email": email},
        }, status_code=401)

    if not doctor.is_verified:
        return templates.TemplateResponse(request, LOGIN_TEMPLATE, {
            "errors": {"general": "Veuillez vérifier votre email avant de vous connecter."},
            "form_data": {"email": email},
        }, status_code=401)

    access_token = create_access_token(doctor.id)
    response = RedirectResponse(url=DOCTOR_HOME_URL, status_code=302)
    set_auth_cookie(response, access_token)

    logger.info(f"Successful login: doctor_id={doctor.id}")
    return response


# =============================================================================
# Logout
# =============================================================================

@router.get("/logout")
async def logout(request: Request):
    token = get_token_from_cookie(request)
    response = RedirectResponse(url="/", status_code=302)
    if token:
        revoke_token(token)
    clear_auth_cookie(response)
    return response


# =============================================================================
# Password recovery
# =============================================================================

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    if brevo_quota.is_blocked():
        return templates.TemplateResponse(request, FORGOT_PASSWORD_TEMPLATE, {
            "submitted": False,
            "error": "Il n'est pas possible de réinitialiser votre mot de passe en ce moment. Veuillez réessayer dans quelques minutes.",
        }, status_code=503)
    return templates.TemplateResponse(request, FORGOT_PASSWORD_TEMPLATE, {
        "submitted": False, "error": None,
    })


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(request: Request, db: DbSession):
    form_data = await request.form()
    email = (form_data.get("email") or "").strip().lower()

    if brevo_quota.is_blocked():
        return templates.TemplateResponse(request, FORGOT_PASSWORD_TEMPLATE, {
            "submitted": False,
            "error": "Il n'est pas possible de réinitialiser votre mot de passe en ce moment. Veuillez réessayer dans quelques minutes.",
        }, status_code=503)

    if not check_password_reset(request):
        return templates.TemplateResponse(request, FORGOT_PASSWORD_TEMPLATE, {
            "submitted": False,
            "error": "Trop de tentatives. Réessayez dans une heure.",
        })

    doctor = get_doctor_by_email(db, email)
    if doctor and doctor.is_verified:
        token = generate_token()
        db.add(PasswordResetToken(
            doctor_id=doctor.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        ))
        db.commit()

        reset_url = build_url(f"/reset-password?token={token}")
        await send_password_reset_email(
            to_email=doctor.email,
            doctor_name=f"{doctor.first_name} {doctor.last_name}",
            reset_url=reset_url,
        )

    # Always generic message
    return templates.TemplateResponse(request, FORGOT_PASSWORD_TEMPLATE, {
        "submitted": True, "error": None,
    })


# =============================================================================
# Password reset
# =============================================================================

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, db: DbSession):
    token = request.query_params.get("token", "")

    if not token:
        return templates.TemplateResponse(request, RESET_PASSWORD_TEMPLATE, {
            "valid": False, "token": "", "expired": False, "errors": {},
            "password_checks": {"min_length": False, "has_uppercase": False, "has_lowercase": False, "has_number": False},
        })

    rt = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token, PasswordResetToken.is_used == False
    ).first()

    if not rt or rt.expires_at < datetime.now(timezone.utc):
        return templates.TemplateResponse(request, RESET_PASSWORD_TEMPLATE, {
            "valid": False, "token": token, "expired": True, "errors": {},
            "password_checks": {"min_length": False, "has_uppercase": False, "has_lowercase": False, "has_number": False},
        })

    return templates.TemplateResponse(request, RESET_PASSWORD_TEMPLATE, {
        "valid": True, "token": token, "expired": False, "errors": {},
        "password_checks": {"min_length": False, "has_uppercase": False, "has_lowercase": False, "has_number": False},
    })


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(request: Request, db: DbSession):
    form_data = await request.form()
    token = form_data.get("token") or ""
    new_password = form_data.get("password") or ""

    rt = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token, PasswordResetToken.is_used == False
    ).first()

    if not rt or rt.expires_at < datetime.now(timezone.utc):
        return templates.TemplateResponse(request, RESET_PASSWORD_TEMPLATE, {
            "valid": False, "token": token, "expired": True, "errors": {},
            "password_checks": {"min_length": False, "has_uppercase": False, "has_lowercase": False, "has_number": False},
        })

    errors = {}
    if not new_password:
        errors["password"] = "Veuillez définir un nouveau mot de passe."
    elif not is_password_valid(new_password):
        errors["password"] = "Le mot de passe ne respecte pas les critères de sécurité."

    if errors:
        return templates.TemplateResponse(request, RESET_PASSWORD_TEMPLATE, {
            "valid": True, "token": token, "expired": False, "errors": errors,
            "password_checks": validate_password_strength(new_password),
        }, status_code=400)

    doctor = get_doctor_by_id(db, rt.doctor_id)
    if doctor:
        doctor.password_hash = hash_password(new_password)
        rt.is_used = True
        db.commit()

        change_timestamp = datetime.now(LUX_TZ).strftime("%d/%m/%Y à %H:%M (%Z)")
        await send_password_changed_email(
            to_email=doctor.email,
            doctor_name=f"{doctor.first_name} {doctor.last_name}",
            change_timestamp=change_timestamp,
        )
        logger.info(f"Password changed: doctor_id={doctor.id}")

    return RedirectResponse(url="/login", status_code=302)


# =============================================================================
# Terms and Privacy (static pages)
# =============================================================================

@router.get("/cgu", response_class=HTMLResponse)
async def cgu(request: Request):
    from datetime import datetime
    return templates.TemplateResponse(request, "base/cgu.html", {
        "current_date": "05/02/2026"
    })


@router.get("/confidentialite", response_class=HTMLResponse)
async def confidentialite(request: Request):
    from datetime import datetime
    return templates.TemplateResponse(request, "base/confidentialite.html", {
        "current_date": "05/02/2026"
    })
