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
from zoneinfo import ZoneInfo
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.settings import settings
from app.core.models import Form, Question
from app.core.rate_limiter import check_patient_submission, brevo_quota
from app.pdf.service import generate_and_encrypt_pdf, generate_pdf_filename
from app.email.service import send_form_submission_email
from app.core.logging import get_logger
from app.auth.crypto import decrypt_pdf_password

logger = get_logger("patient.routes")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

LUX_TZ = ZoneInfo("Europe/Luxembourg")

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
    q_text = question["text"]

    if question["is_required"] and _is_empty(answer):
        return f"La réponse à « {q_text} » est obligatoire."

    if _is_empty(answer):
        return None

    validator = _ANSWER_VALIDATORS.get(question["question_type"])
    return validator(answer, q_text, question) if validator else None


def _is_empty(answer) -> bool:
    if answer is None:
        return True
    if isinstance(answer, str) and answer.strip() == "":
        return True
    return isinstance(answer, list) and len(answer) == 0


def _validate_type_text(answer, q_text: str, question: dict) -> str | None:
    if not isinstance(answer, str):
        return f"Format invalide pour « {q_text} »."
    return None


def _validate_type_text_long(answer, q_text: str, question: dict) -> str | None:
    if not isinstance(answer, str):
        return f"Format invalide pour « {q_text} »."
    if len(answer) > MAX_LONG_TEXT_CHARS:
        return f"« {q_text} » dépasse le maximum de {MAX_LONG_TEXT_CHARS} caractères."
    return None


def _validate_type_yes_no(answer, q_text: str, question: dict) -> str | None:
    if answer not in ("oui", "non"):
        return f"Réponse invalide pour « {q_text} ». Choisissez Oui ou Non."
    return None


def _validate_type_select(answer, q_text: str, question: dict) -> str | None:
    if answer not in question.get("options", []):
        return f"Option invalide pour « {q_text} »."
    return None


def _validate_type_multiselect(answer, q_text: str, question: dict) -> str | None:
    if not isinstance(answer, list):
        return f"Format invalide pour « {q_text} »."
    options = question.get("options", [])
    for item in answer:
        if item not in options:
            return f"Option invalide « {item} » pour « {q_text} »."
    return None


def _validate_type_date(answer, q_text: str, question: dict) -> str | None:
    if not isinstance(answer, str):
        return f"Date invalide pour « {q_text} »."
    try:
        datetime.strptime(answer, "%Y-%m-%d")
    except ValueError:
        return f"Date invalide pour « {q_text} »."
    return None


def _validate_type_number(answer, q_text: str, question: dict) -> str | None:
    if isinstance(answer, str):
        answer = answer.replace(",", ".")  # French decimal convention
    try:
        val = float(answer)
        if not question.get("allow_decimals", False) and val != int(val):
            return f"« {q_text} » doit être un nombre entier."
    except (ValueError, TypeError):
        return f"Nombre invalide pour « {q_text} »."
    return None


def _validate_type_email(answer, q_text: str, question: dict) -> str | None:
    if not isinstance(answer, str) or "@" not in answer or "." not in answer.split("@")[-1]:
        return f"Email invalide pour « {q_text} »."
    return None


def _validate_type_phone(answer, q_text: str, question: dict) -> str | None:
    if not isinstance(answer, str):
        return f"Numéro de téléphone invalide pour « {q_text} »."
    cleaned = answer.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if not cleaned.isdigit() or len(cleaned) < 7:
        return f"Numéro de téléphone invalide pour « {q_text} »."
    return None


def _validate_type_scale(answer, q_text: str, question: dict) -> str | None:
    try:
        val = int(answer)
        if val < 1 or val > 10:
            return f"« {q_text} » doit être entre 1 et 10."
    except (ValueError, TypeError):
        return f"Valeur invalide pour « {q_text} »."
    return None


def _validate_type_matricule(answer, q_text: str, question: dict) -> str | None:
    if not isinstance(answer, str):
        return f"Matricule invalide pour « {q_text} »."
    digits_only = answer.replace(" ", "").replace("-", "")
    if not digits_only.isdigit() or len(digits_only) != 13:
        return "Le matricule doit contenir exactement 13 chiffres."
    return None


_ANSWER_VALIDATORS = {
    "text": _validate_type_text,
    "text_long": _validate_type_text_long,
    "yes_no": _validate_type_yes_no,
    "select": _validate_type_select,
    "multiselect": _validate_type_multiselect,
    "date": _validate_type_date,
    "number": _validate_type_number,
    "email": _validate_type_email,
    "phone": _validate_type_phone,
    "scale": _validate_type_scale,
    "matricule": _validate_type_matricule,
}


# =============================================================================
# GET /f/{slug} — Show form to patient
# =============================================================================

@router.get("/f/{slug}", response_class=HTMLResponse)
async def patient_form_page(request: Request, slug: str):
    # Create DB session directly (don't use dependency injection for public routes)
    from app.core.database import SessionLocal
    db = SessionLocal()

    try:
        # Brevo quota check — block access if at 99% of daily limit
        if brevo_quota.is_blocked():
            return templates.TemplateResponse(request, "patient/unavailable.html", {
                "quota_exceeded": True,
            }, status_code=503)

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

def _collect_validated_answers(questions, answers_raw: dict) -> tuple[list, list]:
    """Validates all answers. Returns (errors, validated_answers)."""
    errors = []
    validated_answers = []
    for q in questions:
        q_dict = question_to_patient_dict(q)
        raw_answer = answers_raw.get(q.id)
        if q.question_type == "number" and isinstance(raw_answer, str):
            raw_answer = raw_answer.replace(",", ".")
        error = validate_answer(q_dict, raw_answer)
        if error:
            errors.append(error)
        else:
            validated_answers.append({
                "question_id": q.id,
                "question_text": q.text,
                "question_type": q.question_type,
                "value": _format_answer_for_pdf(q.question_type, raw_answer, q_dict),
            })
    return errors, validated_answers


async def _generate_and_send_pdf(form, doctor, questions, validated_answers: list, submission_timestamp: str):
    """Generates PDF and sends it by email. Returns error JSONResponse or None on success."""
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
        pdf_filename = generate_pdf_filename(form.slug, datetime.now(LUX_TZ))
    except Exception as e:
        logger.error(f"Error generating PDF for form id={form.id}: {e}")
        return JSONResponse({"success": False, "error": "Erreur d'envoi. Si le problème persiste, contactez votre médecin."}, status_code=500)

    email_sent = await send_form_submission_email(
        to_email=doctor.email,
        doctor_name=doctor_name,
        form_name=form.name,
        submission_timestamp=submission_timestamp,
        pdf_bytes=encrypted_pdf,
        pdf_filename=pdf_filename,
    )
    del encrypted_pdf  # Never persisted to disk
    if not email_sent:
        logger.error(f"Email delivery failed for form id={form.id} — patient answers preserved on screen")
        return JSONResponse({"success": False, "error": "L'envoi a échoué. Vos réponses sont conservées, veuillez réessayer dans quelques instants."}, status_code=500)
    return None


@router.post("/f/{slug}/submit", response_class=JSONResponse)
async def patient_form_submit(request: Request, slug: str):
    import json
    from app.core.database import SessionLocal
    db = SessionLocal()

    try:
        if not check_patient_submission(request):
            return JSONResponse({"success": False, "error": "Trop de soumissions. Veuillez réessayer plus tard."}, status_code=429)

        form = get_form_by_slug(db, slug)
        if not form or not form.is_active:
            return JSONResponse({"success": False, "error": "Ce formulaire n'est plus disponible."}, status_code=404)

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"success": False, "error": "Données invalides."}, status_code=400)

        if len(json.dumps(body).encode("utf-8")) > MAX_SUBMISSION_SIZE_KB * 1024:
            return JSONResponse({"success": False, "error": "La soumission dépasse la taille maximale autorisée."}, status_code=400)

        if settings.HCAPTCHA_SECRET_KEY and settings.HCAPTCHA_SECRET_KEY != "your_hcaptcha_secret_key_here":
            if not await _verify_hcaptcha(body.get("hcaptcha_token", "")):
                return JSONResponse({"success": False, "error": "Vérification de sécurité échouée."}, status_code=400)

        questions = sorted(form.questions, key=lambda q: q.order)
        errors, validated_answers = _collect_validated_answers(questions, body.get("answers", {}))
        if errors:
            return JSONResponse({"success": False, "errors": errors}, status_code=400)

        submission_timestamp = datetime.now(LUX_TZ).strftime("%d/%m/%Y à %H:%M (CET)")
        error_response = await _generate_and_send_pdf(form, form.doctor, questions, validated_answers, submission_timestamp)
        if error_response:
            return error_response

        form.submission_count += 1
        db.commit()
        logger.info(f"Form id={form.id} submitted successfully. Total submissions: {form.submission_count}")
        return JSONResponse({"success": True, "timestamp": submission_timestamp})

    finally:
        db.close()


# =============================================================================
# Internal helpers
# =============================================================================

def _fmt_yes_no(answer, q_dict: dict) -> str:
    return "Oui" if answer == "oui" else "Non"


def _fmt_multiselect(answer, q_dict: dict) -> str:
    if isinstance(answer, list):
        return ", ".join(answer) if answer else "—"
    return str(answer)


def _fmt_number(answer, q_dict: dict) -> str:
    try:
        val = float(str(answer).replace(",", "."))
        if q_dict.get("allow_decimals", False):
            return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
        return f"{int(val):,}".replace(",", " ")
    except (ValueError, TypeError):
        return str(answer)


def _fmt_date(answer, q_dict: dict) -> str:
    try:
        return datetime.strptime(str(answer), "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(answer)


def _fmt_scale(answer, q_dict: dict) -> str:
    label_1 = q_dict.get("scale_label_1", "")
    label_10 = q_dict.get("scale_label_10", "")
    labels = f" ({label_1} → {label_10})" if label_1 and label_10 else ""
    return f"{answer}/10{labels}"


_PDF_FORMATTERS = {
    "yes_no": _fmt_yes_no,
    "multiselect": _fmt_multiselect,
    "number": _fmt_number,
    "date": _fmt_date,
    "scale": _fmt_scale,
}


def _format_answer_for_pdf(question_type: str, answer, q_dict: dict) -> str:
    """Format the answer for display in the PDF."""
    if answer is None:
        return "—"
    formatter = _PDF_FORMATTERS.get(question_type)
    return formatter(answer, q_dict) if formatter else str(answer)


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