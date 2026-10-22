"""Multipart SMTP delivery using the existing SMTP environment contract."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from uuid import NAMESPACE_URL, uuid5
from email_validator import validate_email


class EmailConfigurationError(RuntimeError):
    pass


def smtp_config():
    values = {key: os.getenv(key, "").strip() for key in (
        "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM",
    )}
    values["SMTP_PASSWORD"] = os.getenv("SMTP_PASSWORD", "")
    if not all(values.values()):
        raise EmailConfigurationError("SMTP configuration incomplete")
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        if not 1 <= port <= 65535:
            raise ValueError()
        tls = os.getenv("SMTP_USE_TLS", "true").lower()
        implicit = os.getenv("SMTP_USE_SSL", "false").lower()
        if tls not in {"true", "false"} or implicit not in {"true", "false"}:
            raise ValueError()
        if (tls == "true") == (implicit == "true"):
            raise ValueError()  # Require exactly one encrypted transport.
        validate_email(values["SMTP_FROM"], check_deliverability=False)
        if any("\r" in value or "\n" in value for value in values.values()):
            raise ValueError()
    except ValueError as exc:
        raise EmailConfigurationError("Invalid SMTP configuration") from exc
    return values, port, implicit == "true"


def send_welcome_email(recipient, subject, text, html, message_key):
    values, port, implicit_ssl = smtp_config()
    recipient = validate_email(recipient, check_deliverability=False).normalized
    message = EmailMessage()
    message["From"] = values["SMTP_FROM"]
    message["To"] = recipient
    message["Subject"] = subject
    opaque_key = uuid5(NAMESPACE_URL, f"https://nexnidhi.in/mail/welcome/{message_key}")
    message["Message-ID"] = f"<welcome-{opaque_key}@nexnidhi.in>"
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    context = ssl.create_default_context()
    if implicit_ssl:
        connection = smtplib.SMTP_SSL(values["SMTP_HOST"], port, timeout=30, context=context)
    else:
        connection = smtplib.SMTP(values["SMTP_HOST"], port, timeout=30)
    with connection as server:
        if not implicit_ssl:
            server.starttls(context=context)
        server.login(values["SMTP_USERNAME"], values["SMTP_PASSWORD"])
        refused = server.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
