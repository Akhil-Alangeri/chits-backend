from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel


# =========================================================
# LEDGER TRANSACTION TYPES
# =========================================================

LedgerTransactionType = Literal[
    "chit_collection",
    "loan_taken",
    "loan_given",
    "loan_repayment_received",
    "loan_repayment_paid",
    "expense",
    "chit_payout",
]


# =========================================================
# PAYMENT METHODS
# =========================================================

LedgerPaymentMethod = Literal[
    "all",
    "cash",
    "upi",
    "bank_transfer",
    "cheque",
    "other",
]


# =========================================================
# SUMMARY
# =========================================================

class LedgerReportSummary(BaseModel):
    total_transactions: int

    total_money_in: int
    total_money_out: int
    net_movement: int

    cash_in: int
    cash_out: int
    cash_net: int

    bank_in: int
    bank_out: int
    bank_net: int


# =========================================================
# LEDGER ITEM
# =========================================================

class LedgerReportItem(BaseModel):
    id: str

    date: date

    transaction_type: str

    description: str

    reference: Optional[str] = None

    person_name: Optional[str] = None

    chit_name: Optional[str] = None

    loan_direction: Optional[str] = None

    payment_method: str

    amount: int

    cash_amount: int

    bank_amount: int

    money_flow: Literal["in", "out"]

    cash_balance: int

    bank_balance: int

    total_balance: int


# =========================================================
# RESPONSE
# =========================================================

class LedgerReportResponse(BaseModel):
    company_id: int

    company_name: str

    logo_url: Optional[str] = None

    date_from: Optional[date] = None

    date_to: Optional[date] = None

    summary: LedgerReportSummary

    items: list[LedgerReportItem]

    total_records: int

    page: int

    page_size: int

    total_pages: int