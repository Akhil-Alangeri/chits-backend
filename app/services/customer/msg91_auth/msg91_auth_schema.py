import re
from fastapi import HTTPException
from pydantic import BaseModel, field_validator


class Msg91SendOtpRequest(BaseModel):
    mobile_number: str

    @field_validator("mobile_number")
    @classmethod
    def normalize_mobile(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"(?:\+?91)?[6-9][0-9]{9}", value):
            raise HTTPException(400, "Invalid mobile number.")
        return value[-10:]


class Msg91VerifyOtpRequest(Msg91SendOtpRequest):
    otp: str

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{6}", value):
            raise HTTPException(400, "Enter a valid 6-digit OTP.")
        return value


class Msg91OtpResponse(BaseModel):
    success: bool = True
    message: str
    resend_after: int = 60
    request_id: str | None = None
