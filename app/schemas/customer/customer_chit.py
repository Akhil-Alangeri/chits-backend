from decimal import Decimal
from datetime import date

from pydantic import BaseModel, Field


# =========================================================
# COMPANY BASIC DETAILS
# =========================================================

class CustomerCompanyResponse(BaseModel):

    company_id: int

    company_name: str

    logo_url: str | None = None

    customer_profile_id: int | None = None

    customer_code: str | None = None


# =========================================================
# COMPANY STATISTICS
# =========================================================

class CustomerCompanyStatistics(BaseModel):

    active_chits: int

    active_members: int


# =========================================================
# CUSTOMER CHIT
# =========================================================

class CustomerChitResponse(BaseModel):

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
# MY CHITS - COMPANIES LIST
# =========================================================

class CustomerMyChitsResponse(BaseModel):

    success: bool

    message: str

    companies: list[CustomerCompanyResponse] = Field(
        default_factory=list
    )


# =========================================================
# COMPANY CHITS PAGE
# =========================================================

class CustomerCompanyChitsResponse(BaseModel):

    success: bool

    message: str

    company: CustomerCompanyResponse

    statistics: CustomerCompanyStatistics

    chits: list[CustomerChitResponse] = Field(
        default_factory=list
    )
    
    
    
# =========================================================
# CUSTOMER PAYMENT TRANSACTION
# =========================================================

class CustomerPaymentTransactionResponse(BaseModel):

    payment_id: int

    amount: Decimal

    payment_date: date

    payment_method: str

    reference_number: str | None = None


# =========================================================
# CUSTOMER MONTHLY PAYMENT
# =========================================================

class CustomerMonthlyPaymentResponse(BaseModel):

    installment_id: int

    installment_number: int

    due_date: date

    due_amount: Decimal

    paid_amount: Decimal

    balance_amount: Decimal

    status: str

    payments: list[
        CustomerPaymentTransactionResponse
    ] = Field(
        default_factory=list
    )


# =========================================================
# CURRENT MONTH PAYMENT
# =========================================================

class CustomerCurrentMonthPaymentResponse(BaseModel):

    installment_number: int

    due_date: date

    due_amount: Decimal

    paid_amount: Decimal

    balance_amount: Decimal

    status: str


# =========================================================
# PAYMENT SUMMARY
# =========================================================

class CustomerPaymentSummaryResponse(BaseModel):

    total_installments: int

    paid_installments: int

    due_installments: int

    total_due_amount: Decimal

    total_paid_amount: Decimal

    total_pending_amount: Decimal


# =========================================================
# CUSTOMER LIFT DETAILS
# =========================================================

class CustomerLiftDetailsResponse(BaseModel):

    lift_id: int

    month_number: int

    month_date: date

    lift_date: date

    monthly_lift_amount: Decimal

    discount_amount: Decimal

    lifted_amount: Decimal

    payout_status: str

    payout_date: date | None = None

    cash_amount: Decimal

    upi_amount: Decimal


# =========================================================
# CUSTOMER CHIT DETAILS
# =========================================================

class CustomerChitDetailsResponse(BaseModel):

    success: bool

    message: str

    chit: CustomerChitResponse

    payment_summary: CustomerPaymentSummaryResponse

    current_month: CustomerCurrentMonthPaymentResponse | None = None

    monthly_payments: list[
        CustomerMonthlyPaymentResponse
    ] = Field(
        default_factory=list
    )

    lift_details: CustomerLiftDetailsResponse | None = None
    
    
from decimal import Decimal
from datetime import date

from pydantic import BaseModel, Field


class CustomerCompanyResponse(BaseModel):
    company_id: int
    company_name: str
    logo_url: str | None = None
    customer_profile_id: int | None = None
    customer_code: str | None = None


class CustomerCompanyStatistics(BaseModel):
    active_chits: int
    active_members: int


class CustomerChitResponse(BaseModel):
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


class CustomerMyChitsResponse(BaseModel):
    success: bool
    message: str
    companies: list[CustomerCompanyResponse] = Field(
        default_factory=list
    )


class CustomerCompanyChitsResponse(BaseModel):
    success: bool
    message: str
    company: CustomerCompanyResponse
    statistics: CustomerCompanyStatistics
    chits: list[CustomerChitResponse] = Field(
        default_factory=list
    )


# ============================================================
# CUSTOMER CHIT DETAILS
# ============================================================

class CustomerPaymentTransactionResponse(BaseModel):
    payment_id: int
    amount: Decimal
    payment_date: date
    payment_method: str
    reference_number: str | None = None


class CustomerMonthlyPaymentResponse(BaseModel):
    installment_id: int
    installment_number: int
    due_date: date
    due_amount: Decimal

    paid_amount: Decimal
    balance_amount: Decimal

    status: str

    payments: list[CustomerPaymentTransactionResponse] = Field(
        default_factory=list
    )


class CustomerPaymentSummaryResponse(BaseModel):
    total_installments: int
    paid_installments: int
    due_installments: int

    total_due_amount: Decimal
    total_paid_amount: Decimal
    total_pending_amount: Decimal


class CustomerLiftDetailsResponse(BaseModel):
    lift_id: int

    month_number: int
    month_date: date

    lift_date: date

    monthly_lift_amount: Decimal
    discount_amount: Decimal
    lifted_amount: Decimal

    payout_status: str
    payout_date: date | None = None

    cash_amount: Decimal
    upi_amount: Decimal


class CustomerChitDetailsResponse(BaseModel):
    success: bool
    message: str

    # This is ONE specific slot/member.
    chit: CustomerChitResponse

    payment_summary: CustomerPaymentSummaryResponse

    # Every month/installment for this specific slot.
    monthly_payments: list[CustomerMonthlyPaymentResponse] = Field(
        default_factory=list
    )

    # One lift for this specific slot, if lifted.
    lift_details: CustomerLiftDetailsResponse | None = None