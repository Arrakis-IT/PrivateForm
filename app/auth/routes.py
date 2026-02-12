# =============================================================================
# PrivateForm - Auth Routes
# =============================================================================
# Authentication routes: registration, login, logout, email verification,
# password recovery and change.
# =============================================================================

import secrets
import pytz
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
    get_token_from_cookie, decode_access_token,
)
from app.core.rate_limiter import check_password_reset, check_verification_resend
from app.email.service import (
    send_verification_email, send_password_reset_email,
    send_password_changed_email,
)
from app.core.logging import get_logger

logger = get_logger("auth.routes")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

LUX_TZ = pytz.timezone("Europe/Luxembourg")


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
        return RedirectResponse(url="/doctor/home")
    return templates.TemplateResponse(request, "base/landing.html", {})


# =============================================================================
# Registro
# =============================================================================

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    token = get_token_from_cookie(request)
    if token and decode_access_token(token):
        return RedirectResponse(url="/doctor/home")
    return templates.TemplateResponse(request, "auth/register.html", {
        "specialties": MEDICAL_SPECIALTIES,
        "countries": AVAILABLE_COUNTRIES,
        "errors": {},
        "form_data": {},
        "password_checks": {"min_length": False, "has_uppercase": False, "has_lowercase": False, "has_number": False},
    })


@router.post("/register", response_class=HTMLResponse)
async def register_submit(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()

    last_name = (form_data.get("last_name") or "").strip()
    first_name = (form_data.get("first_name") or "").strip()
    email = (form_data.get("email") or "").strip().lower()
    password = form_data.get("password") or ""
    password_confirm = form_data.get("password_confirm") or ""
    pdf_password = form_data.get("pdf_password") or ""
    pdf_password_confirm = form_data.get("pdf_password_confirm") or ""
    specialty = form_data.get("specialty") or ""
    phone = (form_data.get("phone") or "").strip()
    country = form_data.get("country") or ""
    newsletter = form_data.get("newsletter") == "on"
    terms_accepted = form_data.get("terms_accepted") == "on"

    errors = {}

    if not last_name or len(last_name) < 2:
        errors["last_name"] = "Veuillez indiquer votre nom (minimum 2 caractères)."
    if not first_name or len(first_name) < 2:
        errors["first_name"] = "Veuillez indiquer votre prénom (minimum 2 caractères)."
    if not email:
        errors["email"] = "Veuillez indiquer votre adresse email."
    elif "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Le format de votre adresse email est invalide."
    if not password:
        errors["password"] = "Veuillez définir un mot de passe."
    elif not is_password_valid(password):
        errors["password"] = "Le mot de passe ne respecte pas les critères de sécurité."
    elif password != password_confirm:
        errors["password"] = "Les deux mots de passe ne correspondent pas."
    if not pdf_password:
        errors["pdf_password"] = "Veuillez définir un mot de passe de chiffrement."
    elif not is_password_valid(pdf_password):
        errors["pdf_password"] = "Le mot de passe de chiffrement ne respecte pas les critères de sécurité."
    elif pdf_password != pdf_password_confirm:
        errors["pdf_password"] = "Les deux mots de passe de chiffrement ne correspondent pas."
    if phone and not phone.startswith("+"):
        errors["phone"] = "Le format du téléphone doit inclure l'indicatif (ex: +352...)."
    if not terms_accepted:
        errors["terms_accepted"] = "Vous devez accepter les CGU et la politique de confidentialité."

    if errors:
        logger.warning(f"Validation errors in registration: {errors}")
        return templates.TemplateResponse(request, "auth/register.html", {
            "specialties": MEDICAL_SPECIALTIES,
            "countries": AVAILABLE_COUNTRIES,
            "errors": errors,
            "form_data": {
                "last_name": last_name, "first_name": first_name, "email": email,
                "specialty": specialty, "phone": phone, "country": country, "newsletter": newsletter,
            },
            "password_checks": validate_password_strength(password),
        }, status_code=400)

    # Email already exists -> generic message
    if get_doctor_by_email(db, email):
        errors["email"] = "Impossible de créer le compte. Veuillez vérifier vos informations."
        return templates.TemplateResponse(request, "auth/register.html", {
            "specialties": MEDICAL_SPECIALTIES,
            "countries": AVAILABLE_COUNTRIES,
            "errors": errors,
            "form_data": {
                "last_name": last_name, "first_name": first_name, "email": email,
                "specialty": specialty, "phone": phone, "country": country, "newsletter": newsletter,
            },
            "password_checks": validate_password_strength(password),
        }, status_code=400)

    # Create doctor
    doctor = Doctor(
        email=email,
        password_hash=hash_password(password),
        pdf_encryption_password=pdf_password,
        last_name=last_name,
        first_name=first_name,
        specialty=specialty if specialty else None,
        phone=phone if phone else None,
        country=country if country else None,
        newsletter=newsletter,
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

    logger.info(f"New doctor registered: {doctor.email}")
    return RedirectResponse(url=f"/verify-pending?email={email}", status_code=302)


# =============================================================================
# Pending verification
# =============================================================================

@router.get("/verify-pending", response_class=HTMLResponse)
async def verify_pending(request: Request):
    email = request.query_params.get("email", "")
    return templates.TemplateResponse(request, "auth/verify_pending.html", {
        "email": email, "resend_error": None, "resend_success": False,
    })


@router.post("/verify-pending/resend", response_class=HTMLResponse)
async def resend_verification(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    email = (form_data.get("email") or "").strip().lower()

    if not check_verification_resend(request):
        return templates.TemplateResponse(request, "auth/verify_pending.html", {
            "email": email,
            "resend_error": "Limite atteinte. Réessayez dans 24 heures.",
            "resend_success": False,
        })

    doctor = get_doctor_by_email(db, email)
    if not doctor or doctor.is_verified:
        return RedirectResponse(url="/login", status_code=302)

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

    return templates.TemplateResponse(request, "auth/verify_pending.html", {
        "email": email, "resend_error": None, "resend_success": True,
    })


# =============================================================================
# Email verification
# =============================================================================

@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email(request: Request, db: Session = Depends(get_db)):
    token = request.query_params.get("token", "")

    if not token:
        return templates.TemplateResponse(request, "auth/verify_result.html", {
            "success": False, "context": "verification", "expired": False, "email": "",
        })

    vt = db.query(VerificationToken).filter(
        VerificationToken.token == token, VerificationToken.is_used == False
    ).first()

    if not vt:
        return templates.TemplateResponse(request, "auth/verify_result.html", {
            "success": False, "context": "verification", "expired": False, "email": "",
        })

    if vt.expires_at < datetime.now(timezone.utc):
        doctor = get_doctor_by_id(db, vt.doctor_id)
        return templates.TemplateResponse(request, "auth/verify_result.html", {
            "success": False, "context": "verification", "expired": True,
            "email": doctor.email if doctor else "",
        })

    vt.is_used = True
    doctor = get_doctor_by_id(db, vt.doctor_id)
    if doctor:
        doctor.is_verified = True
    db.commit()

    logger.info(f"Email verified: {doctor.email if doctor else 'unknown'}")
    return templates.TemplateResponse(request, "auth/verify_result.html", {
        "success": True, "context": "verification", "expired": False, "email": "",
    })


# =============================================================================
# Login
# =============================================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    token = get_token_from_cookie(request)
    if token and decode_access_token(token):
        return RedirectResponse(url="/doctor/home")
    return templates.TemplateResponse(request, "auth/login.html", {"errors": {}, "form_data": {}})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    email = (form_data.get("email") or "").strip().lower()
    password = form_data.get("password") or ""

    errors = {}
    if not email:
        errors["email"] = "Veuillez indiquer votre adresse email."
    if not password:
        errors["password"] = "Veuillez indiquer votre mot de passe."
    if errors:
        return templates.TemplateResponse(request, "auth/login.html", {
            "errors": errors, "form_data": {"email": email},
        }, status_code=400)

    doctor = get_doctor_by_email(db, email)
    if not doctor:
        return templates.TemplateResponse(request, "auth/login.html", {
            "errors": {"general": "Email ou mot de passe incorrect."},
            "form_data": {"email": email},
        }, status_code=401)

    if not doctor.is_verified:
        return templates.TemplateResponse(request, "auth/login.html", {
            "errors": {"general": "Veuillez vérifier votre email avant de vous connecter."},
            "form_data": {"email": email},
        }, status_code=401)

    if not verify_password(password, doctor.password_hash):
        return templates.TemplateResponse(request, "auth/login.html", {
            "errors": {"general": "Email ou mot de passe incorrect."},
            "form_data": {"email": email},
        }, status_code=401)

    access_token = create_access_token(doctor.id)
    response = RedirectResponse(url="/doctor/home", status_code=302)
    set_auth_cookie(response, access_token)

    logger.info(f"Successful login: {doctor.email}")
    return response


# =============================================================================
# Logout
# =============================================================================

@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/", status_code=302)
    clear_auth_cookie(response)
    return response


# =============================================================================
# Password recovery
# =============================================================================

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "auth/forgot_password.html", {
        "submitted": False, "error": None,
    })


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    email = (form_data.get("email") or "").strip().lower()

    if not check_password_reset(request):
        return templates.TemplateResponse(request, "auth/forgot_password.html", {
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
    return templates.TemplateResponse(request, "auth/forgot_password.html", {
        "submitted": True, "error": None,
    })


# =============================================================================
# Password reset
# =============================================================================

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, db: Session = Depends(get_db)):
    token = request.query_params.get("token", "")

    if not token:
        return templates.TemplateResponse(request, "auth/reset_password.html", {
            "valid": False, "token": "", "expired": False, "errors": {},
            "password_checks": {"min_length": False, "has_uppercase": False, "has_lowercase": False, "has_number": False},
        })

    rt = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token, PasswordResetToken.is_used == False
    ).first()

    if not rt or rt.expires_at < datetime.now(timezone.utc):
        return templates.TemplateResponse(request, "auth/reset_password.html", {
            "valid": False, "token": token, "expired": True, "errors": {},
            "password_checks": {"min_length": False, "has_uppercase": False, "has_lowercase": False, "has_number": False},
        })

    return templates.TemplateResponse(request, "auth/reset_password.html", {
        "valid": True, "token": token, "expired": False, "errors": {},
        "password_checks": {"min_length": False, "has_uppercase": False, "has_lowercase": False, "has_number": False},
    })


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    token = form_data.get("token") or ""
    new_password = form_data.get("new_password") or ""
    new_password_confirm = form_data.get("new_password_confirm") or ""

    rt = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token, PasswordResetToken.is_used == False
    ).first()

    if not rt or rt.expires_at < datetime.now(timezone.utc):
        return templates.TemplateResponse(request, "auth/reset_password.html", {
            "valid": False, "token": token, "expired": True, "errors": {},
            "password_checks": {"min_length": False, "has_uppercase": False, "has_lowercase": False, "has_number": False},
        })

    errors = {}
    if not new_password:
        errors["new_password"] = "Veuillez définir un nouveau mot de passe."
    elif not is_password_valid(new_password):
        errors["new_password"] = "Le mot de passe ne respecte pas les critères de sécurité."
    elif new_password != new_password_confirm:
        errors["new_password"] = "Les deux mots de passe ne correspondent pas."

    if errors:
        return templates.TemplateResponse(request, "auth/reset_password.html", {
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
        logger.info(f"Password changed: {doctor.email}")

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