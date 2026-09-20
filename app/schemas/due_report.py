from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel


DueReportStatus = Literal[
    "all",
    "due",
    "partial",
    "overdue",
]


class DueReportSummary(BaseModel):
    total_due: int
    total_paid: int
    total_remaining: int

    total_records: int

    due_records: int
    partial_records: int
    overdue_records: int

    unique_members: int


class DueReportItem(BaseModel):
    id: int

    chit_id: int
    chit_name: str
    chit_code: Optional[str] = None

    chit_member_id: int
    member_id: int

    member_number: Optional[str] = None
    member_name: str
    customer_code: Optional[str] = None

    installment_number: int
    due_date: Optional[date] = None

    due_amount: int
    paid_amount: int
    remaining_amount: int

    status: Literal[
        "due",
        "partial",
        "overdue",
    ]

    days_overdue: int


class DueReportResponse(BaseModel):
    company_id: int
    company_name: str
    logo_url: Optional[str] = None

    summary: DueReportSummary

    items: list[DueReportItem]

    total_records: int
    page: int
    page_size: int
    total_pages: int