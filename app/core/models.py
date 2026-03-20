# =============================================================================
# PrivateForm - Database Models
# =============================================================================
# SQLAlchemy models for all application entities.
# =============================================================================

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey,
    Text, JSON, func
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def generate_slug() -> str:
    """Generates a 6-character alphanumeric slug."""
    import secrets
    import string
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(6))


# -----------------------------------------------------------------------------
# Model: Doctor
# -----------------------------------------------------------------------------
class Doctor(Base):
    __tablename__ = "doctors"

    id: str = Column(String, primary_key=True, default=generate_uuid)
    email: str = Column(String, unique=True, nullable=False, index=True)
    password_hash: str = Column(String, nullable=False)
    pdf_encryption_password: str = Column(String, nullable=False)  # In plain text
    last_name: str = Column(String, nullable=False)                # Last name
    first_name: str = Column(String, nullable=False)               # First name
    specialty: str = Column(String, nullable=True)
    phone: str = Column(String, nullable=True)
    country: str = Column(String, nullable=True)
    newsletter: bool = Column(Boolean, default=False)
    is_verified: bool = Column(Boolean, default=False)
    form_limit: int = Column(Integer, default=10)                  # Configurable per doctor

    # Timestamps
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: datetime = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    forms = relationship("Form", back_populates="doctor", cascade="all, delete-orphan")
    verification_tokens = relationship("VerificationToken", back_populates="doctor", cascade="all, delete-orphan")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="doctor", cascade="all, delete-orphan")


# -----------------------------------------------------------------------------
# Model: Form
# -----------------------------------------------------------------------------
class Form(Base):
    __tablename__ = "forms"

    id: str = Column(String, primary_key=True, default=generate_uuid)
    doctor_id: str = Column(String, ForeignKey("doctors.id"), nullable=False)
    name: str = Column(String, nullable=False)
    slug: str = Column(String, unique=True, nullable=False, default=generate_slug, index=True)
    is_active: bool = Column(Boolean, default=False)
    is_example: bool = Column(Boolean, default=False)    # Example form (not deletable)
    submission_count: int = Column(Integer, default=0)   # Perpetual historical counter

    # Timestamps
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: datetime = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    doctor = relationship("Doctor", back_populates="forms")
    questions = relationship("Question", back_populates="form", cascade="all, delete-orphan", order_by="Question.order")


# -----------------------------------------------------------------------------
# Model: Question (question on a form)
# -----------------------------------------------------------------------------
class Question(Base):
    __tablename__ = "questions"

    id: str = Column(String, primary_key=True, default=generate_uuid)
    form_id: str = Column(String, ForeignKey("forms.id"), nullable=False)
    text: str = Column(Text, nullable=False)                        # Question text
    question_type: str = Column(String, nullable=False)             # Type of response
    is_required: bool = Column(Boolean, default=True)               # Required by default
    order: int = Column(Integer, nullable=False)                    # Order in the form

    # Conditional fields by type
    options: list = Column(JSON, nullable=True)                     # Select/Multiselect: list of options
    allow_decimals: bool = Column(Boolean, nullable=True)           # Number: allow decimals
    scale_label_1: str = Column(String, nullable=True)              # Scale: label for 1
    scale_label_10: str = Column(String, nullable=True)             # Scale: label for 10

    # Relationship
    form = relationship("Form", back_populates="questions")


# -----------------------------------------------------------------------------
# Model: VerificationToken (email verification token)
# -----------------------------------------------------------------------------
class VerificationToken(Base):
    __tablename__ = "verification_tokens"

    id: str = Column(String, primary_key=True, default=generate_uuid)
    doctor_id: str = Column(String, ForeignKey("doctors.id"), nullable=False)
    token: str = Column(String, unique=True, nullable=False, index=True)
    is_used: bool = Column(Boolean, default=False)
    expires_at: datetime = Column(DateTime(timezone=True), nullable=False)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    doctor = relationship("Doctor", back_populates="verification_tokens")


# -----------------------------------------------------------------------------
# Model: PasswordResetToken (password recovery token)
# -----------------------------------------------------------------------------
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: str = Column(String, primary_key=True, default=generate_uuid)
    doctor_id: str = Column(String, ForeignKey("doctors.id"), nullable=False)
    token: str = Column(String, unique=True, nullable=False, index=True)
    is_used: bool = Column(Boolean, default=False)
    expires_at: datetime = Column(DateTime(timezone=True), nullable=False)
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    doctor = relationship("Doctor", back_populates="password_reset_tokens")


# -----------------------------------------------------------------------------
# Constants: Valid question types
# -----------------------------------------------------------------------------
VALID_QUESTION_TYPES = [
    "text",           # Texto
    "text_long",      # Texto largo
    "yes_no",         # Oui/Non
    "select",         # Select (single selection)
    "multiselect",    # Multiselect (multiple selection)
    "date",           # Fecha
    "number",         # Number
    "email",          # Email
    "phone",          # Phone
    "scale",          # Scale 1-10
]

# -----------------------------------------------------------------------------
# Constants: Medical specialties
# -----------------------------------------------------------------------------
MEDICAL_SPECIALTIES = [
    "Allergologie",
    "Anatomie-pathologique",
    "Anesthésie-réanimation",
    "Biologie clinique",
    "Cardiologie et angiologie",
    "Chirurgie cardio-vasculaire",
    "Chirurgie dentaire, orale et maxillo-faciale",
    "Chirurgie des vaisseaux",
    "Chirurgie gastro-entérologique",
    "Chirurgie générale",
    "Chirurgie pédiatrique",
    "Chirurgie plastique",
    "Chirurgie thoracique",
    "Chirurgie vasculaire",
    "Dermato-vénéréologie",
    "Electroradiologie",
    "Endocrinologie",
    "Gastro-entérologie",
    "Gériatrie",
    "Gynécologie-obstétrique",
    "Hématologie",
    "Maladies contagieuses",
    "Médecine d'urgence",
    "Médecine dentaire",
    "Médecine du travail",
    "Médecine générale",
    "Médecine génétique",
    "Médecine interne",
    "Médecine légale",
    "Médecine nucléaire",
    "Médecine physique et réadaptation",
    "Microbiologie-bactérologie",
    "Néphrologie",
    "Neurochirurgie",
    "Neurologie",
    "Neuropathologie",
    "Neuropsychiatrie",
    "Oncologie médicale",
    "Ophtalmologie",
    "Orthopédie",
    "Oto-rhino-laryngologie",
    "Pédiatrie",
    "Pneumologie",
    "Psychiatrie",
    "Psychiatrie infantile",
    "Psychothérapie",
    "Radiodiagnostic",
    "Radiologie",
    "Radiothérapie",
    "Rééducation et réadaptation fonctionnelles",
    "Rhumatologie",
    "Santé publique et médecine sociale",
    "Stomatologie",
    "Traumatologie et Médecine d'Urgence",
    "Urologie",
    "Autre",
]

# -----------------------------------------------------------------------------
# Constants: Available countries
# -----------------------------------------------------------------------------
AVAILABLE_COUNTRIES = [
    ("Luxembourg", "Luxembourg"),
    ("Allemagne", "Allemagne"),
    ("Belgique", "Belgique"),
    ("France", "France"),
]
