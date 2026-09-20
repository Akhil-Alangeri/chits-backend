from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# =========================================================
# OVERVIEW
# =========================================================

class DashboardOverview(BaseModel):
    active_chits: int
    total_customers: int
    active_members: int

    today_collection: int
    this_month_collection: int

    total_due: int
    total_paid: int
    total_outstanding: int

    collection_rate: float


# =========================================================
# COLLECTION BREAKDOWN
# =========================================================

class CollectionBreakdown(BaseModel):
    total: int

    upi: int
    cash: int
    bank_transfer: int
    cheque: int
    other: int


# =========================================================
# PAYMENT STATUS
# =========================================================

class PaymentStatus(BaseModel):
    total: int
    paid: int
    partial: int
    pending: int


# =========================================================
# DUES
# =========================================================

class DashboardDues(BaseModel):
    overdue_count: int
    overdue_amount: int

    due_this_month_count: int
    due_this_month_amount: int


# =========================================================
# CASH
# =========================================================

class DashboardCash(BaseModel):
    cash_collected_today: int
    cash_collected_this_month: int
    cash_collected_total: int
    upi_collected_total: int

    cash_closing_balance: int
    bank_upi_closing_balance: int
    total_cash_bank_balance: int


# =========================================================
# CASH / BANK CLOSING BALANCE
# =========================================================

class DashboardCashBank(BaseModel):
    cash: int
    bank: int
    total: int


# =========================================================
# LOANS
# =========================================================

class DashboardLoans(BaseModel):
    total_count: int
    active_count: int
    partially_settled_count: int
    closed_count: int

    given_amount: int
    taken_amount: int

    given_outstanding: int
    taken_outstanding: int
    total_outstanding: int

    given_cash: int
    given_upi: int

    repayment_cash: int
    repayment_upi: int


# =========================================================
# EXPENSE CATEGORY
# =========================================================

class ExpenseCategorySummary(BaseModel):
    category: str
    amount: int


# =========================================================
# EXPENSE DASHBOARD
# =========================================================

class DashboardExpenses(BaseModel):
    total: int
    this_month: int

    cash: int
    upi: int

    this_month_cash: int
    this_month_upi: int

    categories: list[ExpenseCategorySummary]


# =========================================================
# BALANCE
# =========================================================

class DashboardBalance(BaseModel):
    collections: int
    loan_given: int
    loan_repayments: int
    expenses: int

    available_balance: int


# =========================================================
# MONTHLY CHART
# =========================================================

class MonthlyChartPoint(BaseModel):
    month: int
    collection: int
    due: int


# =========================================================
# CHIT-WISE SUMMARY
# =========================================================

class ChitWiseSummary(BaseModel):
    chit_id: int
    chit_name: str
    chit_code: str

    monthly_emi: int

    total_due: int
    total_paid: int
    outstanding: int

    collection_rate: float

    this_month_collection: int

    upi: int
    cash: int
    bank_transfer: int
    cheque: int
    other: int


# =========================================================
# RECENT PAYMENT
# =========================================================

class RecentPayment(BaseModel):
    payment_id: int

    customer_id: int
    customer_name: str
    customer_code: str | None = None

    chit_id: int
    chit_name: str
    chit_code: str

    member_id: int
    member_number: int

    installment_number: int

    amount: int
    payment_method: str | None = None

    payment_date: date | datetime | None = None

    reference_number: str | None = None


# =========================================================
# UPCOMING AUCTION
# =========================================================

class UpcomingAuction(BaseModel):
    chit_id: int
    chit_name: str
    chit_code: str

    chit_month_id: int
    month_number: int

    auction_date: date

    planned_lift_amount: int


# =========================================================
# COMPLETE DASHBOARD RESPONSE
# =========================================================

class DashboardResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    overview: DashboardOverview

    today_collection: CollectionBreakdown
    this_month_collection: CollectionBreakdown

    payment_status: PaymentStatus

    dues: DashboardDues

    cash_bank: DashboardCashBank

    cash: DashboardCash

    loans: DashboardLoans

    expenses: DashboardExpenses

    balance: DashboardBalance

    upcoming_auctions: list[UpcomingAuction]

    monthly_chart: list[MonthlyChartPoint]

    chit_wise: list[ChitWiseSummary]

    recent_payments: list[RecentPayment]