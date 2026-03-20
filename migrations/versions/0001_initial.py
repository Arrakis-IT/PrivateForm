# =============================================================================
# PrivateForm - Initial migration
# =============================================================================
# Create all tables: doctors, forms, questions,
# verification_tokens, password_reset_tokens.
# =============================================================================

from alembic import op
import sqlalchemy as sa

# revision
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # Table: doctors
    # -------------------------------------------------------------------------
    op.create_table(
        "doctors",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("pdf_encryption_password", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("specialty", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("newsletter", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("is_verified", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("form_limit", sa.Integer(), nullable=True, server_default=sa.text("10")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_doctors_email"), "doctors", ["email"], unique=True)

    # -------------------------------------------------------------------------
    # Table: forms
    # -------------------------------------------------------------------------
    op.create_table(
        "forms",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("doctor_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("is_example", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("submission_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_forms_slug"), "forms", ["slug"], unique=True)

    # -------------------------------------------------------------------------
    # Table: questions
    # -------------------------------------------------------------------------
    op.create_table(
        "questions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("form_id", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("question_type", sa.String(), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("allow_decimals", sa.Boolean(), nullable=True),
        sa.Column("scale_label_1", sa.String(), nullable=True),
        sa.Column("scale_label_10", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["form_id"], ["forms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # Table: verification_tokens
    # -------------------------------------------------------------------------
    op.create_table(
        "verification_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("doctor_id", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_verification_tokens_token"), "verification_tokens", ["token"], unique=True)

    # -------------------------------------------------------------------------
    # Table: password_reset_tokens
    # -------------------------------------------------------------------------
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("doctor_id", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_password_reset_tokens_token"), "password_reset_tokens", ["token"], unique=True)


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_table("verification_tokens")
    op.drop_table("questions")
    op.drop_table("forms")
    op.drop_table("doctors")
