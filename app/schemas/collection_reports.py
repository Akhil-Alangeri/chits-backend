from datetime import date
from typing import Optional, Literal

from pydantic import BaseModel, ConfigDict


CollectionReportStatus = Literal[
    "all",
    "paid",
    "partial",
    "due",
]


# =========================================================
# FILTERS
# =========================================================

class CollectionReportFilters(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    chit_id: Optional[int] = None
    member_id: Optional[int] = None

    payment_method: Optional[str] = None

    status: CollectionReportStatus = "all"

    search: Optional[str] = None


# =========================================================
# SUMMARY
# =========================================================

class CollectionReportSummary(BaseModel):
    total_collected: int
    total_payments: int
    unique_members: int
    pending_amount: int


# =========================================================
# COLLECTION ITEM
# =========================================================

class CollectionReportItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int

    date: date

    receipt_no: Optional[str] = None

    member_id: Optional[int] = None
    member_name: str
    member_number: Optional[str] = None

    chit_id: int
    chit_name: str

    installment_id: Optional[int] = None
    installment_number: Optional[int] = None

    due_amount: int
    paid_amount: int
    remaining_amount: int

    payment_method: str

    reference_number: Optional[str] = None

    status: Literal[
        "paid",
        "partial",
        "due",
    ]

    collected_by: Optional[str] = None


# =========================================================
# RESPONSE
# =========================================================

class CollectionReportResponse(BaseModel):

    # -----------------------------------------------------
    # COMPANY DETAILS
    # -----------------------------------------------------
    #
    # These are intentionally kept at ROOT LEVEL
    # to preserve the existing API structure.
    # -----------------------------------------------------

    company_id: int

    company_name: str

    logo_url: Optional[str] = None

    # -----------------------------------------------------
    # EXISTING REPORT DATA
    # -----------------------------------------------------

    summary: CollectionReportSummary

    items: list[CollectionReportItem]

    total_records: int

    page: int

    page_size: int

    total_pages: int