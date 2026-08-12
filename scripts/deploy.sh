#!/bin/bash
# =============================================================================
# PrivateForm - Deployment Script
# =============================================================================
# Run as root from the server:
#   bash /opt/privateform/scripts/deploy.sh
#
# This script does NOT handle:
#   - The mediform_user password (manual step 0)
#   - Brevo credentials (manual step)
#   - SSL certificate (manual step with certbot)
#   - PNG logo (manual step)
# =============================================================================

set -e

SEPARATOR="=============================================="

DEPLOY_DIR="/opt/privateform"
SECRETS_DIR="${DEPLOY_DIR}/secrets"

echo "$SEPARATOR"
echo "  PrivateForm — Deploy"
echo "$SEPARATOR"
echo ""

# ---------------------------------------------------------------
# STEP 0: Remove old database (if exists)
# ---------------------------------------------------------------
echo "[STEP 0] Checking old database..."
sudo -u postgres psql -c "SELECT 1 FROM pg_database WHERE datname = 'mediform_db_srv';" 2>/dev/null && {
    echo "  → Database 'mediform_db_srv' found."
    echo "  → Terminating active connections..."
    sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'mediform_db_srv';"
    echo "  → Deleting database..."
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS mediform_db_srv;"
    echo "  ✓ Database deleted."
} || echo "  → Database 'mediform_db_srv' not found (already deleted or never existed)."

echo ""

# ---------------------------------------------------------------
# STEP 1: Create secrets directory
# ---------------------------------------------------------------
echo "[STEP 1] Preparing secrets directory..."
mkdir -p "${SECRETS_DIR}"
chmod 700 "${SECRETS_DIR}"
echo "  ✓ ${SECRETS_DIR} ready."
echo ""

# ---------------------------------------------------------------
# STEP 2: Generate automatic secrets (JWT, App Key)
# ---------------------------------------------------------------
echo "[STEP 2] Generating automatic secrets..."

if [[ ! -f "${SECRETS_DIR}/jwt_secret.txt" ]]; then
    openssl rand -base64 48 | tr -d '\n' > "${SECRETS_DIR}/jwt_secret.txt"
    echo "  ✓ jwt_secret.txt generated."
else
    echo "  → jwt_secret.txt already exists (not overwriting)."
fi

if [[ ! -f "${SECRETS_DIR}/app_secret_key.txt" ]]; then
    openssl rand -base64 48 | tr -d '\n' > "${SECRETS_DIR}/app_secret_key.txt"
    echo "  ✓ app_secret_key.txt generated."
else
    echo "  → app_secret_key.txt already exists (not overwriting)."
fi

# 644: directory is 700 so only root can browse it, but Docker (root) mounts
# the files inside the container — appuser needs read access inside the container.
chmod 644 "${SECRETS_DIR}"/*.txt 2>/dev/null || true
echo ""

# ---------------------------------------------------------------
# STEP 3: Verify manual secrets
# ---------------------------------------------------------------
echo "[STEP 3] Verifying manual secrets..."
MISSING=0

for secret in db_password brevo_api_key; do
    if [[ ! -f "${SECRETS_DIR}/${secret}.txt" ]]; then
        echo "  ⚠ MISSING: ${SECRETS_DIR}/${secret}.txt"
        MISSING=1
    else
        echo "  ✓ ${secret}.txt exists."
    fi
done

# hCaptcha is optional
for secret in hcaptcha_site_key hcaptcha_secret_key; do
    if [[ ! -f "${SECRETS_DIR}/${secret}.txt" ]]; then
        echo "  ℹ ${secret}.txt doesn't exist → hCaptcha disabled (OK for now)."
        # Create with placeholder value so Docker doesn't fail
        printf 'your_hcaptcha_site_key_here' > "${SECRETS_DIR}/${secret}.txt"
        chmod 600 "${SECRETS_DIR}/${secret}.txt"
    else
        echo "  ✓ ${secret}.txt exists."
    fi
done

if [[ $MISSING -eq 1 ]]; then
    echo ""
    echo "  ⛔ STOP: Create missing secrets and run again."
    echo ""
    echo "     Example:"
    echo "       printf 'your_db_password' > ${SECRETS_DIR}/db_password.txt"
    echo "       printf 'your_brevo_api_key' > ${SECRETS_DIR}/brevo_api_key.txt"
    echo "       chmod 600 ${SECRETS_DIR}/*.txt"
    exit 1
fi

echo ""

# ---------------------------------------------------------------
# STEP 4: Verify .env
# ---------------------------------------------------------------
echo "[STEP 4] Verifying .env..."
if [[ ! -f "${DEPLOY_DIR}/.env" ]]; then
    if [[ -f "${DEPLOY_DIR}/.env.example" ]]; then
        cp "${DEPLOY_DIR}/.env.example" "${DEPLOY_DIR}/.env"
        echo "  ⚠ .env created from .env.example."
        echo "  → Review and edit ${DEPLOY_DIR}/.env (especially APP_DOMAIN)."
    else
        echo "  ⛔ .env.example not found."
        exit 1
    fi
else
    echo "  ✓ .env exists."
fi
echo ""

# ---------------------------------------------------------------
# STEP 5: Verify PNG logo
# ---------------------------------------------------------------
echo "[STEP 5] Verifying logo..."
LOGO_SIZE=$(stat -c%s "${DEPLOY_DIR}/app/static/img/logo.png" 2>/dev/null || echo 0)
if [[ "$LOGO_SIZE" -lt 100 ]]; then
    echo "  ⚠ Logo is a placeholder (${LOGO_SIZE} bytes)."
    echo "  → Copy your real logo:"
    echo "      cp /path/to/your/logo.png ${DEPLOY_DIR}/app/static/img/logo.png"
else
    echo "  ✓ Logo OK (${LOGO_SIZE} bytes)."
fi
echo ""

# ---------------------------------------------------------------
# STEP 6: Docker build
# ---------------------------------------------------------------
echo "[STEP 6] Docker build..."
cd "${DEPLOY_DIR}"

docker compose -f docker-compose.yml build 2>&1
echo "  ✓ Build completed."
echo ""

# ---------------------------------------------------------------
# STEP 7: Deploy
# ---------------------------------------------------------------
echo "[STEP 7] Starting containers..."
docker compose -f docker-compose.yml up -d
echo ""

# Wait for database to be ready
echo "  → Waiting for PostgreSQL to be ready..."
for i in $(seq 1 30); do
    if docker compose -f docker-compose.yml exec db pg_isready -U privateform_user -d privateform_db >/dev/null 2>&1; then
        echo "  ✓ PostgreSQL ready."
        break
    fi
    echo "  . (attempt ${i}/30)"
    sleep 2
done
echo ""

# ---------------------------------------------------------------
# STEP 8: Migration
# ---------------------------------------------------------------
echo "[STEP 8] Running Alembic migration..."
docker compose -f docker-compose.yml exec app alembic upgrade head
echo "  ✓ Migration completed."
echo ""

# ---------------------------------------------------------------
# Final status
# ---------------------------------------------------------------
echo "$SEPARATOR"
echo "  Container status:"
echo "$SEPARATOR"
docker compose -f docker-compose.yml ps
echo ""
echo "$SEPARATOR"
echo "  ✓ Deploy completed."
echo "$SEPARATOR"
echo ""
echo "Next steps (if first time):"
echo "  1. Verify APP_DOMAIN in .env matches your domain"
echo "  2. Make sure the external 'web' network exists (docker network create web)"
echo "  3. Point the shared host nginx to the privateform_app container on the 'web' network"
echo "  5. Upload your real logo: cp /path/logo.png app/static/img/logo.png"
echo "  6. If you want hCaptcha: create secrets and restart app"
