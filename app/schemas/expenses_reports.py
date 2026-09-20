from datetime import date
from typing import Optional

from pydantic import BaseModel


# =========================================================
# CATEGORY SUMMARY
# =========================================================

class ExpenseReportCategorySummary(BaseModel):
    category: str
    amount: int
    record_count: int


# =========================================================
# MONTHLY SUMMARY
# =========================================================

class ExpenseReportMonthlySummary(BaseModel):
    year: int
    month: int
    month_name: str
    amount: int
    record_count: int


# =========================================================
# SUMMARY
# =========================================================

class ExpenseReportSummary(BaseModel):
    total_expenses: int
    total_records: int

    cash_expenses: int
    upi_expenses: int
    other_expenses: int

    average_expense: int

    highest_expense: int

    unique_categories: int


# =========================================================
# ITEM
# =========================================================

class ExpenseReportItem(BaseModel):
    id: int

    category: str
    amount: int

    description: Optional[str] = None

    expense_date: date

    payment_method: str

    reference: Optional[str] = None

    notes: Optional[str] = None

    created_by: int

    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# =========================================================
# RESPONSE
# =========================================================

class ExpenseReportResponse(BaseModel):
    company_id: int
    company_name: str
    logo_url: Optional[str] = None

    date_from: Optional[date] = None
    date_to: Optional[date] = None

    summary: ExpenseReportSummary

    categories: list[
        ExpenseReportCategorySummary
    ]

    monthly_summary: list[
        ExpenseReportMonthlySummary
    ]

    items: list[
        ExpenseReportItem
    ]

    total_records: int

    page: int
    page_size: int
    total_pages: int