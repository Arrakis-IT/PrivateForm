# =============================================================================
# PrivateForm - Dockerfile
# =============================================================================
# Base image: Python 3.12 slim
# Multi-stage build to optimize final image size
# =============================================================================

# --- Stage 1: Install dependencies ---
FROM python:3.12-slim AS builder

# Install system dependencies needed to build Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
WORKDIR /app
COPY requirements.txt ./

# Install dependencies with pip
RUN pip install --no-cache-dir -r requirements.txt

# --- Stage 2: Final production image ---
FROM python:3.12-slim

# Install runtime dependencies + Unicode fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy installed dependencies from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/alembic /usr/local/bin/alembic

WORKDIR /app

# Copy app code
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# Create logs directory
RUN mkdir -p /app/logs && chmod 777 /app/logs

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Entrypoint: run migrations + uvicorn
ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]