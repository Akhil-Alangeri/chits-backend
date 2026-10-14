"""Backend-only MSG91 v5 transport. Never log requests, OTPs or provider bodies."""
import os
import logging
import re
import httpx
from fastapi import HTTPException

BASE_URL = "https://control.msg91.com/api/v5/otp"
INVALID_MESSAGES = {"otp not match", "otp expired", "otp not found", "invalid otp", "otp already verified"}


async def _request(mobile: str, otp: str | None = None) -> str | None:
    key = os.getenv("MSG91_AUTH_KEY")
    template = os.getenv("MSG91_TEMPLATE_ID")
    if not key or not template:
        raise HTTPException(503, "OTP service is not configured.")
    params = {"mobile": "91" + mobile}
    if otp is None:
        params.update(template_id=template, otp_length=6, otp_expiry=10, invisible=0, realTimeResponse=1)
    else:
        params["otp"] = otp
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                "POST" if otp is None else "GET",
                BASE_URL if otp is None else BASE_URL + "/verify",
                params=params, headers={"authkey": key, "accept": "application/json", "content-type": "application/json"},
            )
    except httpx.RequestError:
        raise HTTPException(503, "OTP service is temporarily unavailable.") from None
    if response.status_code >= 500 or response.status_code == 429:
        raise HTTPException(503, "OTP service is temporarily unavailable.")
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(502, "Invalid response from OTP service.") from None
    if not isinstance(data, dict):
        raise HTTPException(502, "Invalid response from OTP service.")
    message = str(data.get("message", "")).strip().lower()
    if "ip is not whitelisted" in message:
        logging.getLogger("uvicorn.error").error(
            "MSG91 rejected the backend IP. Add the server's outbound IP to the Authkey whitelist."
        )
        raise HTTPException(
            503, "OTP service is unavailable. Please contact support.",
            headers={"X-OTP-Error-Code": "msg91_ip_not_whitelisted"},
        )
    if otp is not None and message in INVALID_MESSAGES and response.status_code in (200, 400):
        raise HTTPException(401, "Invalid or expired OTP.")
    if response.status_code >= 400 or data.get("type") != "success":
        raise HTTPException(502, "OTP service is temporarily unavailable.")
    # Fail closed: 'already verified' must never issue another session.
    if otp is not None and message != "otp verified success":
        raise HTTPException(502, "Invalid response from OTP service.")


    if otp is None:
        # MSG91 returns a correlation ID, not proof of handset delivery.
        # Only allow its documented ID format; never expose a provider body.
        request_id = data.get("request_id") or data.get("requestId") or data.get("message")
        if isinstance(request_id, str) and re.fullmatch(r"[a-fA-F0-9]{16,128}", request_id):
            return request_id
    return None


async def send_otp(mobile: str) -> str | None:
    return await _request(mobile)


async def verify_otp(mobile: str, otp: str) -> None:
    await _request(mobile, otp)
