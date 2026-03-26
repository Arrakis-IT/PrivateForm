# =============================================================================
# PrivateForm - Forms Routes
# =============================================================================
# Doctor routes: home (listing), create/edit form, activate/deactivate,
# delete, share (QR/URL).
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

import json
import qrcode
import io
import base64
from typing import Annotated
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.settings import settings
from app.core.models import Doctor, Form, Question, VALID_QUESTION_TYPES
from app.auth.utils import get_current_doctor_id
from app.core.logging import get_logger, sanitize_log

logger = get_logger("forms.routes")

DbSession = Annotated[Session, Depends(get_db)]
CurrentDoctorId = Annotated[str, Depends(get_current_doctor_id)]

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# =============================================================================
# Helpers
# =============================================================================

def get_doctor(db: Session, doctor_id: str) -> Doctor | None:
    return db.query(Doctor).filter(Doctor.id == doctor_id).first()


def get_form(db: Session, form_id: str, doctor_id: str) -> Form | None:
    return db.query(Form).filter(Form.id == form_id, Form.doctor_id == doctor_id).first()


def form_to_dict(form: Form) -> dict:
    """Converts a SQLAlchemy Form to dict for template."""
    return {
        "id": form.id,
        "name": form.name,
        "slug": form.slug,
        "is_active": form.is_active,
        "is_example": form.is_example,
        "submission_count": form.submission_count,
        "created_at": form.created_at,
        "updated_at": form.updated_at,
        "questions_count": len(form.questions),
    }


def question_to_dict(q: Question) -> dict:
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


def build_form_url(slug: str) -> str:
    protocol = "https" if settings.APP_DOMAIN != "localhost" else "http"
    return f"{protocol}://{settings.APP_DOMAIN}/f/{slug}"


def generate_qr_base64(url: str) -> str:
    """Generates a QR code as base64 string (300x300px, black on white)."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img = img.resize((300, 300))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def count_forms(db: Session, doctor_id: str) -> int:
    return db.query(Form).filter(Form.doctor_id == doctor_id).count()


def _validate_question_text(text: str, errors: list) -> None:
    if not text or len(text) < 5:
        errors.append("La question doit contenir au moins 5 caractères.")
    elif len(text) > 500:
        errors.append("La question ne doit pas dépasser 500 caractères.")


def _validate_question_type(q_type: str, errors: list) -> None:
    if not q_type:
        errors.append("Veuillez sélectionner un type de réponse.")
    elif q_type not in VALID_QUESTION_TYPES:
        errors.append("Type de réponse invalide.")


def _validate_select_options(q: dict, errors: list) -> None:
    options = q.get("options") or []
    if not options or len(options) < 2:
        errors.append("Vous devez avoir au moins 2 options.")
    elif len(options) > settings.MAX_OPTIONS_PER_QUESTION:
        errors.append(f"Maximum {settings.MAX_OPTIONS_PER_QUESTION} options autorisées.")


def _validate_scale_labels(q: dict, errors: list) -> None:
    label_1 = (q.get("scale_label_1") or "").strip()
    label_10 = (q.get("scale_label_10") or "").strip()
    if not label_1:
        errors.append("L'étiquette pour 1 est obligatoire.")
    elif len(label_1) > 30:
        errors.append("L'étiquette pour 1 ne doit pas dépasser 30 caractères.")
    if not label_10:
        errors.append("L'étiquette pour 10 est obligatoire.")
    elif len(label_10) > 30:
        errors.append("L'étiquette pour 10 ne doit pas dépasser 30 caractères.")


def _validate_single_question(q: dict) -> list[str]:
    errors: list[str] = []
    text = (q.get("text") or "").strip()
    q_type = q.get("question_type") or ""
    _validate_question_text(text, errors)
    _validate_question_type(q_type, errors)
    if q_type in ("select", "multiselect"):
        _validate_select_options(q, errors)
    if q_type == "scale":
        _validate_scale_labels(q, errors)
    return errors


def validate_questions(questions_data: list[dict]) -> dict[int, list[str]]:
    """
    Validates all questions.
    Returns dict of {index: [errors]} only for questions with errors.
    """
    return {
        i: errs
        for i, q in enumerate(questions_data)
        if (errs := _validate_single_question(q))
    }


# =============================================================================
# Home - Forms listing
# =============================================================================

@router.get("/home", response_class=HTMLResponse)
async def home(request: Request, db: DbSession,
               doctor_id: CurrentDoctorId):
    doctor = get_doctor(db, doctor_id)
    if not doctor:
        return RedirectResponse(url="/login", status_code=302)

    forms = db.query(Form).filter(Form.doctor_id == doctor_id).order_by(Form.updated_at.desc()).all()
    forms_data = [form_to_dict(f) for f in forms]

    total_forms = len(forms_data)
    at_limit = total_forms >= doctor.form_limit

    return templates.TemplateResponse(request, "forms/home.html", {
        "doctor": doctor,
        "forms": forms_data,
        "at_limit": at_limit,
        "form_limit": doctor.form_limit,
        "question_limit": doctor.question_limit,
        "contact_email": settings.CONTACT_EMAIL,
    })


# =============================================================================
# Create new form
# =============================================================================

@router.get("/form/new", response_class=HTMLResponse)
async def new_form_page(request: Request, db: DbSession,
                        doctor_id: CurrentDoctorId):
    doctor = get_doctor(db, doctor_id)
    if not doctor:
        return RedirectResponse(url="/login", status_code=302)

    # Verify limit
    total_forms = count_forms(db, doctor_id)
    if total_forms >= doctor.form_limit:
        return RedirectResponse(url="/doctor/home", status_code=302)

    return templates.TemplateResponse(request, "forms/editor.html", {
        "doctor": doctor,
        "form": None,
        "form_name": "",
        "questions": [],
        "errors": {},
        "question_errors": {},
        "is_new": True,
        "question_types": VALID_QUESTION_TYPES,
        "max_questions": doctor.question_limit,
        "max_options": settings.MAX_OPTIONS_PER_QUESTION,
        "max_long_text": settings.MAX_LONG_TEXT_CHARS,
    })


@router.post("/form/new", response_class=HTMLResponse)
async def new_form_submit(request: Request, db: DbSession,
                          doctor_id: CurrentDoctorId):
    doctor = get_doctor(db, doctor_id)
    if not doctor:
        return RedirectResponse(url="/login", status_code=302)

    # Verify limit
    total_forms = count_forms(db, doctor_id)
    if total_forms >= doctor.form_limit:
        return RedirectResponse(url="/doctor/home", status_code=302)

    # Receive JSON instead of form data
    try:
        json_data = await request.json()
        form_name = (json_data.get("name") or "").strip()
        questions_data = json_data.get("questions") or []
    except Exception:
        form_name = ""
        questions_data = []

    errors = {}

    # Validate form name
    if not form_name or len(form_name) < 3:
        errors["form_name"] = "Le nom du formulaire doit contenir au moins 3 caractères."
    elif len(form_name) > 100:
        errors["form_name"] = "Le nom du formulaire ne doit pas dépasser 100 caractères."
    else:
        # Verify name uniqueness
        existing = db.query(Form).filter(
            Form.doctor_id == doctor_id,
            Form.name == form_name
        ).first()
        if existing:
            errors["form_name"] = "Un formulaire avec ce nom existe déjà. Choisissez un autre nom."

    # Verify at least 1 question
    if not questions_data:
        errors["questions"] = "Le formulaire doit contenir au moins une question."

    # Verify maximum questions
    if len(questions_data) > doctor.question_limit:
        errors["questions"] = f"Maximum {doctor.question_limit} questions autorisées."

    # Validate questions
    question_errors = validate_questions(questions_data)

    if errors or question_errors:
        logger.warning(f"Validation errors when creating form: errors={sanitize_log(errors)}, question_errors={sanitize_log(question_errors)}")
        all_errors = {**errors}
        if question_errors:
            all_errors["question_errors"] = question_errors
        error_messages = [v for v in errors.values()] + [str(question_errors)]
        return JSONResponse(
            content={"success": False, "errors": error_messages},
            status_code=400
        )

    # Create form
    new_form = Form(
        doctor_id=doctor_id,
        name=form_name,
        is_active=False,  # Inactive when created
        is_example=False,
    )
    db.add(new_form)
    db.flush()  # To obtain the ID

    # Create questions
    for i, q in enumerate(questions_data):
        options = q.get("options")
        if isinstance(options, str):
            # Parse options from textarea (one per line)
            options = [opt.strip() for opt in options.strip().split("\n") if opt.strip()]

        question = Question(
            form_id=new_form.id,
            text=q["text"].strip(),
            question_type=q["question_type"],
            is_required=q.get("is_required", True),
            order=i,
            options=options if q["question_type"] in ("select", "multiselect") else None,
            allow_decimals=q.get("allow_decimals") if q["question_type"] == "number" else None,
            scale_label_1=q.get("scale_label_1", "").strip() if q["question_type"] == "scale" else None,
            scale_label_10=q.get("scale_label_10", "").strip() if q["question_type"] == "scale" else None,
        )
        db.add(question)

    db.commit()
    logger.info(f"Form created: slug={new_form.slug}")

    # Return JSON with created form ID
    return JSONResponse(content={"success": True, "form_id": new_form.id})


# =============================================================================
# Edit existing form
# =============================================================================

@router.get("/form/{form_id}/edit", response_class=HTMLResponse)
async def edit_form_page(request: Request, form_id: str, db: DbSession,
                         doctor_id: CurrentDoctorId):
    doctor = get_doctor(db, doctor_id)
    form = get_form(db, form_id, doctor_id)

    if not doctor or not form:
        return RedirectResponse(url="/doctor/home", status_code=302)

    questions = [question_to_dict(q) for q in form.questions]

    return templates.TemplateResponse(request, "forms/editor.html", {
        "doctor": doctor,
        "form": form,
        "form_name": form.name,
        "questions": questions,
        "errors": {},
        "question_errors": {},
        "is_new": False,
        "question_types": VALID_QUESTION_TYPES,
        "max_questions": doctor.question_limit,
        "max_options": settings.MAX_OPTIONS_PER_QUESTION,
        "max_long_text": settings.MAX_LONG_TEXT_CHARS,
    })


@router.post("/form/{form_id}/edit", response_class=HTMLResponse)
async def edit_form_submit(request: Request, form_id: str, db: DbSession,
                           doctor_id: CurrentDoctorId):
    doctor = get_doctor(db, doctor_id)
    form = get_form(db, form_id, doctor_id)

    if not doctor or not form:
        return RedirectResponse(url="/doctor/home", status_code=302)

    # Receive JSON instead of form data
    try:
        json_data = await request.json()
        form_name = (json_data.get("name") or "").strip()
        questions_data = json_data.get("questions") or []
    except Exception:
        form_name = ""
        questions_data = []

    errors = {}

    # Validate name
    if not form_name or len(form_name) < 3:
        errors["form_name"] = "Le nom du formulaire doit contenir au moins 3 caractères."
    elif len(form_name) > 100:
        errors["form_name"] = "Le nom du formulaire ne doit pas dépasser 100 caractères."
    else:
        # Uniqueness except for the same form
        existing = db.query(Form).filter(
            Form.doctor_id == doctor_id,
            Form.name == form_name,
            Form.id != form_id
        ).first()
        if existing:
            errors["form_name"] = "Un formulaire avec ce nom existe déjà. Choisissez un autre nom."

    if not questions_data:
        errors["questions"] = "Le formulaire doit contenir au moins une question."
    if len(questions_data) > doctor.question_limit:
        errors["questions"] = f"Maximum {doctor.question_limit} questions autorisées."

    question_errors = validate_questions(questions_data)

    if errors or question_errors:
        all_errors = {**errors}
        if question_errors:
            all_errors["question_errors"] = question_errors
        error_messages = [v for v in errors.values()] + ([str(question_errors)] if question_errors else [])
        return JSONResponse(
            content={"success": False, "errors": error_messages},
            status_code=400
        )

    # Update form
    form.name = form_name

    # Deactivate form during edit to prevent inconsistencies with in-flight submissions
    was_active = form.is_active
    form.is_active = False

    # Delete existing questions and recreate them (simpler than trying to diff)
    db.query(Question).filter(Question.form_id == form_id).delete()

    for i, q in enumerate(questions_data):
        options = q.get("options")
        if isinstance(options, str):
            options = [opt.strip() for opt in options.strip().split("\n") if opt.strip()]

        question = Question(
            form_id=form_id,
            text=q["text"].strip(),
            question_type=q["question_type"],
            is_required=q.get("is_required", True),
            order=i,
            options=options if q["question_type"] in ("select", "multiselect") else None,
            allow_decimals=q.get("allow_decimals") if q["question_type"] == "number" else None,
            scale_label_1=q.get("scale_label_1", "").strip() if q["question_type"] == "scale" else None,
            scale_label_10=q.get("scale_label_10", "").strip() if q["question_type"] == "scale" else None,
        )
        db.add(question)

    db.commit()
    logger.info(f"Form edited: slug={form.slug}")

    # Return JSON with success; notify frontend if form was deactivated
    return JSONResponse(content={"success": True, "form_id": form_id, "was_deactivated": was_active})


# =============================================================================
# Toggle active/inactive (AJAX)
# =============================================================================

@router.post("/form/{form_id}/toggle", response_class=JSONResponse)
async def toggle_form(form_id: str, request: Request, db: DbSession,
                      doctor_id: CurrentDoctorId):
    form = get_form(db, form_id, doctor_id)
    if not form:
        return JSONResponse(content={"error": "Formulaire non trouvé"}, status_code=404)

    form.is_active = not form.is_active
    db.commit()

    logger.info(f"Form {'activated' if form.is_active else 'deactivated'}: slug={form.slug}")
    return JSONResponse(content={"is_active": form.is_active})


# =============================================================================
# Delete form
# =============================================================================

@router.post("/form/{form_id}/delete", response_class=JSONResponse)
async def delete_form(form_id: str, request: Request, db: DbSession,
                      doctor_id: CurrentDoctorId):
    form = get_form(db, form_id, doctor_id)
    if not form:
        return JSONResponse(content={"error": "Formulaire non trouvé"}, status_code=404)

    # Example forms cannot be deleted (they are needed to always have at least one form)
    if form.is_example:
        return JSONResponse(
            content={"error": "Vous devez conserver au moins un formulaire."},
            status_code=403
        )

    db.delete(form)
    db.commit()

    logger.info(f"Form deleted: slug={form.slug}")
    return JSONResponse(content={"success": True})


# =============================================================================
# Modal QR/URL (modal)
# =============================================================================

@router.get("/form/{form_id}/share", response_class=JSONResponse)
async def get_share_data(form_id: str, db: DbSession,
                         doctor_id: CurrentDoctorId):
    form = get_form(db, form_id, doctor_id)
    if not form:
        return JSONResponse(content={"error": "Formulaire non trouvé"}, status_code=404)

    url = build_form_url(form.slug)
    qr_base64 = generate_qr_base64(url)

    return JSONResponse(content={
        "form_name": form.name,
        "url": url,
        "qr_base64": qr_base64,
        "slug": form.slug,
    })


# =============================================================================
# Download QR as PNG
# =============================================================================

@router.get("/form/{form_id}/qr-download")
async def download_qr(form_id: str, db: DbSession,
                      doctor_id: CurrentDoctorId):
    from fastapi.responses import Response

    form = get_form(db, form_id, doctor_id)
    if not form:
        return RedirectResponse(url="/doctor/home", status_code=302)

    url = build_form_url(form.slug)
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img = img.resize((300, 300))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    # Filename: privateform_qr_[form_name].png
    safe_name = "".join(c if c.isalnum() or c in ("-", "_", " ") else "" for c in form.name)
    filename = f"privateform_qr_{safe_name}.png"

    return Response(
        content=buffer.read(),
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )