from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# =========================================================
# PAYOUT STATUS
# =========================================================

PayoutStatus = Literal[
    "pending",
    "paid",
    "cancelled",
]


# =========================================================
# CREATE
# =========================================================

class ChitLiftCreate(BaseModel):

    # -----------------------------------------------------
    # Month on which the lift/auction happened
    # -----------------------------------------------------

    chit_month_id: int = Field(
        ...,
        gt=0,
    )

    lift_date: date

    # -----------------------------------------------------
    # Additional amount
    #
    # Business meaning:
    # selected month's planned lift amount + discount_amount
    # = final lifted amount
    # -----------------------------------------------------

    discount_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    # -----------------------------------------------------
    # Keep this optional for API compatibility, but backend
    # should calculate the final value.
    #
    # Do NOT trust frontend value.
    # -----------------------------------------------------

    lifted_amount: Decimal | None = Field(
        default=None,
        gt=0,
    )
    upi_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    cash_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    payout_status: PayoutStatus = Field(
        default="pending",
    )

    payout_date: date | None = None

    notes: str | None = None


# =========================================================
# UPDATE
#
# edit_reason is mandatory for EVERY update.
# =========================================================

class ChitLiftUpdate(BaseModel):

    # -----------------------------------------------------
    # Winner / Membership can be changed during edit.
    # -----------------------------------------------------

    chit_member_id: int | None = Field(
        default=None,
        gt=0,
    )

    # -----------------------------------------------------
    # Month can be changed during edit.
    # -----------------------------------------------------

    chit_month_id: int | None = Field(
        default=None,
        gt=0,
    )

    lift_date: date | None = None
    
    discount_amount: Decimal | None = Field(
        default=None,
        ge=0,
    )

    upi_amount: Decimal | None = Field(
        default=None,
        ge=0,
    )

    # -----------------------------------------------------
    # Additional amount
    # -----------------------------------------------------

    discount_amount: Decimal | None = Field(
        default=None,
        ge=0,
    )

    # -----------------------------------------------------
    # Final amount
    #
    # Backend should recalculate this using:
    #
    # month.monthly_lift_amount + discount_amount
    # -----------------------------------------------------

    lifted_amount: Decimal | None = Field(
        default=None,
        gt=0,
    )

    payout_status: PayoutStatus | None = None

    payout_date: date | None = None

    notes: str | None = None

    # -----------------------------------------------------
    # MANDATORY AUDIT REASON
    # -----------------------------------------------------

    edit_reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
    )


# =========================================================
# RESPONSE
# =========================================================

class ChitLiftResponse(BaseModel):

    id: int

    company_id: int

    chit_id: int

    chit_member_id: int

    customer_name: str

    member_number: str

    slot_number: int | None

    # -----------------------------------------------------
    # Authoritative month reference
    # -----------------------------------------------------

    chit_month_id: int | None

    # -----------------------------------------------------
    # Temporary legacy field
    # -----------------------------------------------------

    cycle_number: int | None

    lift_date: date

    # -----------------------------------------------------
    # Additional amount
    # -----------------------------------------------------

    discount_amount: Decimal | None

    # -----------------------------------------------------
    # Final actual amount paid to customer
    # -----------------------------------------------------

    lifted_amount: Decimal
    upi_amount: Decimal

    cash_amount: Decimal

    payout_status: PayoutStatus

    payout_date: date | None

    notes: str | None

    edit_reason: str | None

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )