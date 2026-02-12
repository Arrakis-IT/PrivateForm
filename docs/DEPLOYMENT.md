# DEPLOYMENT.md — PrivateForm Deployment Guide

> 💡 **Quick option:** If you prefer, there's an automated script in `scripts/deploy.sh` that handles most of the steps. See end of this guide.

## Server Prerequisites

- Ubuntu 22.04+ (VPS)
- Docker installed and running
- PostgreSQL installed (test DB `mediform_db_srv` must be removed — see step 1)
- RustDesk running in container (no conflict: PrivateForm uses ports 80/443)
- Domain pointing to server IP (for Let's Encrypt)

---

## STEP 0: Remove Test Database

Connect via SSH to server:

```bash
ssh root@45.80.209.148
```

Connect to PostgreSQL and remove test DB:

```bash
sudo -u postgres psql
```

```sql
-- Check there are no active connections
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'mediform_db_srv';

-- Drop the database
DROP DATABASE mediform_db_srv;

-- Drop the user (if not needed for other purposes)
DROP USER mediform_user;

\q
```

> ⚠️ Verify before DROP that nobody else is using this DB.

---

## STEP 1: Prepare Credentials

### PostgreSQL Credentials (new DB for PrivateForm)

The new DB will be created automatically with Docker Compose. You only need to choose a password:

```
DB_USER:     privateform_user
DB_PASSWORD: [NOTE HERE]  ← You decide when creating secrets/db_password.txt
```

### PostgreSQL Password for `mediform_user` (for DROP)

If you need the old user password to connect and do DROP:

```
Old user:     mediform_user
Password:     _______________  ← NOTE CURRENT PASSWORD HERE
```

> 📝 **This field is pending for you to fill.** If you don't remember the password, you can reset it from the `postgres` user:
> ```sql
> ALTER USER mediform_user WITH PASSWORD 'new_temp_password';
> ```

---

## STEP 2: Clone Project to Server

```bash
cd /opt
git clone <repository_url> privateform
cd privateform
```

---

## STEP 3: Create `.env` File

```bash
cp .env.example .env
nano .env
```

Fill in the fields. Fields marked with `[SECRET]` must also go in `secrets/` files.

**Main fields to configure:**

| Field | Value |
|---|---|
| `APP_DOMAIN` | Your domain (e.g., `privateform.arrakis.lu`) |
| `APP_DEBUG` | `False` in production |
| `APP_LOG_LEVEL` | `INFO` |

---

## STEP 4: Create Secret Files

```bash
mkdir -p secrets
```

Create each file (without trailing newline):

```bash
# New PostgreSQL DB password
printf 'your_db_password' > secrets/db_password.txt

# JWT secret (generate a random one)
printf 'your_long_random_jwt_secret' > secrets/jwt_secret.txt

# App secret key
printf 'your_random_app_secret_key' > secrets/app_secret_key.txt

# Brevo API key
printf 'your_brevo_api_key' > secrets/brevo_api_key.txt

# hCaptcha (see STEP 6)
printf 'your_hcaptcha_site_key' > secrets/hcaptcha_site_key.txt
printf 'your_hcaptcha_secret_key' > secrets/hcaptcha_secret_key.txt
```

> 🔒 Recommended permissions:
> ```bash
> chmod 600 secrets/*.txt
> ```

---

## STEP 5: Upload Static Assets

```bash
# Logo (PNG with transparent background) — for PDF watermark and web
cp /local/path/logo.png app/static/img/logo.png

# Favicon (can be the same logo or a specific one)
cp /local/path/favicon.png app/static/img/favicon.png
```

---

## STEP 6: Register hCaptcha (optional — can be added later)

hCaptcha is **not mandatory for first deployment**. The system automatically detects if credentials are configured and disables captcha if they're not. This allows testing the application without waiting.

**To add hCaptcha when ready:**

1. Go to https://www.hcaptcha.com
2. Create free account
3. In dashboard, add your domain (e.g., `privateform.arrakis.lu`)
4. Copy the **Site Key** and **Secret Key**
5. Update the files:
   ```bash
   printf 'your_real_site_key' > secrets/hcaptcha_site_key.txt
   printf 'your_real_secret_key' > secrets/hcaptcha_secret_key.txt
   chmod 600 secrets/hcaptcha_*.txt
   ```
6. Restart app:
   ```bash
   docker compose restart app
   ```

> If secret files contain the placeholder value (`your_hcaptcha_site_key_here`), captcha is automatically disabled in both frontend and backend verification.

---

## STEP 7: SSL with Let's Encrypt

Install certbot on server (if not already installed):

```bash
apt update && apt install -y certbot
```

Get certificate **before** starting Docker (so Nginx can read it):

```bash
certbot certonly --standalone -d privateform.arrakis.lu
```

> Certificate is saved in `/etc/letsencrypt/live/privateform.arrakis.lu/`

Configure auto-renewal:

```bash
crontab -e
# Add:
0 3 * * * certbot renew --quiet && docker compose -f /opt/privateform/docker-compose.yml restart nginx
```

---

## STEP 8: Adjust nginx/privateform.conf

Edit `/opt/privateform/nginx/privateform.conf` and replace:
- `privateform.arrakis.lu` → your real domain
- Certificate paths if necessary

---

## STEP 9: Build and Deploy

```bash
cd /opt/privateform

# Build app image
docker compose build

# Start containers in background
docker compose up -d
```

Verify status:

```bash
docker compose ps
# All should be "running"
```

---

## STEP 10: Run Database Migration

```bash
docker compose exec app alembic upgrade head
```

Verify:

```bash
docker compose exec app alembic current
# Should show: 0001_initial (head)
```

---

## STEP 11: Verification

1. Open `https://privateform.arrakis.lu` → should show landing page
2. Register a test doctor
3. Verify confirmation email
4. Login → should see example form
5. Create a form, activate it, share via QR
6. From another device/browser, open QR → fill and submit
7. Verify doctor receives email with encrypted PDF

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Nginx 502 | `docker compose logs app` — verify app is running |
| SSL error | Verify certbot generated certificate correctly |
| DB connection error | Verify `secrets/db_password.txt` matches password in `.env` |
| Email not sent | Verify Brevo API key and domain is verified in Brevo |
| hCaptcha not showing | Verify site key in secrets is correct and domain is allowed in hCaptcha |
| Alembic error | `docker compose exec app alembic heads` — verify no multiple heads |

---

## Coexistence with RustDesk

RustDesk and PrivateForm coexist without conflicts:
- PrivateForm uses ports **80** (HTTP→redirect) and **443** (HTTPS) via Nginx
- RustDesk uses its own ports (verify it's not using 80/443)
- They're on different Docker networks by default

If there's a conflict on ports 80/443, verify with:
```bash
ss -tlnp | grep -E '80|443'
```

---

## Security Notes

- `secrets/` files are never uploaded to Git (included in `.gitignore`)
- `.env` is also in `.gitignore`
- PostgreSQL doesn't expose ports externally (only internal Docker network)
- UFW: allow only ports 22, 80, 443
- Fail2ban recommended for SSH

---

## Automated Deploy with Script

As an alternative to manual steps, there's a script that automates most of it:

```bash
# 1. Connect to server
ssh root@45.80.209.148

# 2. Navigate to project (assuming it's already in /opt/privateform)
cd /opt/privateform

# 3. Create manual secrets BEFORE running the script:
mkdir -p secrets
printf 'your_new_db_password' > secrets/db_password.txt
printf 'your_brevo_api_key' > secrets/brevo_api_key.txt
chmod 600 secrets/*.txt

# 4. Run the script
bash scripts/deploy.sh
```

The script automatically does:
- Remove old DB `mediform_db_srv`
- Generate security secrets (JWT, App Key)
- Create hCaptcha placeholders (if they don't exist)
- Verify ports and configuration
- Docker build
- Deploy containers
- Wait for PostgreSQL to be ready
- Run Alembic migration

**After the script**, you still need to manually:
1. Configure `APP_DOMAIN` in `.env` with your real domain
2. Get SSL certificate with `certbot`
3. Uncomment HTTPS block in `nginx/privateform.conf`
4. Restart nginx: `docker compose restart nginx`
5. Upload your real PNG logo
