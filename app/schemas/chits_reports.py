from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel


ChitReportStatus = Literal[
    "all",
    "draft",
    "active",
    "completed",
    "cancelled",
]


# =========================================================
# SUMMARY
# =========================================================

class ChitReportSummary(BaseModel):
    total_chits: int

    draft_chits: int
    active_chits: int
    completed_chits: int
    cancelled_chits: int

    total_chit_value: int

    total_members: int
    confirmed_members: int
    active_members: int

    total_scheduled_amount: int
    total_collected_amount: int
    total_outstanding_amount: int

    collection_rate: float

    total_lifts: int
    completed_payouts: int
    pending_payouts: int

    total_lifted_amount: int
    total_discount_amount: int


# =========================================================
# CHIT ITEM
# =========================================================

class ChitReportItem(BaseModel):
    id: int

    name: str
    code: str

    chit_value: int
    monthly_emi: int

    duration_months: int
    max_members: int

    start_date: Optional[date] = None

    status: str

    member_count: int
    confirmed_members: int
    active_members: int

    scheduled_amount: int
    collected_amount: int
    outstanding_amount: int

    collection_rate: float

    total_lifts: int

    lifted_amount: int
    discount_amount: int

    payout_completed: int
    payout_pending: int

    last_collection_date: Optional[date] = None
    last_lift_date: Optional[date] = None


# =========================================================
# MONTH SUMMARY
# =========================================================

class ChitReportMonthSummary(BaseModel):
    chit_id: int
    chit_name: str
    chit_code: str

    installment_number: int

    month_date: Optional[date] = None

    monthly_emi: int
    monthly_lift_amount: int

    scheduled_amount: int
    collected_amount: int
    outstanding_amount: int

    collection_rate: float

    paid_installments: int
    partial_installments: int
    pending_installments: int

    lift_status: str

    lifted_amount: int
    discount_amount: int


# =========================================================
# RESPONSE
# =========================================================

class ChitReportResponse(BaseModel):
    company_id: int
    company_name: str
    logo_url: Optional[str] = None

    summary: ChitReportSummary

    items: list[ChitReportItem]

    monthly_summary: list[
        ChitReportMonthSummary
    ]

    total_records: int

    page: int
    page_size: int
    total_pages: int