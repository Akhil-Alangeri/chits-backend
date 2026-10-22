from html import escape
from app.services.welcome_email import send_welcome_email

SUBJECT = "NexNidhi | Company Admin Password Reset Verification"

def send_recovery_email(recipient, name, otp, message_key):
    text = f"""Hello {name},

We received a request to reset the password for your NexNidhi Company Admin account.
Use the following verification code to continue: {otp}
This verification code expires in 5 minutes.
If you did not request a password reset, you can safely ignore this email.
For your security, never share this OTP with anyone.

Regards,
Team NexNidhi
NexNidhi ? Chit Management, Beautifully Organised"""
    html = f"""<!doctype html><html><body style="margin:0;background:#f6f3eb;font-family:Arial,sans-serif;color:#103e34">
<div style="max-width:600px;margin:auto;background:#fff">
<div style="padding:28px;background:#103e34;color:#e3cb8d"><h1>NexNidhi.</h1>SECURE ACCOUNT RECOVERY</div>
<div style="padding:28px"><p>Hello {escape(name)},</p>
<p>We received a request to reset the password for your NexNidhi Company Admin account.</p>
<p>Use the following verification code to continue:</p>
<div style="padding:20px;background:#f6f3eb;font-size:36px;letter-spacing:8px;text-align:center">{escape(otp)}</div>
<p>This verification code expires in <strong>5 minutes</strong>.</p>
<p>If you did not request a password reset, you can safely ignore this email.</p>
<p>For your security, never share this OTP with anyone.</p><p>Regards,<br><strong>Team NexNidhi</strong></p></div>
<div style="padding:24px;background:#103e34;color:#e3cb8d">NexNidhi ? Chit Management, Beautifully Organised</div></div></body></html>"""
    send_welcome_email(recipient, SUBJECT, text, html, message_key)
