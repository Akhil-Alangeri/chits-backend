from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel


LoanReportDirection = Literal[
    "all",
    "given",
    "taken",
]

LoanReportStatus = Literal[
    "all",
    "active",
    "partially_settled",
    "closed",
    "cancelled",
]


class LoanReportSummary(BaseModel):
    total_loans: int

    active_loans: int
    partially_settled_loans: int
    closed_loans: int
    cancelled_loans: int

    given_loans: int
    taken_loans: int

    total_principal: int
    total_disbursed: int

    principal_paid: int
    interest_paid: int
    discount: int

    principal_outstanding: int
    interest_outstanding: int
    total_outstanding: int

    cash_disbursed: int
    upi_disbursed: int

    cash_repaid: int
    upi_repaid: int

    total_repayments: int

    unique_persons: int


class LoanReportItem(BaseModel):
    id: int

    person_name: str
    person_mobile: Optional[str] = None
    person_address: Optional[str] = None

    direction: str

    principal_amount: int
    interest_rate: int | float
    interest_type: str

    start_date: date
    due_date: Optional[date] = None

    status: str

    total_disbursed: int

    principal_paid: int
    interest_paid: int
    discount: int

    principal_outstanding: int
    interest_outstanding: int

    total_paid: int
    total_outstanding: int

    cash_disbursed: int
    upi_disbursed: int

    cash_repaid: int
    upi_repaid: int

    transaction_count: int

    last_transaction_date: Optional[date] = None


class LoanReportResponse(BaseModel):
    company_id: int
    company_name: str
    logo_url: Optional[str] = None

    as_of_date: date

    summary: LoanReportSummary

    items: list[LoanReportItem]

    total_records: int
    page: int
    page_size: int
    total_pages: int