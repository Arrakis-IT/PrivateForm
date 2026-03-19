# =============================================================================
# PrivateForm - Email Service (Brevo)
# =============================================================================
# Email sending via Brevo API.
# Types: verification, recovery, password change confirmation,
#        form notification (with PDF attachment), critical alerts.
# =============================================================================

import base64
import httpx
from app.core.settings import settings
from app.core.logging import get_logger
from app.core.rate_limiter import check_alert_limit

logger = get_logger("email")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


async def _send_email_original(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    attachments: list[dict] | None = None,
) -> bool:
    """
    Base function to send email via Brevo API.
    Returns True if sent successfully, False if it fails.
    """
    headers = {
        "api-key": settings.BREVO_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "sender": {
            "name": settings.BREVO_SENDER_NAME,
            "email": settings.BREVO_SENDER_EMAIL,
        },
        "replyTo": {
            "email": settings.BREVO_REPLY_TO,
        },
        "to": [
            {
                "email": to_email,
                "name": to_name,
            }
        ],
        "subject": subject,
        "htmlContent": html_body,
    }

    if attachments:
        payload["attachment"] = attachments

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(BREVO_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

async def _send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    attachments: list[dict] | None = None,
) -> bool:
    """
    Base function to send email via Brevo API.
    Returns True if sent successfully, False if it fails.
    """
    logger.info(f"Attempting to send email to {to_email}, subject: {subject}")  # ← AÑADIR
    logger.info(f"Using API URL: {BREVO_API_URL}")  # ← AÑADIR
    logger.info(f"API Key starts with: {settings.BREVO_API_KEY[:20]}")  # ← AÑADIR
    
    headers = {
        "api-key": settings.BREVO_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "sender": {
            "name": settings.BREVO_SENDER_NAME,
            "email": settings.BREVO_SENDER_EMAIL,
        },
        "replyTo": {
            "email": settings.BREVO_REPLY_TO,
        },
        "to": [
            {
                "email": to_email,
                "name": to_name,
            }
        ],
        "subject": subject,
        "htmlContent": html_body,
    }

    if attachments:
        payload["attachment"] = attachments
    
    try:
        logger.info("Creating httpx client...")  # ← AÑADIR
        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info(f"Posting to {BREVO_API_URL}")  # ← AÑADIR
            response = await client.post(BREVO_API_URL, json=payload, headers=headers)
            logger.info(f"Got response: {response.status_code}")  # ← AÑADIR
            response.raise_for_status()
            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        logger.exception("Full traceback:")  # ← AÑADIR (muestra stack trace completo)
        return False

# =============================================================================
# Base HTML template for emails
# =============================================================================

def _email_base_template(content_html: str) -> str:
    """Generates the base HTML of the email with PrivateForm branding."""
    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PrivateForm</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background-color: #f3f4f6;
                margin: 0;
                padding: 20px;
                color: #1f2937;
            }}
            .container {{
                max-width: 580px;
                margin: 0 auto;
                background: #ffffff;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }}
            .header {{
                background: linear-gradient(135deg, #5FD4C4, #4B8FDB, #6B7FDB);
                padding: 32px;
                text-align: center;
            }}
            .header h1 {{
                color: #ffffff;
                margin: 0;
                font-size: 24px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            .content {{
                padding: 32px;
                line-height: 1.6;
            }}
            .content p {{
                margin-bottom: 16px;
                color: #374151;
            }}
            .btn {{
                display: inline-block;
                background: linear-gradient(135deg, #4B8FDB, #6B7FDB);
                color: #ffffff;
                text-decoration: none;
                padding: 14px 32px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 16px;
                margin: 16px 0;
            }}
            .btn-container {{
                text-align: center;
                margin: 24px 0;
            }}
            .url-box {{
                background: #f3f4f6;
                border-radius: 8px;
                padding: 12px 16px;
                margin: 16px 0;
                font-size: 13px;
                word-break: break-all;
                color: #6b7280;
            }}
            .warning {{
                background: #fef3c7;
                border-left: 4px solid #f59e0b;
                padding: 12px 16px;
                border-radius: 0 8px 8px 0;
                margin: 16px 0;
                font-size: 14px;
                color: #92400e;
            }}
            .info {{
                background: #eff6ff;
                border-left: 4px solid #3b82f6;
                padding: 12px 16px;
                border-radius: 0 8px 8px 0;
                margin: 16px 0;
                font-size: 14px;
                color: #1e40af;
            }}
            .footer {{
                padding: 24px 32px;
                border-top: 1px solid #e5e7eb;
                text-align: center;
                font-size: 13px;
                color: #9ca3af;
            }}
            .footer a {{
                color: #4B8FDB;
                text-decoration: none;
            }}
            .divider {{
                height: 1px;
                background: #e5e7eb;
                margin: 24px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>PrivateForm</h1>
            </div>
            <div class="content">
                {content_html}
            </div>
            <div class="footer">
                <p>PrivateForm - Formulaires médicaux sécurisés et privés</p>
                <p>
                    <a href="mailto:{settings.CONTACT_EMAIL}">{settings.CONTACT_EMAIL}</a> |
                    {settings.CONTACT_PHONE} |
                    <a href="https://{settings.CONTACT_WEB}">{settings.CONTACT_WEB}</a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """


# =============================================================================
# Email: Account verification
# =============================================================================

async def send_verification_email(to_email: str, doctor_name: str, verification_url: str) -> bool:
    """
    Sends the account verification email.
    Includes link, expiration (24h), alternative URL and non-recognition notice.
    """
    # Anti-spam tip
    anti_spam_note = f"""
    <div class="info">
        💡 Si cet email se retrouve dans votre dossier spam, ajoutez
        <strong>{settings.BREVO_SENDER_EMAIL}</strong> à vos contacts
        pour éviter ce problème à l'avenir.
    </div>
    """

    content = f"""
    <p>Bonjour <strong>{doctor_name}</strong>,</p>
    <p>Merci de vous être inscrit sur PrivateForm. Cliquez sur le bouton ci-dessous
    pour vérifier votre adresse email et activer votre compte.</p>

    <div class="btn-container">
        <a href="{verification_url}" class="btn">Vérifier mon email</a>
    </div>

    <p>Ce lien expirera dans <strong>24 heures</strong>.</p>

    <p>Si le bouton ci-dessus ne fonctionne pas, copiez et collez le lien suivant
    dans votre navigateur :</p>
    <div class="url-box">{verification_url}</div>

    {anti_spam_note}

    <div class="warning">
        Si vous n'avez pas créé de compte sur PrivateForm, ignorez cet email.
        Votre sécurité n'est pas compromise.
    </div>
    """

    return await _send_email(
        to_email=to_email,
        to_name=doctor_name,
        subject="Vérifiez votre compte PrivateForm",
        html_body=_email_base_template(content),
    )


# =============================================================================
# Email: Password recovery
# =============================================================================

async def send_password_reset_email(to_email: str, doctor_name: str, reset_url: str) -> bool:
    """
    Sends the password recovery email.
    """
    content = f"""
    <p>Bonjour <strong>{doctor_name}</strong>,</p>
    <p>Vous avez demandé la réinitialisation de votre mot de passe PrivateForm.
    Cliquez sur le bouton ci-dessous pour définir un nouveau mot de passe.</p>

    <div class="btn-container">
        <a href="{reset_url}" class="btn">Réinitialiser mon mot de passe</a>
    </div>

    <p>Ce lien expirera dans <strong>24 heures</strong>.</p>

    <p>Si le bouton ci-dessus ne fonctionne pas, copiez et collez le lien suivant
    dans votre navigateur :</p>
    <div class="url-box">{reset_url}</div>

    <div class="warning">
        Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.
        Votre mot de passe restera inchangé et votre compte reste sécurisé.
    </div>
    """

    return await _send_email(
        to_email=to_email,
        to_name=doctor_name,
        subject="Réinitialisation de votre mot de passe PrivateForm",
        html_body=_email_base_template(content),
    )


# =============================================================================
# Email: Password change confirmation
# =============================================================================

async def send_password_changed_email(to_email: str, doctor_name: str, change_timestamp: str) -> bool:
    """
    Sends notification that the password has been changed.
    Includes timestamp and security notice.
    """
    content = f"""
    <p>Bonjour <strong>{doctor_name}</strong>,</p>
    <p>Votre mot de passe PrivateForm a été modifié avec succès.</p>

    <div class="info">
        🕐 Modification effectuée le : <strong>{change_timestamp}</strong>
    </div>

    <p>Toutes les sessions actives ont été fermées par mesure de sécurité.
    Vous devrez vous reconnectez lors de votre prochaine visite.</p>

    <div class="warning">
        Si vous n'êtes pas à l'origine de ce changement, contactez-nous
        immédiatement à <strong>{settings.CONTACT_EMAIL}</strong>.
    </div>
    """

    return await _send_email(
        to_email=to_email,
        to_name=doctor_name,
        subject="Votre mot de passe a été modifié",
        html_body=_email_base_template(content),
    )


# =============================================================================
# Email: New form notification (with encrypted PDF)
# =============================================================================

async def send_form_submission_email(
    to_email: str,
    doctor_name: str,
    form_name: str,
    submission_timestamp: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> bool:
    """
    Sends the email to the doctor with the encrypted PDF attached.
    """
    # Convert PDF to base64 for attachment
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

    content = f"""
    <p>Bonjour <strong>{doctor_name}</strong>,</p>
    <p>Un nouveau formulaire a été reçu via PrivateForm.</p>

    <div class="info">
        📋 <strong>Formulaire :</strong> {form_name}<br>
        🕐 <strong>Date d'envoi :</strong> {submission_timestamp}
    </div>

    <p>Le PDF adjunto contient les réponses du patient. Il est protégé par
    votre <strong>mot de passe de chiffrement PDF</strong> configuré dans
    votre compte PrivateForm.</p>

    <div class="warning">
        📎 Pour ouvrir le PDF, utilisez votre mot de passe de chiffrement
        défini dans votre profil PrivateForm.
    </div>
    """

    attachments = [
        {
            "name": pdf_filename,
            "content": pdf_base64,
        }
    ]

    return await _send_email(
        to_email=to_email,
        to_name=doctor_name,
        subject=f"Nouveau formulaire reçu: {form_name}",
        html_body=_email_base_template(content),
        attachments=attachments,
    )


# =============================================================================
# Email: Critical error alert
# =============================================================================

async def send_critical_alert_email(
    error_type: str,
    error_message: str,
    timestamp: str,
    url_affected: str,
    doctor_id: str | None = None,
    form_name: str | None = None,
) -> bool:
    """
    Sends critical error alert to administrator.
    Respects alert rate limiting (maximum 10/hour).
    """
    if not check_alert_limit():
        logger.warning("Alert limit reached. Alert not sent.")
        return False

    # Build optional lines
    extra_info = ""
    if doctor_id:
        extra_info += f"<br>👨‍⚕️ <strong>ID Médico:</strong> {doctor_id}"
    if form_name:
        extra_info += f"<br>📋 <strong>Formulaire:</strong> {form_name}"

    content = f"""
    <p>⚠️ <strong>Une erreur critique a été détectée sur PrivateForm.</strong></p>

    <div class="warning">
        🔴 <strong>Type d'erreur :</strong> {error_type}<br>
        📝 <strong>Message :</strong> {error_message}<br>
        🕐 <strong>Timestamp :</strong> {timestamp}<br>
        🌐 <strong>URL affectée :</strong> {url_affected}
        {extra_info}
    </div>

    <p>Merci de vérifier les logs de l'application pour plus de détails.</p>
    """

    return await _send_email(
        to_email=settings.ALERT_EMAIL,
        to_name="PrivateForm Alertes",
        subject="⚠️ PrivateForm - Erreur critique",
        html_body=_email_base_template(content),
    )
