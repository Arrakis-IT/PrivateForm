# =============================================================================
# PrivateForm - Alembic env.py
# =============================================================================
# Migration environment configuration.
# Import the models so that Alembic can detect changes (autogenerate).
# # =============================================================================

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
import os
from logging.config import fileConfig
from sqlalchemy import create_engine, engine_from_config, pool
from alembic import context

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.settings import settings
from app.core.database import Base

# Import all models for autogenerate
from app.core import models  # noqa: F401

# Logging configuration from alembic.ini
config = context.config
if config.file_config:
    fileConfig(config.file_config, disable_existing_loggers=False)

# URL of the database from settings
target_metadata = Base.metadata


def get_database_url() -> str:
    """Constructs the PostgreSQL URL from environment variables."""
    return (
        f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )


def run_migrations_offline():
    """Constructs the PostgreSQL URL from environment variables."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Perform migrations in online mode (while connected to the database)."""
    connectable = create_engine(
        get_database_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
