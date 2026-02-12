# =============================================================================
# PrivateForm - Main Application Entry Point
# =============================================================================
# Instancia de FastAPI, middlewares, routers y evento de inicio.
# =============================================================================

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from app.core.settings import settings
from app.core.logging import get_logger

logger = get_logger("main")


# -----------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup event: creates tables if they don't exist (development)."""
    if settings.APP_DEBUG:
        from app.core.database import Base, engine
        Base.metadata.create_all(bind=engine)
        logger.info("Tables created (development mode).")
    yield
    logger.info("Application closed.")


# -----------------------------------------------------------------------------
# App creation
# -----------------------------------------------------------------------------
app = FastAPI(
    title="PrivateForm",
    description="Formulaires médicaux sécurisés et privés",
    docs_url=None,           # Disable docs in production
    redoc_url=None,
    lifespan=lifespan,
)


# -----------------------------------------------------------------------------
# Static files
# -----------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# -----------------------------------------------------------------------------
# Routers
# -----------------------------------------------------------------------------
from app.auth.routes import router as auth_router
from app.forms.routes import router as forms_router
from app.users.routes import router as users_router
from app.patient.routes import router as patient_router

app.include_router(auth_router)
app.include_router(forms_router, prefix="/doctor")
app.include_router(users_router, prefix="/doctor")
app.include_router(patient_router)


# -----------------------------------------------------------------------------
# 404 global
# -----------------------------------------------------------------------------
templates = Jinja2Templates(directory="app/templates")

@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse(
        request, "errors/404.html", {}, status_code=404
    )
