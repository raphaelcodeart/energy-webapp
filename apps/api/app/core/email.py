"""Minimal SMTP email sending, used only for password-reset links today.

No email infrastructure existed anywhere in this project before this. Rather
than fake it or block the whole password-reset feature on procuring an SMTP
provider, this sends for real when SMTP_HOST is configured, and otherwise
writes the would-be email (including the reset link) to the audit log --
real, inspectable, and never silently lost, but not actually delivered until
SMTP is configured (see docs/business-rules.md §Password reset)."""

import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

settings = get_settings()


class EmailNotConfiguredError(Exception):
    pass


def send_email(*, to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        raise EmailNotConfiguredError("SMTP is not configured (smtp_host is empty)")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_address
    message["To"] = to
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
