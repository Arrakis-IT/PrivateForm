# =============================================================================
# PrivateForm - PDF Service
# =============================================================================
# Generation of professional PDFs with patient responses.
# Watermark (large logo, 30% opacity), bilingual footer.
# Password encryption using pypdf.
# =============================================================================

import io
from pathlib import Path
from datetime import datetime
import pytz
from fpdf import FPDF
from PIL import Image
import pypdf
from app.core.settings import settings
from app.core.logging import get_logger

logger = get_logger("pdf")

# Logo path (must exist on server)
LOGO_PATH = Path("/app/app/static/img/logo.png")

# Luxembourg timezone
LUX_TZ = pytz.timezone("Europe/Luxembourg")


def _get_lux_timestamp(dt: datetime | None = None) -> str:
    """Returns timestamp in European format with Luxembourg timezone."""
    if dt is None:
        dt = datetime.now(LUX_TZ)
    elif dt.tzinfo is None:
        dt = LUX_TZ.localize(dt)
    else:
        dt = dt.astimezone(LUX_TZ)

    # Determine CET or CEST
    tz_abbr = dt.strftime("%Z")  # CET or CEST automatically

    return dt.strftime(f"%d/%m/%Y à %H:%M ({tz_abbr})")


class PrivateFormPDF(FPDF):
    """
    Custom PDF with:
    - Professional header with doctor name and form
    - Watermark (large logo, 30% opacity) centered
    - Bilingual footer on all pages
    """

    def __init__(self, doctor_name: str, form_name: str, submission_timestamp: str):
        super().__init__()
        self.doctor_name = doctor_name
        self.form_name = form_name
        self.submission_timestamp = submission_timestamp
        # Add Unicode fontsDejaVu
        self.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        self.add_font("DejaVu", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        self.add_font("DejaVu", "I", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf")
        self.set_auto_page_break(auto=True, margin=45)  # Space for footer

    def header(self):
        """Header for each page."""
        # Only show complete header on first page
        if self.page_no() == 1:
            # Colored top line (gradient simulated with blue)
            self.set_fill_color(75, 143, 219)  # Branding blue
            self.rect(0, 0, self.w, 3, "F")

            self.ln(8)

            # Title: PrivateForm
            self.set_font("DejaVu", "B", 20)
            self.set_text_color(75, 143, 219)
            self.cell(0, 8, "PrivateForm", new_x="LMARGIN", new_y="NEXT", align="C")

            self.ln(4)

            # Doctor name
            self.set_font("DejaVu", "", 11)
            self.set_text_color(100, 100, 100)
            self.cell(0, 6, f"Dr. {self.doctor_name}", new_x="LMARGIN", new_y="NEXT", align="C")

            # Form name
            self.set_font("DejaVu", "B", 13)
            self.set_text_color(31, 41, 55)
            self.cell(0, 7, self.form_name, new_x="LMARGIN", new_y="NEXT", align="C")

            self.ln(3)

            # Divider line
            self.set_draw_color(229, 231, 235)
            self.line(15, self.get_y(), self.w - 15, self.get_y())

            self.ln(5)

            # Timestamp
            self.set_font("DejaVu", "I", 9)
            self.set_text_color(107, 114, 128)
            self.cell(0, 5, f"Envoyé le : {self.submission_timestamp}", new_x="LMARGIN", new_y="NEXT", align="C")

            self.ln(6)
        else:
            # Following pages: minimal header
            self.set_fill_color(75, 143, 219)
            self.rect(0, 0, self.w, 3, "F")
            self.ln(8)

            self.set_font("DejaVu", "B", 10)
            self.set_text_color(75, 143, 219)
            self.cell(0, 5, "PrivateForm", new_x="LMARGIN", new_y="NEXT", align="C")

            self.set_font("DejaVu", "", 9)
            self.set_text_color(100, 100, 100)
            self.cell(0, 5, self.form_name, new_x="LMARGIN", new_y="NEXT", align="C")

            self.ln(4)

            self.set_draw_color(229, 231, 235)
            self.line(15, self.get_y(), self.w - 15, self.get_y())
            self.ln(5)

    def footer(self):
        """
        Bilingual footer on ALL pages.
        Highly visible with marketing text.
        """
        self.set_y(-42)

        # Divider line
        self.set_draw_color(229, 231, 235)
        self.line(15, self.get_y(), self.w - 15, self.get_y())
        self.ln(3)

        # Bilingual marketing text
        self.set_font("DejaVu", "B", 8)
        self.set_text_color(75, 143, 219)

        # French
        self.cell(0, 4, "Synchronisation automatique avec votre logiciel ? Contactez-nous.",
                  new_x="LMARGIN", new_y="NEXT", align="C")

        self.ln(3)

        # Contact
        self.set_font("DejaVu", "", 7)
        self.set_text_color(107, 114, 128)
        self.cell(0, 4,
                  f"{settings.CONTACT_EMAIL}  |  {settings.CONTACT_PHONE}  |  {settings.CONTACT_WEB}",
                  new_x="LMARGIN", new_y="NEXT", align="C")

        # Page
        self.set_font("DejaVu", "I", 7)
        self.set_text_color(156, 163, 175)
        self.cell(0, 4, f"Page {self.page_no()}", new_x="LMARGIN", new_y="NEXT", align="C")

    def _add_watermark(self):
        """
        Adds watermark (large logo, 30% opacity) centered on the page.
        Executed when generating final PDF (post-processing with PIL).
        """
        # Watermark is added as image with opacity
        # fpdf2 does not support native opacity, so we use image with alpha
        if not LOGO_PATH.exists():
            logger.warning("Logo not found at expected path for watermark.")
            return

        try:
            # Create image with 30% opacity
            logo = Image.open(LOGO_PATH).convert("RGBA")
            # Adjust alpha to 30% (76 of 255)
            alpha = logo.split()[3]
            alpha = alpha.point(lambda p: int(p * 0.30))
            logo.putalpha(alpha)

            # Save temporarily as PNG with alpha
            watermark_path = "/tmp/privateform_watermark.png"
            logo.save(watermark_path, "PNG")

            # Calculate large centered size
            # Maximum width: 120mm centered on A4 page (210mm)
            img_width = 120
            img_height = logo.size[1] * (img_width / logo.size[0])

            # Centered position
            x = (self.w - img_width) / 2
            # Vertical center of page (approx.)
            y = (self.h - img_height) / 2

            # Add image
            self.image(watermark_path, x=x, y=y, w=img_width)

        except Exception as e:
            logger.error(f"Error adding watermark: {e}")


def generate_pdf(
    doctor_name: str,
    form_name: str,
    questions: list[dict],
    answers: list[dict],
    submission_timestamp: str,
) -> bytes:
    """
    Generates PDF with patient responses.

    Args:
        doctor_name: Doctor's full name
        form_name: Form name
        questions: List of dicts with info for each question
        answers: List of dicts with patient responses
        submission_timestamp: Luxembourg formatted timestamp

    Returns:
        Generated PDF bytes (unencrypted)
    """
    pdf = PrivateFormPDF(doctor_name, form_name, submission_timestamp)
    pdf.add_page()

    # Add watermark on first page
    # Save current position
    current_y = pdf.get_y()
    pdf._add_watermark()
    # Restore position to write content
    pdf.set_y(current_y)

    # Write questions and answers
    for i, question in enumerate(questions):
        question_id = question["id"]
        question_text = question["text"]
        question_type = question["question_type"]
        is_required = question["is_required"]

        # Find corresponding answer
        answer_value = ""
        for ans in answers:
            if ans["question_id"] == question_id:
                answer_value = ans["value"]
                break

        # Subtle alternating background
        if i % 2 == 0:
            pdf.set_fill_color(249, 250, 251)  # Very light gray
            pdf.rect(12, pdf.get_y(), pdf.w - 24, 18, "F")

        # Question number + text
        pdf.set_font("DejaVu", "B", 10)
        pdf.set_text_color(31, 41, 55)

        obligatorio_text = " *" if is_required else ""
        pdf.cell(0, 6, f"{i + 1}. {question_text}{obligatorio_text}", new_x="LMARGIN", new_y="NEXT")

        # Question type (small, gray)
        type_labels = {
            "text": "Texte",
            "text_long": "Texte long",
            "yes_no": "Oui / Non",
            "select": "Sélection unique",
            "multiselect": "Sélection multiple",
            "date": "Date",
            "number": "Nombre",
            "email": "Email",
            "phone": "Téléphone",
            "scale": "Échelle 1-10",
        }
        pdf.set_font("DejaVu", "I", 8)
        pdf.set_text_color(156, 163, 175)
        pdf.cell(0, 4, f"Type : {type_labels.get(question_type, question_type)}", new_x="LMARGIN", new_y="NEXT")

        # Answer
        pdf.set_font("DejaVu", "", 10)
        pdf.set_text_color(55, 65, 81)

        if not answer_value and answer_value != 0:
            pdf.set_text_color(156, 163, 175)
            pdf.multi_cell(0, 5, "Non répondu")
        elif question_type == "yes_no":
            label = "Oui" if answer_value == "yes" else "Non"
            pdf.cell(0, 5, label, new_x="LMARGIN", new_y="NEXT")
        elif question_type == "multiselect" and isinstance(answer_value, list):
            pdf.cell(0, 5, ", ".join(answer_value), new_x="LMARGIN", new_y="NEXT")
        elif question_type == "scale":
            # Show labels if they exist
            scale_label_1 = question.get("scale_label_1", "")
            scale_label_10 = question.get("scale_label_10", "")
            scale_text = str(answer_value)
            if scale_label_1 or scale_label_10:
                scale_text += f"  ({scale_label_1} ← → {scale_label_10})"
            pdf.cell(0, 5, scale_text, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, 5, str(answer_value))

        pdf.ln(4)

        # If page is filling up, add new page with watermark
        if pdf.get_y() > pdf.h - 55:
            pdf.add_page()
            pdf._add_watermark()

    # Generate PDF bytes
    pdf_bytes = pdf.output()
    return pdf_bytes


def encrypt_pdf(pdf_bytes: bytes, password: str) -> bytes:
    """
    Encrypts a PDF with password using pypdf.

    Args:
        pdf_bytes: Unencrypted PDF bytes
        password: Encryption password

    Returns:
        Encrypted PDF bytes
    """
    try:
        # Read PDF from bytes
        input_pdf = pypdf.PdfReader(io.BytesIO(pdf_bytes))

        # Create writer and add pages
        output_pdf = pypdf.PdfWriter()
        for page in input_pdf.pages:
            output_pdf.add_page(page)

        # Configure AES-256 encryption
        output_pdf.encrypt(
            user_password=password,
            owner_password=password,
            algorithm="AES-256"
        )

        # Write to bytes
        output_buffer = io.BytesIO()
        output_pdf.write(output_buffer)
        
        return output_buffer.getvalue()

    except Exception as e:
        logger.error(f"Error encrypting PDF: {e}")
        raise


def generate_and_encrypt_pdf(
    doctor_name: str,
    form_name: str,
    questions: list[dict],
    answers: list[dict],
    submission_timestamp: str,
    encryption_password: str,
) -> bytes:
    """
    Main function: generates and encrypts complete PDF.

    Returns:
        Password-encrypted PDF bytes
    """
    # 1. Generate PDF
    pdf_bytes = generate_pdf(
        doctor_name=doctor_name,
        form_name=form_name,
        questions=questions,
        answers=answers,
        submission_timestamp=submission_timestamp,
    )

    # 2. Encrypt PDF
    encrypted_pdf_bytes = encrypt_pdf(pdf_bytes, encryption_password)

    return encrypted_pdf_bytes


def generate_pdf_filename(form_slug: str, timestamp: datetime | None = None) -> str:
    """
    Generates PDF filename.
    Format: privateform_[slug]_[YYYYMMDD_HHMMSS].pdf
    """
    if timestamp is None:
        timestamp = datetime.now(LUX_TZ)
    elif timestamp.tzinfo is None:
        timestamp = LUX_TZ.localize(timestamp)

    ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
    return f"privateform_{form_slug}_{ts_str}.pdf"
