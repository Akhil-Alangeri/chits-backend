import os
import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


SMTP_HOST = os.getenv(
    "SMTP_HOST",
    "smtp.gmail.com",
)

SMTP_PORT = int(
    os.getenv(
        "SMTP_PORT",
        "587",
    )
)

SMTP_USERNAME = os.getenv(
    "SMTP_USERNAME",
)

SMTP_PASSWORD = os.getenv(
    "SMTP_PASSWORD",
)

SMTP_FROM = os.getenv(
    "SMTP_FROM",
)


def send_email(
    to_email: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> None:

    if not SMTP_USERNAME:
        raise RuntimeError(
            "SMTP_USERNAME is not configured"
        )

    if not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP_PASSWORD is not configured"
        )

    if not SMTP_FROM:
        raise RuntimeError(
            "SMTP_FROM is not configured"
        )

    message = MIMEMultipart()

    message["From"] = SMTP_FROM
    message["To"] = to_email
    message["Subject"] = subject

    if reply_to:
        message["Reply-To"] = reply_to

    message.attach(
        MIMEText(
            body.strip(),
            "plain",
            "utf-8",
        )
    )

    with smtplib.SMTP(
        SMTP_HOST,
        SMTP_PORT,
        timeout=30,
    ) as server:

        server.starttls()

        server.login(
            SMTP_USERNAME,
            SMTP_PASSWORD,
        )

        server.sendmail(
            SMTP_FROM,
            [to_email],
            message.as_string(),
        )