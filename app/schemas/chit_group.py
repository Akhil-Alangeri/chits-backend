from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# =========================================================
# CHIT MONTH CREATE
# =========================================================

class ChitMonthCreate(BaseModel):

    month_number: int = Field(
        gt=0
    )

    month_date: date

    monthly_emi: Decimal = Field(
        gt=0
    )

    monthly_lift_amount: Decimal = Field(
        gt=0
    )


# =========================================================
# CHIT GROUP CREATE
# =========================================================

class ChitGroupCreate(BaseModel):

    name: str = Field(
        min_length=2,
        max_length=150
    )

    chit_value: Decimal = Field(
        gt=0
    )

    # -----------------------------------------------------
    # Keep this for compatibility with existing ChitGroup.
    # Actual month-wise EMI will come from ChitMonth.
    # -----------------------------------------------------

    monthly_emi: Decimal = Field(
        gt=0
    )

    duration_months: int = Field(
        gt=0
    )

    max_members: int = Field(
        gt=0
    )

    start_date: date

    # -----------------------------------------------------
    # MONTH-WISE SCHEDULE
    # -----------------------------------------------------

    months: list[ChitMonthCreate] = Field(
        min_length=1
    )


# =========================================================
# CHIT GROUP UPDATE
# =========================================================

class ChitGroupUpdate(BaseModel):

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=150
    )

    chit_value: Optional[Decimal] = Field(
        default=None,
        gt=0
    )

    # Keep temporarily for existing code compatibility.
    monthly_emi: Optional[Decimal] = Field(
        default=None,
        gt=0
    )

    duration_months: Optional[int] = Field(
        default=None,
        gt=0
    )

    max_members: Optional[int] = Field(
        default=None,
        gt=0
    )

    start_date: Optional[date] = None

    status: Optional[str] = "draft"

    # -----------------------------------------------------
    # MONTH-WISE SCHEDULE UPDATE
    # -----------------------------------------------------

    months: Optional[list[ChitMonthCreate]] = None


# =========================================================
# CHIT MONTH RESPONSE
# =========================================================

class ChitMonthResponse(BaseModel):

    id: int

    company_id: int

    chit_id: int

    month_number: int

    month_date: date

    monthly_emi: Decimal

    monthly_lift_amount: Decimal

    class Config:
        from_attributes = True


# =========================================================
# CHIT GROUP RESPONSE
# =========================================================

class ChitGroupResponse(BaseModel):

    id: int

    company_id: int

    name: str

    code: str

    chit_value: Decimal

    monthly_emi: Decimal

    duration_months: int

    max_members: int

    start_date: Optional[date]

    status: str

    months: list[ChitMonthResponse] = []

    class Config:
        from_attributes = True