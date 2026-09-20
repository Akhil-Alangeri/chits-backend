from __future__ import annotations

from datetime import date
from math import ceil
from typing import Optional

from sqlalchemy.orm import Session

from app.models.admin.company import Company
from app.models.admin.loan import Loan

from app.services.loan_services import (
    get_transactions_for_loan,
    get_principal_paid,
    calculate_outstanding_principal,
    calculate_automatic_interest,
    get_interest_paid,
    get_total_discount,
    get_total_payment_amount,
)


# =========================================================
# HELPERS
# =========================================================

def _safe_int(value) -> int:
    """
    Convert Decimal/int/float/None to integer.
    """

    if value is None:
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


def _safe_float(value) -> float:
    """
    Convert Decimal/int/float/None to float.
    """

    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _get_transaction_cash_amount(
    transactions,
) -> int:
    """
    Total cash movement from all loan transactions.
    """

    total = 0

    for transaction in transactions:
        total += _safe_int(
            transaction.cash_amount
        )

    return total


def _get_transaction_upi_amount(
    transactions,
) -> int:
    """
    Total UPI movement from all loan transactions.
    """

    total = 0

    for transaction in transactions:
        total += _safe_int(
            transaction.upi_amount
        )

    return total


def _get_disbursement_amount(
    transactions,
) -> int:
    """
    Total actual loan disbursement.

    Only disbursement transactions are included.
    """

    total = 0

    for transaction in transactions:

        if (
            transaction.transaction_type
            != "disbursement"
        ):
            continue

        total += (
            _safe_int(
                transaction.upi_amount
            )
            + _safe_int(
                transaction.cash_amount
            )
        )

    return total


def _get_disbursement_cash(
    transactions,
) -> int:

    total = 0

    for transaction in transactions:

        if (
            transaction.transaction_type
            != "disbursement"
        ):
            continue

        total += _safe_int(
            transaction.cash_amount
        )

    return total


def _get_disbursement_upi(
    transactions,
) -> int:

    total = 0

    for transaction in transactions:

        if (
            transaction.transaction_type
            != "disbursement"
        ):
            continue

        total += _safe_int(
            transaction.upi_amount
        )

    return total


def _get_repayment_cash(
    transactions,
) -> int:
    """
    Cash received/paid through repayment transactions.

    Disbursement is excluded.
    """

    total = 0

    for transaction in transactions:

        if transaction.transaction_type not in {
            "principal_repayment",
            "interest_payment",
        }:
            continue

        total += _safe_int(
            transaction.cash_amount
        )

    return total


def _get_repayment_upi(
    transactions,
) -> int:
    """
    UPI received/paid through repayment transactions.

    Disbursement is excluded.
    """

    total = 0

    for transaction in transactions:

        if transaction.transaction_type not in {
            "principal_repayment",
            "interest_payment",
        }:
            continue

        total += _safe_int(
            transaction.upi_amount
        )

    return total


def _get_last_transaction_date(
    transactions,
) -> Optional[date]:

    if not transactions:
        return None

    return max(
        transaction.transaction_date
        for transaction in transactions
        if transaction.transaction_date
    )


# =========================================================
# BUILD REPORT
# =========================================================

def _build_loan_report_data(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    direction: str = "all",
    report_status: str = "all",
    search: Optional[str] = None,
    as_of_date: Optional[date] = None,
):
    """
    Build complete Loan Report data.

    Important:
    Existing loan-service calculation functions are used
    for principal, interest and outstanding calculations.
    """

    # -----------------------------------------------------
    # AS OF DATE
    # -----------------------------------------------------

    report_as_of_date = (
        as_of_date
        or date_to
        or date.today()
    )

    # -----------------------------------------------------
    # COMPANY
    # -----------------------------------------------------

    company = (
        db.query(Company)
        .filter(
            Company.id == company_id
        )
        .first()
    )

    if not company:
        raise ValueError(
            "Company not found."
        )

    # -----------------------------------------------------
    # BASE QUERY
    # -----------------------------------------------------

    query = (
        db.query(Loan)
        .filter(
            Loan.company_id == company_id
        )
    )

    # -----------------------------------------------------
    # DATE FILTER
    #
    # Date filter is applied to loan start date.
    # -----------------------------------------------------

    if date_from:
        query = query.filter(
            Loan.start_date >= date_from
        )

    if date_to:
        query = query.filter(
            Loan.start_date <= date_to
        )

    # -----------------------------------------------------
    # DIRECTION
    # -----------------------------------------------------

    if (
        direction
        and direction != "all"
    ):
        query = query.filter(
            Loan.direction == direction
        )

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    if (
        report_status
        and report_status != "all"
    ):
        query = query.filter(
            Loan.status == report_status
        )

    # -----------------------------------------------------
    # SEARCH
    #
    # Search:
    # - person name
    # - mobile
    # - address
    # -----------------------------------------------------

    if search and search.strip():

        search_value = (
            f"%{search.strip()}%"
        )

        query = query.filter(
            Loan.person_name.ilike(
                search_value
            )
            |
            Loan.person_mobile.ilike(
                search_value
            )
            |
            Loan.person_address.ilike(
                search_value
            )
        )

    # -----------------------------------------------------
    # ORDER
    # -----------------------------------------------------

    loans = (
        query
        .order_by(
            Loan.start_date.desc(),
            Loan.id.desc(),
        )
        .all()
    )

    # -----------------------------------------------------
    # SUMMARY VARIABLES
    # -----------------------------------------------------

    total_loans = 0

    active_loans = 0
    partially_settled_loans = 0
    closed_loans = 0
    cancelled_loans = 0

    given_loans = 0
    taken_loans = 0

    total_principal = 0
    total_disbursed = 0

    principal_paid_total = 0
    interest_paid_total = 0
    discount_total = 0

    principal_outstanding_total = 0
    interest_outstanding_total = 0
    total_outstanding_total = 0

    cash_disbursed_total = 0
    upi_disbursed_total = 0

    cash_repaid_total = 0
    upi_repaid_total = 0

    total_repayments = 0

    unique_persons = set()

    report_items = []

    # -----------------------------------------------------
    # LOAN PROCESSING
    # -----------------------------------------------------

    for loan in loans:

        # -------------------------------------------------
        # Transactions only up to report date
        # -------------------------------------------------

        transactions = (
            get_transactions_for_loan(
                db=db,
                company_id=company_id,
                loan_id=loan.id,
                end_date=report_as_of_date,
            )
        )

        # -------------------------------------------------
        # Principal
        # -------------------------------------------------

        principal_amount = _safe_int(
            loan.principal_amount
        )

        principal_paid = _safe_int(
            get_principal_paid(
                transactions
            )
        )

        principal_outstanding = _safe_int(
            calculate_outstanding_principal(
                loan=loan,
                transactions=transactions,
            )
        )

        # -------------------------------------------------
        # Interest
        # -------------------------------------------------

        interest_calculated = _safe_int(
            calculate_automatic_interest(
                db=db,
                company_id=company_id,
                loan=loan,
                transaction_date=report_as_of_date,
            )
        )

        interest_paid = _safe_int(
            get_interest_paid(
                transactions
            )
        )

        discount = _safe_int(
            get_total_discount(
                transactions
            )
        )

        interest_outstanding = max(
            interest_calculated
            - interest_paid
            - discount,
            0,
        )

        # -------------------------------------------------
        # Actual repayment
        # -------------------------------------------------

        total_paid = _safe_int(
            get_total_payment_amount(
                transactions
            )
        )

        # -------------------------------------------------
        # Total outstanding
        # -------------------------------------------------

        total_outstanding = (
            principal_outstanding
            + interest_outstanding
        )

        # -------------------------------------------------
        # Disbursement
        # -------------------------------------------------

        total_disbursed = (
            _get_disbursement_amount(
                transactions
            )
        )

        cash_disbursed = (
            _get_disbursement_cash(
                transactions
            )
        )

        upi_disbursed = (
            _get_disbursement_upi(
                transactions
            )
        )

        # -------------------------------------------------
        # Repayments
        # -------------------------------------------------

        cash_repaid = (
            _get_repayment_cash(
                transactions
            )
        )

        upi_repaid = (
            _get_repayment_upi(
                transactions
            )
        )

        # -------------------------------------------------
        # Skip loans that have no applicable transactions
        # only when report date is before loan start.
        # Normally this will not happen because start date
        # filtering prevents it.
        # -------------------------------------------------

        # -------------------------------------------------
        # Summary counts
        # -------------------------------------------------

        total_loans += 1

        if loan.status == "active":
            active_loans += 1

        elif loan.status == "partially_settled":
            partially_settled_loans += 1

        elif loan.status == "closed":
            closed_loans += 1

        elif loan.status == "cancelled":
            cancelled_loans += 1

        # -------------------------------------------------
        # Direction counts
        # -------------------------------------------------

        if loan.direction == "given":
            given_loans += 1

        elif loan.direction == "taken":
            taken_loans += 1

        # -------------------------------------------------
        # Financial totals
        # -------------------------------------------------

        total_principal += principal_amount

        total_disbursed += total_disbursed

        principal_paid_total += principal_paid
        interest_paid_total += interest_paid
        discount_total += discount

        principal_outstanding_total += (
            principal_outstanding
        )

        interest_outstanding_total += (
            interest_outstanding
        )

        total_outstanding_total += (
            total_outstanding
        )

        cash_disbursed_total += (
            cash_disbursed
        )

        upi_disbursed_total += (
            upi_disbursed
        )

        cash_repaid_total += (
            cash_repaid
        )

        upi_repaid_total += (
            upi_repaid
        )

        total_repayments += total_paid

        # -------------------------------------------------
        # Unique person
        # -------------------------------------------------

        person_key = (
            loan.person_mobile
            or loan.person_name
            or f"loan-{loan.id}"
        )

        unique_persons.add(
            person_key
        )

        # -------------------------------------------------
        # Report item
        # -------------------------------------------------

        report_items.append(
            {
                "id": loan.id,

                "person_name": (
                    loan.person_name
                    or "Unknown"
                ),

                "person_mobile": (
                    loan.person_mobile
                ),

                "person_address": (
                    loan.person_address
                ),

                "direction": loan.direction,

                "principal_amount": (
                    principal_amount
                ),

                "interest_rate": (
                    _safe_float(
                        loan.interest_rate
                    )
                ),

                "interest_type": (
                    loan.interest_type
                ),

                "start_date": (
                    loan.start_date
                ),

                "due_date": (
                    loan.due_date
                ),

                "status": (
                    loan.status
                ),

                "total_disbursed": (
                    total_disbursed
                ),

                "principal_paid": (
                    principal_paid
                ),

                "interest_paid": (
                    interest_paid
                ),

                "discount": (
                    discount
                ),

                "principal_outstanding": (
                    principal_outstanding
                ),

                "interest_outstanding": (
                    interest_outstanding
                ),

                "total_paid": (
                    total_paid
                ),

                "total_outstanding": (
                    total_outstanding
                ),

                "cash_disbursed": (
                    cash_disbursed
                ),

                "upi_disbursed": (
                    upi_disbursed
                ),

                "cash_repaid": (
                    cash_repaid
                ),

                "upi_repaid": (
                    upi_repaid
                ),

                "transaction_count": (
                    len(transactions)
                ),

                "last_transaction_date": (
                    _get_last_transaction_date(
                        transactions
                    )
                ),
            }
        )

    # -----------------------------------------------------
    # FINAL RESPONSE
    # -----------------------------------------------------

    return {
        "company_id": company.id,
        "company_name": company.company_name,
        "logo_url": company.logo_url,

        "as_of_date": report_as_of_date,

        "summary": {
            "total_loans": total_loans,

            "active_loans": active_loans,
            "partially_settled_loans": (
                partially_settled_loans
            ),
            "closed_loans": closed_loans,
            "cancelled_loans": cancelled_loans,

            "given_loans": given_loans,
            "taken_loans": taken_loans,

            "total_principal": total_principal,
            "total_disbursed": total_disbursed,

            "principal_paid": (
                principal_paid_total
            ),
            "interest_paid": (
                interest_paid_total
            ),
            "discount": discount_total,

            "principal_outstanding": (
                principal_outstanding_total
            ),
            "interest_outstanding": (
                interest_outstanding_total
            ),
            "total_outstanding": (
                total_outstanding_total
            ),

            "cash_disbursed": (
                cash_disbursed_total
            ),
            "upi_disbursed": (
                upi_disbursed_total
            ),

            "cash_repaid": (
                cash_repaid_total
            ),
            "upi_repaid": (
                upi_repaid_total
            ),

            "total_repayments": (
                total_repayments
            ),

            "unique_persons": (
                len(unique_persons)
            ),
        },

        "items": report_items,

        "total_records": len(
            report_items
        ),
    }


# =========================================================
# PAGINATED REPORT
# =========================================================

def get_loan_report(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    direction: str = "all",
    report_status: str = "all",
    search: Optional[str] = None,
    as_of_date: Optional[date] = None,
    page: int = 1,
    page_size: int = 10,
):
    """
    Get paginated Loan Report.
    """

    page = max(
        page,
        1,
    )

    page_size = min(
        max(page_size, 1),
        100,
    )

    offset = (
        page - 1
    ) * page_size

    report = _build_loan_report_data(
        db=db,
        company_id=company_id,

        date_from=date_from,
        date_to=date_to,

        direction=direction,
        report_status=report_status,

        search=search,

        as_of_date=as_of_date,
    )

    total_records = report[
        "total_records"
    ]

    total_pages = (
        ceil(
            total_records
            / page_size
        )
        if total_records > 0
        else 0
    )

    report["items"] = report[
        "items"
    ][
        offset:
        offset + page_size
    ]

    report["page"] = page
    report["page_size"] = page_size
    report["total_pages"] = total_pages

    return report


# =========================================================
# EXPORT DATA
# =========================================================

def get_loan_report_export_data(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    direction: str = "all",
    report_status: str = "all",
    search: Optional[str] = None,
    as_of_date: Optional[date] = None,
):
    """
    Complete unpaginated report data for Excel/PDF.
    """

    return _build_loan_report_data(
        db=db,
        company_id=company_id,

        date_from=date_from,
        date_to=date_to,

        direction=direction,
        report_status=report_status,

        search=search,

        as_of_date=as_of_date,
    )