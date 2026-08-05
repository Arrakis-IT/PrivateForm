# =============================================================================
# PrivateForm - Dockerfile
# =============================================================================
# Base image: Python 3.12 slim
# Multi-stage build to optimize final image size
# =============================================================================

# --- Stage 0: Build Tailwind CSS ---
FROM alpine:3.19 AS tailwind-builder

ADD --chmod=755 https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.1/tailwindcss-linux-x64 /usr/local/bin/tailwindcss

WORKDIR /build
COPY tailwind.config.js tailwind.input.css ./
COPY app/templates/ ./app/templates/

RUN tailwindcss -c tailwind.config.js -i tailwind.input.css -o app/static/css/tailwind.min.css --minify


# --- Stage 1: Install dependencies ---
FROM python:3.12-slim AS builder

# Install system dependencies needed to build Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libpq-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files
WORKDIR /app
COPY requirements.txt requirements.lock ./

# Update pip itself before installing dependencies
RUN pip install --no-cache-dir --only-binary :all: pip==26.2.1

# Install pinned dependencies from lockfile (BuildKit cache avoids re-downloading on cache miss)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --only-binary :all: --require-hashes -r requirements.lock

# --- Stage 2: Final production image ---
FROM python:3.12-slim

# Install runtime dependencies + Unicode fonts, upgrade pip
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --only-binary :all: pip==26.2.1

# Copy installed dependencies from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/alembic /usr/local/bin/alembic

WORKDIR /app

# Copy app code
COPY app/ ./app/

# Inject Tailwind CSS built in stage 0
COPY --from=tailwind-builder /build/app/static/css/tailwind.min.css ./app/static/css/tailwind.min.css
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# Create logs directory, non-root user, and set ownership
RUN mkdir -p /app/logs && chmod 750 /app/logs \
    && groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Entrypoint: run migrations + uvicorn
ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]