from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CompanyCreate(BaseModel):

    company_name: str = Field(
        ...,
        min_length=2,
        max_length=150
    )

    mobile: str = Field(
        ...,
        min_length=10,
        max_length=20
    )

    email: EmailStr

    address: str = Field(
        ...,
        min_length=5,
        max_length=500
    )


class CompanyResponse(BaseModel):

    id: int

    company_name: str

    logo_url: str | None = None

    mobile: str | None = None

    email: str | None = None

    address: str | None = None

    status: str

    created_at: datetime

    updated_at: datetime

    class Config:
        from_attributes = True