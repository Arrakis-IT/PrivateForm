# =============================================================================
# PrivateForm - Patient Routes
# =============================================================================
# Patient routes: view form (GET /f/{slug}),
# submit responses (POST /f/{slug}/submit).
# Zero persistence of patient data.
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

import sys
import pytz
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.settings import settings
from app.core.models import Form, Question
from app.core.rate_limiter import check_patient_submission
from app.pdf.service import generate_and_encrypt_pdf, generate_pdf_filename
from app.email.service import send_form_submission_email
from app.core.logging import get_logger
from app.auth.crypto import decrypt_pdf_password

logger = get_logger("patient.routes")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

LUX_TZ = pytz.timezone("Europe/Luxembourg")

# -----------------------------------------------------------------------------
# Validation constants
# -----------------------------------------------------------------------------
MAX_LONG_TEXT_CHARS = int(settings.MAX_LONG_TEXT_CHARS)
MAX_SUBMISSION_SIZE_KB = int(settings.MAX_SUBMISSION_SIZE_KB)


# =============================================================================
# Helpers
# =============================================================================

def get_form_by_slug(db: Session, slug: str) -> Form | None:
    return db.query(Form).filter(Form.slug == slug).first()


def get_client_ip(request: Request) -> str:
    """Gets client's real IP (proxy compatible)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def question_to_patient_dict(q: Question) -> dict:
    """Serializes question for patient template."""
    return {
        "id": q.id,
        "text": q.text,
        "question_type": q.question_type,
        "is_required": q.is_required,
        "order": q.order,
        "options": q.options,
        "allow_decimals": q.allow_decimals,
        "scale_label_1": q.scale_label_1,
        "scale_label_10": q.scale_label_10,
    }


def validate_answer(question: dict, answer) -> str | None:
    """
    Validates an individual answer.
    Returns None if valid, or an error string.
    """
    q_type = question["question_type"]
    is_required = question["is_required"]
    q_text = question["text"]

    # --- Required fields ---
    if is_required:
        if answer is None or (isinstance(answer, str) and answer.strip() == ""):
            return f"La réponse à « {q_text} » est obligatoire."
        if isinstance(answer, list) and len(answer) == 0:
            return f"La réponse à « {q_text} » est obligatoire."

    # If not required and empty, it's valid
    if answer is None or (isinstance(answer, str) and answer.strip() == ""):
        return None
    if isinstance(answer, list) and len(answer) == 0:
        return None

    # --- Validations by type ---
    if q_type == "text":
        if not isinstance(answer, str):
            return f"Format invalide pour « {q_text} »."

    elif q_type == "text_long":
        if not isinstance(answer, str):
            return f"Format invalide pour « {q_text} »."
        if len(answer) > MAX_LONG_TEXT_CHARS:
            return f"« {q_text} » dépasse le maximum de {MAX_LONG_TEXT_CHARS} caractères."

    elif q_type == "yes_no":
        if answer not in ("oui", "non"):
            return f"Réponse invalide pour « {q_text} ». Choisissez Oui ou Non."

    elif q_type == "select":
        options = question.get("options", [])
        if answer not in options:
            return f"Option invalide pour « {q_text} »."

    elif q_type == "multiselect":
        options = question.get("options", [])
        if not isinstance(answer, list):
            return f"Format invalide pour « {q_text} »."
        for item in answer:
            if item not in options:
                return f"Option invalide « {item} » pour « {q_text} »."

    elif q_type == "date":
        if not isinstance(answer, str):
            return f"Date invalide pour « {q_text} »."
        try:
            datetime.strptime(answer, "%Y-%m-%d")
        except ValueError:
            return f"Date invalide pour « {q_text} »."

    elif q_type == "number":
        if isinstance(answer, str):
            # Replace comma with dot (French convention)
            answer = answer.replace(",", ".")
        try:
            val = float(answer)
            allow_decimals = question.get("allow_decimals", False)
            if not allow_decimals and val != int(val):
                return f"« {q_text} » doit être un nombre entier."
        except (ValueError, TypeError):
            return f"Nombre invalide pour « {q_text} »."

    elif q_type == "email":
        if not isinstance(answer, str) or "@" not in answer or "." not in answer.split("@")[-1]:
            return f"Email invalide pour « {q_text} »."

    elif q_type == "phone":
        if not isinstance(answer, str):
            return f"Numéro de téléphone invalide pour « {q_text} »."
        # Flexible format: allow +, spaces, dashes, digits
        cleaned = answer.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if cleaned.startswith("+"):
            cleaned = cleaned[1:]
        if not cleaned.isdigit() or len(cleaned) < 7:
            return f"Numéro de téléphone invalide pour « {q_text} »."

    elif q_type == "scale":
        try:
            val = int(answer)
            if val < 1 or val > 10:
                return f"« {q_text} » doit être entre 1 et 10."
        except (ValueError, TypeError):
            return f"Valeur invalide pour « {q_text} »."

    return None


# =============================================================================
# GET /f/{slug} — Show form to patient
# =============================================================================

@router.get("/f/{slug}", response_class=HTMLResponse)
async def patient_form_page(request: Request, slug: str):
    # Create DB session directly (don't use dependency injection for public routes)
    from app.core.database import SessionLocal
    db = SessionLocal()

    try:
        form = get_form_by_slug(db, slug)

        # Form doesn't exist, inactive or deleted
        if not form or not form.is_active:
            return templates.TemplateResponse(request, "patient/unavailable.html", {}, status_code=200)

        doctor = form.doctor
        questions = sorted(form.questions, key=lambda q: q.order)

        return templates.TemplateResponse(request, "patient/form.html", {
            "form": {
                "id": form.id,
                "name": form.name,
                "slug": form.slug,
            },
            "doctor": {
                "name": f"{doctor.first_name} {doctor.last_name}",
            },
            "questions": [question_to_patient_dict(q) for q in questions],
            "hcaptcha_site_key": settings.HCAPTCHA_SITE_KEY,
        })
    finally:
        db.close()


# =============================================================================
# POST /f/{slug}/submit — Submit patient responses
# =============================================================================

@router.post("/f/{slug}/submit", response_class=JSONResponse)
async def patient_form_submit(request: Request, slug: str):
    from app.core.database import SessionLocal
    db = SessionLocal()

    try:
        # --- Rate limiting ---
        if not check_patient_submission(request):
            return JSONResponse({
                "success": False,
                "error": "Trop de soumissions. Veuillez réessayer plus tard."
            }, status_code=429)

        # --- Verify form ---
        form = get_form_by_slug(db, slug)
        if not form or not form.is_active:
            return JSONResponse({
                "success": False,
                "error": "Ce formulaire n'est plus disponible."
            }, status_code=404)

        # --- Parse body ---
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"success": False, "error": "Données invalides."}, status_code=400)

        # --- Verify maximum size (1MB) ---
        import json
        body_str = json.dumps(body)
        if len(body_str.encode("utf-8")) > MAX_SUBMISSION_SIZE_KB * 1024:
            return JSONResponse({"success": False, "error": "La soumission dépasse la taille maximale autorisée."}, status_code=400)

        # --- Verify hCaptcha ---
        captcha_token = body.get("hcaptcha_token", "")
        if settings.HCAPTCHA_SECRET_KEY and settings.HCAPTCHA_SECRET_KEY != "your_hcaptcha_secret_key_here":
            captcha_valid = await _verify_hcaptcha(captcha_token)
            if not captcha_valid:
                return JSONResponse({"success": False, "error": "Vérification de sécurité échouée."}, status_code=400)

        # --- Get sorted questions ---
        questions = sorted(form.questions, key=lambda q: q.order)
        answers_raw = body.get("answers", {})

        # --- Validate answers ---
        errors = []
        validated_answers = []  # List of {question, answer} for the PDF

        for q in questions:
            q_dict = question_to_patient_dict(q)
            raw_answer = answers_raw.get(q.id)

            # Normalize
            if q.question_type == "number" and isinstance(raw_answer, str):
                raw_answer = raw_answer.replace(",", ".")

            error = validate_answer(q_dict, raw_answer)
            if error:
                errors.append(error)
            else:
                # Format answer for the PDF
                display_answer = _format_answer_for_pdf(q.question_type, raw_answer, q_dict)
                validated_answers.append({
                    "question_id": q.id,
                    "question_text": q.text,
                    "question_type": q.question_type,
                    "value": display_answer,  # Change "answer" to "value"
                })

        if errors:
            return JSONResponse({"success": False, "errors": errors}, status_code=400)

        # --- Generate timestamp ---
        now_lux = datetime.now(LUX_TZ)
        submission_timestamp = now_lux.strftime("%d/%m/%Y à %H:%M (CET)")

        # --- Generate and encrypt PDF ---
        doctor = form.doctor
        doctor_name = f"{doctor.first_name} {doctor.last_name}"

        try:
            encrypted_pdf = generate_and_encrypt_pdf(
                doctor_name=doctor_name,
                form_name=form.name,
                questions=[question_to_patient_dict(q) for q in questions],
                answers=validated_answers,
                submission_timestamp=submission_timestamp,
                encryption_password=decrypt_pdf_password(doctor.pdf_encryption_password),
            )
            pdf_filename = generate_pdf_filename(form.slug, now_lux)

            # LOCAL only: save pdf on /temp for debugging
            # import os
            # pdf_path = f"/tmp/{pdf_filename}"
            # with open(pdf_path, "wb") as f:
            #     f.write(encrypted_pdf)
            # logger.info(f"PDF temporarily saved at {pdf_path}")
        except Exception as e:
            logger.error(f"Error generating PDF for form {slug}: {e}")
            return JSONResponse({"success": False, "error": "Erreur d'envoi. Si le problème persiste, contactez votre médecin."}, status_code=500)

        # --- Send email to doctor ---
        try:
            await send_form_submission_email(
                to_email=doctor.email,
                doctor_name=doctor_name,
                form_name=form.name,
                submission_timestamp=submission_timestamp,
                pdf_bytes=encrypted_pdf,
                pdf_filename=pdf_filename,
            )
        except Exception as e:
            logger.error(f"Error sending email for form {slug}: {e}")
            return JSONResponse({"success": False, "error": "Erreur d'envoi. Si le problème persiste, contactez votre médecin."}, status_code=500)

        # --- PDF destroyed (never saved to disk) ---
        del encrypted_pdf

        # --- Increment counter ---
        form.submission_count += 1
        db.commit()

        logger.info(f"Form {slug} submitted successfully. Total submissions: {form.submission_count}")

        # --- Successful response ---
        return JSONResponse({
            "success": True,
            "timestamp": submission_timestamp,
        })

    finally:
        db.close()


# =============================================================================
# Internal helpers
# =============================================================================

def _format_answer_for_pdf(question_type: str, answer, q_dict: dict) -> str:
    """Format the answer for display in the PDF."""
    if answer is None:
        return "—"

    if question_type == "yes_no":
        return "Oui" if answer == "oui" else "Non"

    if question_type == "multiselect":
        if isinstance(answer, list):
            return ", ".join(answer) if answer else "—"
        return str(answer)

    if question_type == "number":
        try:
            val = float(str(answer).replace(",", "."))
            allow_decimals = q_dict.get("allow_decimals", False)
            if allow_decimals:
                # French format: comma as decimal separator
                formatted = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
                return formatted
            else:
                # Integer with French thousands separator
                formatted = f"{int(val):,}".replace(",", " ")
                return formatted
        except (ValueError, TypeError):
            return str(answer)

    if question_type == "date":
        try:
            dt = datetime.strptime(str(answer), "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            return str(answer)

    if question_type == "scale":
        labels = ""
        label_1 = q_dict.get("scale_label_1", "")
        label_10 = q_dict.get("scale_label_10", "")
        if label_1 and label_10:
            labels = f" ({label_1} → {label_10})"
        return f"{answer}/10{labels}"

    return str(answer)


async def _verify_hcaptcha(token: str) -> bool:
    """Verifica el token de hCaptcha contra la API de hCaptcha."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://hcaptcha.com/siteverify",
                data={
                    "secret": settings.HCAPTCHA_SECRET_KEY,
                    "response": token,
                },
                timeout=10.0,
            )
            data = response.json()
            return data.get("success", False)
    except Exception as e:
        logger.error(f"Error verifying hCaptcha: {e}")
        return False