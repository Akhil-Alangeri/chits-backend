from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# =========================================================
# COMPANY PROFILE UPDATE
# =========================================================

class CompanyProfileUpdate(BaseModel):

    company_name: Optional[str] = Field(
        default=None,
        max_length=150
    )

    email: Optional[EmailStr] = None

    mobile: Optional[str] = Field(
        default=None,
        max_length=20
    )

    address: Optional[str] = Field(
        default=None,
        max_length=500
    )

    logo_url: Optional[str] = Field(
        default=None,
        max_length=500
    )


# =========================================================
# COMPANY PROFILE DATA
# =========================================================

class CompanyProfileData(BaseModel):

    id: int
    company_name: str
    logo_url: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    address: Optional[str] = None
    status: str
    login_id: str


# =========================================================
# COMPANY PROFILE RESPONSE
# =========================================================

class CompanyProfileResponse(BaseModel):

    success: bool
    message: str
    data: CompanyProfileData


# =========================================================
# LOGIN ID UPDATE
# =========================================================

class LoginIdUpdate(BaseModel):

    login_id: str = Field(
        min_length=3,
        max_length=50
    )


class LoginIdUpdateResponse(BaseModel):

    success: bool
    message: str
    login_id: str


# =========================================================
# PASSWORD UPDATE
# =========================================================

class PasswordUpdate(BaseModel):

    current_password: str = Field(
        min_length=1,
        max_length=128
    )

    new_password: str = Field(
        min_length=8,
        max_length=128
    )

    confirm_password: str = Field(
        min_length=8,
        max_length=128
    )


class PasswordUpdateResponse(BaseModel):

    success: bool
    message: str