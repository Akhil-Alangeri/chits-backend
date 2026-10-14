from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


# =========================================================
# CREATE PAYMENT
# =========================================================

class PaymentTransactionCreate(BaseModel):

    amount: int = Field(
        gt=0,
        description="Payment amount in whole rupees.",
    )

    payment_date: date

    payment_method: str = Field(
        min_length=1,
        max_length=30,
    )

    reference_number: str | None = Field(
        default=None,
        max_length=100,
    )

    notes: str | None = None


# =========================================================
# UPDATE PAYMENT
# =========================================================

class PaymentTransactionUpdate(BaseModel):

    amount: int = Field(
        gt=0,
        description="Updated payment amount in whole rupees.",
    )

    payment_date: date

    payment_method: str = Field(
        min_length=1,
        max_length=30,
    )

    reference_number: str | None = Field(
        default=None,
        max_length=100,
    )

    notes: str | None = None


# =========================================================
# PAYMENT TRANSACTION RESPONSE
# =========================================================

class PaymentTransactionResponse(BaseModel):

    id: int

    installment_id: int

    amount: int

    payment_date: date

    payment_method: str

    reference_number: str | None

    notes: str | None

    created_by: int

    created_at: datetime | None

    updated_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
    )


# =========================================================
# PAYMENT HISTORY ITEM
# =========================================================

class PaymentHistoryItem(BaseModel):

    payment_id: int

    installment_id: int

    installment_number: int

    due_date: date

    due_amount: int

    # Actual amount of this individual transaction
    payment_amount: int

    paid_amount: int

    remaining_amount: int

    payment_date: date

    payment_method: str

    reference_number: str | None

    notes: str | None

    created_by: int | None

    created_at: datetime | None
# =========================================================
# PAYMENT HISTORY RESPONSE
# =========================================================

class PaymentHistoryResponse(BaseModel):

    customer_id: int

    chit_id: int

    member_id: int

    member_number: int

    member_name: str

    chit_name: str

    chit_code: str

    monthly_emi: int

    total_months: int

    total_due: int

    total_paid: int

    remaining_amount: int

    paid_months: int

    remaining_months: int

    payments: list[PaymentHistoryItem]