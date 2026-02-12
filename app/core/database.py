# =============================================================================
# PrivateForm - Database Connection
# =============================================================================
# SQLAlchemy engine, session factory, declarative base.
# =============================================================================

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.settings import settings


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""
    pass


# SQLAlchemy Engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,          # Verify connection before using
    pool_size=5,                 # Connection pool size
    max_overflow=10,             # Extra connections if pool is full
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    FastAPI dependency to get a DB session.
    Automatically closed when request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
