"""Add question_limit to doctors, fix form_limit default to 5

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add question_limit column (default 10)
    op.add_column('doctors', sa.Column('question_limit', sa.Integer(), nullable=False, server_default='10'))

    # Fix form_limit default from 10 to 5 for new rows
    op.alter_column('doctors', 'form_limit', server_default='5')


def downgrade() -> None:
    op.drop_column('doctors', 'question_limit')
    op.alter_column('doctors', 'form_limit', server_default='10')
