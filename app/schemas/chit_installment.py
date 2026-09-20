from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


# =========================================================
# GENERATE INSTALLMENTS
# =========================================================

class ChitInstallmentsGenerate(BaseModel):

    start_date: date

    installment_count: int


# =========================================================
# INSTALLMENT RESPONSE
# =========================================================

class ChitInstallmentResponse(BaseModel):

    id: int
    chit_member_id: int
    installment_number: int
    due_date: date
    due_amount: int
    paid_amount: int
    remaining_amount:int
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    model_config = ConfigDict(
        from_attributes=True
    )