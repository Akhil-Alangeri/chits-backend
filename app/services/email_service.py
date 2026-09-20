import os

from email.message import EmailMessage

import aiosmtplib


async def send_company_credentials(
    recipient_email: str,
    company_name: str,
    login_id: str,
    temporary_password: str,
):

    message = EmailMessage()

    message["From"] = os.getenv("SMTP_FROM")

    message["To"] = recipient_email

    message["Subject"] = (
        "SA Chits - Company Account Approved"
    )


    message.set_content(
        f"""
Hello {company_name},

Your SA Chits company registration has been approved.

Your company login credentials are:

Company:
{company_name}

Login ID:
{login_id}

Temporary Password:
{temporary_password}


Please login and change your password after your first login.

Regards,
Akhil Chits Team
"""
    )


    await aiosmtplib.send(
        message,

        hostname=os.getenv(
            "SMTP_HOST",
            "smtp.gmail.com"
        ),

        port=int(
            os.getenv(
                "SMTP_PORT",
                "587"
            )
        ),

        username=os.getenv(
            "SMTP_USERNAME"
        ),

        password=os.getenv(
            "SMTP_PASSWORD"
        ),

        start_tls=True,
    )