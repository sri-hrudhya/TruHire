import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Optional, Tuple

from backend.config import settings
from backend.models import EMAIL_STATUS_FAILED, EMAIL_STATUS_SENT, EMAIL_STATUS_SIMULATED

DELIVERY_MODE_SMTP = "smtp"
DELIVERY_MODE_SIMULATED = "simulated"


def smtp_configured() -> bool:
    return bool((settings.SMTP_HOST or "").strip())


def delivery_mode() -> str:
    return DELIVERY_MODE_SMTP if smtp_configured() else DELIVERY_MODE_SIMULATED


def sender_address() -> Optional[str]:
    return (settings.SMTP_FROM or settings.SMTP_USER or "").strip() or None


def deliver_email(recipient: str, subject: str, body: str) -> Tuple[str, str, Optional[str]]:
    """Send one plain-text email. Returns (status, delivery_mode, error).

    Without SMTP configured nothing is transmitted and the status is "simulated",
    so history never reports a simulated email as sent.
    """
    if not smtp_configured():
        print(f"[email] SIMULATED (no SMTP_HOST configured) to <{recipient}> | Subject: {subject}")
        return EMAIL_STATUS_SIMULATED, DELIVERY_MODE_SIMULATED, None

    from_addr = sender_address()
    if not from_addr:
        return EMAIL_STATUS_FAILED, DELIVERY_MODE_SMTP, "SMTP_FROM (or SMTP_USER) must be set to send email."

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid()
    msg.set_content(body)

    try:
        smtp_cls = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
        with smtp_cls(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT) as server:
            if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as exc:
        print(f"[email] SMTP delivery to <{recipient}> failed: {exc}")
        return EMAIL_STATUS_FAILED, DELIVERY_MODE_SMTP, str(exc) or exc.__class__.__name__
    return EMAIL_STATUS_SENT, DELIVERY_MODE_SMTP, None
