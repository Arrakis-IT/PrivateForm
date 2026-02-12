# =============================================================================
# PrivateForm - Logging
# =============================================================================
# Logging system configurable by level.
# Automatic daily rotation, 30-day retention.
# =============================================================================

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from app.core.settings import settings

LOG_DIR = Path("/app/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Log format: Timestamp, level, module, message
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger configured according to APP_LOG_LEVEL.
    - Levels: DEBUG, INFO, WARNING, ERROR
    - File: logs/privateform.log with daily rotation
    - Console: always active (stdout)
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    # Level according to configuration
    level = getattr(logging, settings.APP_LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # --- Handler: Console (stdout) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # --- Handler: File with daily rotation ---
    file_handler = TimedRotatingFileHandler(
        filename=LOG_DIR / "privateform.log",
        when="midnight",           # Rotation at midnight
        interval=1,                # Every 1 day
        backupCount=settings.LOG_RETENTION_DAYS,  # Retention 30 days
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Avoid propagation to root logger (avoids duplicate logs)
    logger.propagate = False

    return logger


# Main application logger
app_logger = get_logger("privateform")
