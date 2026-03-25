# =============================================================================
# PrivateForm - Main Application Entry Point
# =============================================================================
# Instance of FastAPI, middlewares, routers and startup event.
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

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from app.core.settings import settings
from app.core.logging import get_logger
from starlette.middleware.base import BaseHTTPMiddleware


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
# Middlewares
# -----------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds HTTP security headers to every response.
    Protects against clickjacking, MIME sniffing, XSS, and session hijacking.
    CSP uses 'unsafe-inline' for scripts because templates use inline JS.
    Removing 'unsafe-inline' requires migrating to nonce-based CSP (future work).
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://js.hcaptcha.com https://hcaptcha.com; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://newassets.hcaptcha.com; "
            "font-src 'self' https://cdnjs.cloudflare.com; "
            "img-src 'self' data: https://newassets.hcaptcha.com; "
            "frame-src https://newassets.hcaptcha.com; "
            "connect-src 'self' https://hcaptcha.com https://newassets.hcaptcha.com; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none';"
        )
        return response


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
# Middleware registration
# -----------------------------------------------------------------------------
app.add_middleware(SecurityHeadersMiddleware)

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
from app.admin.routes import router as admin_router

app.include_router(auth_router)
app.include_router(forms_router, prefix="/doctor")
app.include_router(users_router, prefix="/doctor")
app.include_router(patient_router)
app.include_router(admin_router)


# -----------------------------------------------------------------------------
# SEO — robots.txt & sitemap.xml
# -----------------------------------------------------------------------------
@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    content = (
        "User-agent: *\n"
        "Disallow: /doctor/\n"
        "Disallow: /f/\n"
        "\n"
        f"Sitemap: https://{settings.APP_DOMAIN}/sitemap.xml\n"
    )
    return PlainTextResponse(content)


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml():
    base = f"https://{settings.APP_DOMAIN}"
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{base}/</loc><changefreq>monthly</changefreq><priority>1.0</priority></url>
  <url><loc>{base}/login</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>
  <url><loc>{base}/register</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>
</urlset>"""
    return PlainTextResponse(content, media_type="application/xml")


# -----------------------------------------------------------------------------
# 404 global
# -----------------------------------------------------------------------------
templates = Jinja2Templates(directory="app/templates")

@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse(
        request, "errors/404.html", {}, status_code=404
    )
