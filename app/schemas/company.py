from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CompanyStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "inactive"]

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


class CompanyPlanSummary(BaseModel):
    id: int
    name: str
    price: Decimal
    billing_cycle: str
    is_active: bool

    class Config:
        from_attributes = True


class CompanyResponse(BaseModel):

    subscription_plan: CompanyPlanSummary | None = None

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


class CompanyOverviewResponse(CompanyResponse):
    chit_group_amounts: list[Decimal] = Field(default_factory=list)
    active_customers_count: int = 0
    total_customers_count: int = 0
