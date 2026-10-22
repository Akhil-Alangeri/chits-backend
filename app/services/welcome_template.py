"""Self-contained email-safe NexNidhi template, with escaped dynamic content."""
from html import escape

PORTAL_URL = "https://customer.nexnidhi.in/"
WEBSITE_URL = "https://nexnidhi.in/"


def clean(value):
    # Remove control characters, including CR/LF, from header and display values.
    return " ".join(str(value or "").split())


def render_welcome(customer_name, company_name, chit_name, membership_status):
    name, company, chit, status = map(clean, (
        customer_name, company_name, chit_name, membership_status,
    ))
    subject = f"Welcome to {company} | NexNidhi"
    text = f'''NexNidhi.
CHIT FUND MANAGEMENT PLATFORM

Welcome aboard!

Dear {name},

Welcome to {company}!
We are pleased to inform you that your membership in {chit} is now {status}.
Your chit membership details are listed below.

Chit Company: {company}
Chit Group: {chit}
Membership Status: {status.title()}

Two ways to access your customer account:
LOGIN TO CUSTOMER PORTAL: {PORTAL_URL}
You can also visit https://nexnidhi.in and select "Login as Customer" to access your customer account.
{WEBSITE_URL}

Thank you for being part of {company}.
Warm regards,
Team NexNidhi

Powered by NexNidhi
Chit management, beautifully organised.
For your security, never share your OTP or password.
This email confirms membership information, not a payment or financial transaction.
NexNidhi is a software platform, not a chit fund operator or payment-processing service.
'''
    status_label = escape(status.title())
    name, company, chit, status = map(escape, (name, company, chit, status))
    rows = "".join(
        f'<tr><td style="padding:13px 16px;border-bottom:1px solid #e8e2d2;color:#465b53;width:40%">{label}</td>'
        f'<td style="padding:13px 16px;border-bottom:1px solid #e8e2d2;color:#103e34;font-weight:bold;overflow-wrap:anywhere">{value}</td></tr>'
        for label, value in (("Chit Company", company), ("Chit Group", chit), ("Membership Status", status_label))
    )
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Welcome aboard | NexNidhi</title></head>
<body style="margin:0;padding:0;background-color:#f0eee7;font-family:Arial,Helvetica,sans-serif;color:#243e34">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#f0eee7"><tr><td align="center" style="padding:24px 10px">
<!--[if mso]><table role="presentation" width="600" align="center"><tr><td><![endif]-->
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#fffdf7" style="max-width:600px;background-color:#fffdf7">
<tr><td bgcolor="#103e34" style="padding:36px 28px;text-align:center;background-color:#103e34;color:#e3cb8d">
<div style="font-family:Georgia,serif;font-size:42px;font-weight:bold;color:#e3cb8d">NexNidhi.</div>
<p style="margin:12px 0 0;font-size:11px;letter-spacing:2px;color:#e3cb8d">CHIT FUND MANAGEMENT PLATFORM</p></td></tr>
<tr><td style="padding:32px 24px;font-size:16px;line-height:1.65">
<h1 style="margin:0 0 24px;font-family:Georgia,serif;font-size:30px;color:#103e34">Welcome aboard!</h1>
<p>Dear <strong>{name}</strong>,</p><p>Welcome to <strong>{company}</strong>!</p>
<p>We are pleased to inform you that your membership in <strong>{chit}</strong> is now <strong>{status}</strong>.</p>
<p>Your chit membership details are listed below.</p>
<table width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e3cb8d;background-color:#f8f4e9;font-size:14px;table-layout:fixed"><tbody>{rows}</tbody></table>
<h2 style="margin:30px 0 18px;font-size:18px;color:#103e34;text-align:center">Two ways to access your account</h2>
<table role="presentation" cellspacing="0" cellpadding="0" align="center"><tr><td bgcolor="#e3cb8d" style="background-color:#e3cb8d;text-align:center;mso-padding-alt:16px 20px">
<a href="{PORTAL_URL}" style="display:inline-block;padding:16px 20px;color:#103e34;font-size:13px;font-weight:bold;text-decoration:none">LOGIN TO CUSTOMER PORTAL</a></td></tr></table>
<p style="margin:20px 0 28px;font-size:14px;text-align:center;color:#243e34">You can also visit <a href="{WEBSITE_URL}" style="color:#103e34;text-decoration:underline;font-weight:bold">https://nexnidhi.in</a> and select &quot;Login as Customer&quot; to access your customer account.</p>
<p>Thank you for being part of <strong>{company}</strong>.</p><p style="margin-bottom:0">Warm regards,<br><strong>Team NexNidhi</strong></p></td></tr>
<tr><td style="padding:24px;border-top:1px solid #e3cb8d;text-align:center;font-size:12px;line-height:1.7;color:#465b53">
<strong style="color:#103e34">Powered by NexNidhi</strong><br><em>Chit management, beautifully organised.</em>
<p>For your security, never share your OTP or password.</p>
<p>This email confirms membership information, not a payment or financial transaction.</p>
<p style="margin-bottom:0">NexNidhi is a software platform, not a chit fund operator or payment-processing service.</p>
</td></tr></table><!--[if mso]></td></tr></table><![endif]--></td></tr></table></body></html>'''
    return subject, text, html
