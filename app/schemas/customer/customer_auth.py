from pydantic import BaseModel, Field


class CustomerSendOTPRequest(BaseModel):
    mobile: str = Field(
        ...,
        min_length=10,
        max_length=15,
    )


class CustomerSendOTPResponse(BaseModel):
    success: bool
    message: str
    otp_expires_in: int | None = None
    development_otp: str | None = None

class CustomerVerifyOTPRequest(BaseModel):
    mobile: str = Field(
        ...,
        min_length=10,
        max_length=15,
    )

    otp: str = Field(
        ...,
        min_length=6,
        max_length=6,
    )


class CustomerTokenResponse(BaseModel):
    success: bool
    message: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None