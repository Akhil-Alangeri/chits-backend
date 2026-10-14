from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# =========================================================
# PAYMENT TRANSACTION
# =========================================================


class CustomerReceiptPaymentResponse(BaseModel):
    payment_id: int

    amount: Decimal

    payment_date: date

    payment_method: str

    reference_number: str | None = None

    notes: str | None = None


# =========================================================
# MONTHLY PAYMENT
# =========================================================


class CustomerReceiptMonthlyPaymentResponse(BaseModel):
    installment_id: int

    installment_number: int

    due_date: date

    due_amount: Decimal

    paid_amount: Decimal

    balance_amount: Decimal

    status: str

    payments: list[
        CustomerReceiptPaymentResponse
    ] = Field(default_factory=list)


# =========================================================
# COMPANY
# =========================================================


class CustomerReceiptCompanyResponse(BaseModel):
    company_id: int

    company_name: str

    logo_url: str | None = None
    logo_data_url: str | None = None
    email: str | None = None

    mobile: str | None = None

    address: str | None = None


# =========================================================
# CUSTOMER
# =========================================================


class CustomerReceiptCustomerResponse(BaseModel):
    customer_profile_id: int

    customer_code: str

    display_name: str

    legal_name: str | None = None

    mobile: str

    email: str | None = None

    address: str | None = None


# =========================================================
# CHIT
# =========================================================


class CustomerReceiptChitResponse(BaseModel):
    chit_member_id: int

    chit_id: int

    chit_name: str

    chit_code: str

    customer_profile_id: int

    customer_code: str

    member_number: int

    slot_number: int

    member_name: str

    member_status: str

    chit_value: Decimal

    monthly_emi: Decimal

    duration_months: int

    start_date: date | None = None


# =========================================================
# PAYMENT SUMMARY
# =========================================================


class CustomerReceiptPaymentSummaryResponse(BaseModel):
    total_installments: int

    paid_installments: int

    due_installments: int

    partial_installments: int

    total_due_amount: Decimal

    total_paid_amount: Decimal

    total_pending_amount: Decimal


# =========================================================
# LIFT
# =========================================================


class CustomerReceiptLiftResponse(BaseModel):
    lift_id: int

    month_number: int

    month_date: date | None = None

    lift_date: date

    monthly_lift_amount: Decimal

    discount_amount: Decimal

    lifted_amount: Decimal

    payout_status: str

    payout_date: date | None = None

    cash_amount: Decimal | None = None

    upi_amount: Decimal | None = None


# =========================================================
# FINAL RECEIPT RESPONSE
# =========================================================


class CustomerReceiptResponse(BaseModel):

    success: bool

    message: str

    company: CustomerReceiptCompanyResponse

    customer: CustomerReceiptCustomerResponse

    chit: CustomerReceiptChitResponse

    payment_summary: CustomerReceiptPaymentSummaryResponse

    monthly_payments: list[
        CustomerReceiptMonthlyPaymentResponse
    ] = Field(default_factory=list)

    lift_details: CustomerReceiptLiftResponse | None = None

    generated_at: datetime