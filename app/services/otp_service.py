import os
import httpx

from fastapi import HTTPException


MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY")
MSG91_TEMPLATE_ID = os.getenv("MSG91_TEMPLATE_ID")

MSG91_SEND_OTP_URL = "https://control.msg91.com/api/v5/otp"
MSG91_VERIFY_OTP_URL = "https://control.msg91.com/api/v5/otp/verify"


# =====================================================
# NORMALIZE INDIAN MOBILE
# =====================================================

def normalize_indian_mobile(mobile: str) -> str:
    number = "".join(
        char for char in mobile
        if char.isdigit()
    )

    if len(number) == 10:
        return f"91{number}"

    if len(number) == 12 and number.startswith("91"):
        return number

    raise HTTPException(
        status_code=400,
        detail="Invalid mobile number.",
    )


# =====================================================
# SEND OTP
# =====================================================

async def send_mobile_otp(
    mobile: str,
) -> None:
    if not MSG91_AUTH_KEY or not MSG91_TEMPLATE_ID:
        raise HTTPException(
            status_code=500,
            detail="OTP service is not configured.",
        )

    mobile_number = normalize_indian_mobile(mobile)

    params = {
        "template_id": MSG91_TEMPLATE_ID,
        "mobile": mobile_number,

        # Optional:
        # keep this aligned with your SMS text
        "otp_expiry": 10,
    }

    headers = {
        "accept": "application/json",
        "authkey": MSG91_AUTH_KEY,
    }

    try:
        async with httpx.AsyncClient(
            timeout=15.0
        ) as client:
            response = await client.post(
                MSG91_SEND_OTP_URL,
                params=params,
                headers=headers,
            )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="OTP service is temporarily unavailable.",
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Invalid response from OTP service.",
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=data.get(
                "message",
                "Unable to send OTP.",
            ),
        )

    if data.get("type") != "success":
        raise HTTPException(
            status_code=400,
            detail=data.get(
                "message",
                "Unable to send OTP.",
            ),
        )


# =====================================================
# VERIFY OTP
# =====================================================

async def verify_mobile_otp(
    mobile: str,
    otp: str,
) -> bool:
    if not MSG91_AUTH_KEY:
        raise HTTPException(
            status_code=500,
            detail="OTP service is not configured.",
        )

    mobile_number = normalize_indian_mobile(mobile)

    params = {
        "mobile": mobile_number,
        "otp": otp,
    }

    headers = {
        "accept": "application/json",
        "authkey": MSG91_AUTH_KEY,
    }

    try:
        async with httpx.AsyncClient(
            timeout=15.0
        ) as client:
            response = await client.get(
                MSG91_VERIFY_OTP_URL,
                params=params,
                headers=headers,
            )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="OTP verification service is temporarily unavailable.",
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Invalid response from OTP service.",
        ) from exc

    if response.status_code >= 500:
        raise HTTPException(
            status_code=503,
            detail="OTP verification service is temporarily unavailable.",
        )

    message = str(
        data.get("message", "")
    ).strip().lower()

    return (
        data.get("type") == "success"
        and message == "otp verified success"
    )