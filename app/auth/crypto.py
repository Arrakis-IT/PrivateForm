# =============================================================================
# PrivateForm - PDF Password Encryption
# =============================================================================
# Symmetric encryption for PDF passwords using Fernet (AES-128-CBC + HMAC-SHA256).
# The master key is loaded from Docker secrets.
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

from cryptography.fernet import Fernet, InvalidToken
from app.core.settings import settings


def _get_fernet() -> Fernet:
    key = settings.PDF_MASTER_KEY
    if not key:
        raise RuntimeError("PDF_MASTER_KEY is not configured")
    return Fernet(key.encode())


def encrypt_pdf_password(plain_password: str) -> str:
    """Encrypts a PDF password using the server master key."""
    return _get_fernet().encrypt(plain_password.encode()).decode()


def decrypt_pdf_password(encrypted_password: str) -> str:
    """
    Decrypts a PDF password using the server master key.
    Raises ValueError if the ciphertext is invalid or corrupted.
    """
    try:
        return _get_fernet().decrypt(encrypted_password.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Invalid or corrupted PDF password ciphertext") from e