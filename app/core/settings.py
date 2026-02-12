# =============================================================================
# PrivateForm - Core Settings
# =============================================================================
# Centralized configuration. Reads environment variables and Docker secrets.
# =============================================================================

import os
from pathlib import Path
from pydantic_settings import BaseSettings


def read_secret(secret_file_env: str, fallback_env: str) -> str:
    """
    Reads a secret from a Docker secret file.
    If it doesn't exist, falls back to the direct environment variable value.
    """
    file_path = os.getenv(secret_file_env)
    if file_path and Path(file_path).exists():
        return Path(file_path).read_text().strip()
    return os.getenv(fallback_env, "")


class Settings(BaseSettings):
    # -----------------------------------------------------------------------
    # Application
    # -----------------------------------------------------------------------
    APP_NAME: str = "PrivateForm"
    APP_DEBUG: bool = False
    APP_LOG_LEVEL: str = "INFO"
    APP_DOMAIN: str = "localhost"

    # -----------------------------------------------------------------------
    # Base de datos
    # -----------------------------------------------------------------------
    DB_HOST: str = "db"
    DB_PORT: int = 5432
    DB_NAME: str = "privateform_db"
    DB_USER: str = "privateform_user"

    # -----------------------------------------------------------------------
    # JWT
    # -----------------------------------------------------------------------
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 120

    # -----------------------------------------------------------------------
    # Brevo
    # -----------------------------------------------------------------------
    BREVO_SENDER_EMAIL: str = "privateform@arrakis.lu"
    BREVO_SENDER_NAME: str = "PrivateForm"
    BREVO_REPLY_TO: str = "privateform@arrakis.lu"

    # -----------------------------------------------------------------------
    # Contacto
    # -----------------------------------------------------------------------
    CONTACT_EMAIL: str = "privateform@arrakis.lu"
    CONTACT_PHONE: str = "691 292 193"
    CONTACT_WEB: str = "www.arrakis.lu"

    # -----------------------------------------------------------------------
    # Alertas
    # -----------------------------------------------------------------------
    ALERT_EMAIL: str = "privateform@arrakis.lu"
    ALERT_MAX_PER_HOUR: int = 10

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------
    LOG_RETENTION_DAYS: int = 30

    # -----------------------------------------------------------------------
    # Limits
    # -----------------------------------------------------------------------
    DEFAULT_FORM_LIMIT: int = 10
    MAX_QUESTIONS_PER_FORM: int = 50
    MAX_OPTIONS_PER_QUESTION: int = 10
    MAX_LONG_TEXT_CHARS: int = 5000
    MAX_SUBMISSION_SIZE_KB: int = 1024

    # -----------------------------------------------------------------------
    # Rate Limiting
    # -----------------------------------------------------------------------
    PATIENT_SUBMISSIONS_PER_HOUR: int = 2
    PASSWORD_RESET_ATTEMPTS_PER_HOUR: int = 3
    VERIFICATION_RESEND_PER_DAY: int = 3

    # -----------------------------------------------------------------------
    # Properties that read secrets
    # -----------------------------------------------------------------------
    @property
    def DB_PASSWORD(self) -> str:
        return read_secret("DB_PASSWORD_FILE", "DB_PASSWORD")

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def JWT_SECRET(self) -> str:
        return read_secret("JWT_SECRET_FILE", "JWT_SECRET")

    @property
    def APP_SECRET_KEY(self) -> str:
        return read_secret("APP_SECRET_KEY_FILE", "APP_SECRET_KEY")

    @property
    def BREVO_API_KEY(self) -> str:
        return read_secret("BREVO_API_KEY_FILE", "BREVO_API_KEY")

    @property
    def HCAPTCHA_SITE_KEY(self) -> str:
        return read_secret("HCAPTCHA_SITE_KEY_FILE", "HCAPTCHA_SITE_KEY")

    @property
    def HCAPTCHA_SECRET_KEY(self) -> str:
        return read_secret("HCAPTCHA_SECRET_KEY_FILE", "HCAPTCHA_SECRET_KEY")

    model_config = {"env_file": ".env", "extra": "ignore"}


# Global instance (singleton)
settings = Settings()
