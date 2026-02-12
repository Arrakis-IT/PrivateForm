# =============================================================================
# PrivateForm - Alembic env.py
# =============================================================================
# Migration environment configuration.
# Importa los modelos para que Alembic pueda detectar cambios (autogenerate).
# =============================================================================

import sys
import os
from logging.config import fileConfig
from sqlalchemy import create_engine, engine_from_config, pool
from alembic import context

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.settings import settings
from app.core.database import Base

# Importar todos los modelos para autogenerate
from app.core import models  # noqa: F401

# Logging configuration from alembic.ini
config = context.config
if config.file_config:
    fileConfig(config.file_config, disable_existing_loggers=False)

# URL de la base de datos desde settings
target_metadata = Base.metadata


def get_database_url() -> str:
    """Construye la URL de PostgreSQL desde las variables de entorno."""
    return (
        f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )


def run_migrations_offline():
    """Ejecuta migraciones en modo offline (genera SQL sin conectar)."""
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
    """Ejecuta migraciones en modo online (conectado a la BD)."""
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
