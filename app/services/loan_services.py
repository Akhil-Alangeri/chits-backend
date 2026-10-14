from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.admin.loan import Loan
from app.models.admin.loan_transaction import LoanTransaction
from app.services.audit_log_service import (
    create_audit_log,
    snapshot_model,
)


# =========================================================
# CONSTANTS
# =========================================================

ZERO = Decimal("0.00")
ONE = Decimal("1")
ONE_HUNDRED = Decimal("100")
THIRTY_POINT_FOUR_FOUR = Decimal("30.44")
TWO_DECIMAL = Decimal("0.01")


LOAN_AUDIT_FIELDS = [
    "id",
    "person_name",
    "person_mobile",
    "direction",
    "principal_amount",
    "interest_rate",
    "interest_type",
    "start_date",
    "due_date",
    "status",
]

LOAN_TRANSACTION_AUDIT_FIELDS = [
    "id",
    "loan_id",
    "transaction_date",
    "transaction_type",
    "principal_amount",
    "interest_amount",
    "discount",
    "upi_amount",
    "cash_amount",
    "reference",
]


def _loan_snapshot(loan: Loan) -> dict:
    return snapshot_model(
        loan,
        LOAN_AUDIT_FIELDS,
    )


def _loan_transaction_snapshot(
    transaction: LoanTransaction,
) -> dict:
    return snapshot_model(
        transaction,
        LOAN_TRANSACTION_AUDIT_FIELDS,
    )


# =========================================================
# MONEY
# =========================================================

def money(
    value: Decimal | int | float | None,
) -> Decimal:
    """
    Normalize a numeric value to 2 decimal places.
    """

    if value is None:
        return ZERO

    return Decimal(value).quantize(
        TWO_DECIMAL,
        rounding=ROUND_HALF_UP,
    )


# =========================================================
# GET LOAN
# =========================================================

def get_loan_for_company(
    db: Session,
    company_id: int,
    loan_id: int,
):
    """
    Fetch a loan only inside the current company.
    """

    return (
        db.query(Loan)
        .filter(
            Loan.id == loan_id,
            Loan.company_id == company_id,
        )
        .first()
    )


# =========================================================
# GET TRANSACTIONS
# =========================================================

def get_transactions_for_loan(
    db: Session,
    company_id: int,
    loan_id: int,
    end_date: date | None = None,
) -> list[LoanTransaction]:
    """
    Fetch transactions for a company-scoped loan.

    When end_date is supplied, only transactions up to
    that date are returned.
    """

    query = (
        db.query(LoanTransaction)
        .filter(
            LoanTransaction.company_id == company_id,
            LoanTransaction.loan_id == loan_id,
        )
    )

    if end_date is not None:
        query = query.filter(
            LoanTransaction.transaction_date <= end_date,
        )

    return (
        query
        .order_by(
            LoanTransaction.transaction_date.asc(),
            LoanTransaction.id.asc(),
        )
        .all()
    )


# =========================================================
# PRINCIPAL PAID
# =========================================================

def get_principal_paid(
    transactions: list[LoanTransaction],
) -> Decimal:
    """
    Total principal repaid.
    """

    total = ZERO

    for transaction in transactions:
        if transaction.transaction_type != "principal_repayment":
            continue

        total += Decimal(
            transaction.principal_amount or ZERO
        )

    return money(total)


# =========================================================
# OUTSTANDING PRINCIPAL
# =========================================================

def calculate_outstanding_principal(
    loan: Loan,
    transactions: list[LoanTransaction],
) -> Decimal:
    """
    Original loan principal minus principal repayments.
    """

    principal = Decimal(
        loan.principal_amount or ZERO
    )

    principal_paid = get_principal_paid(
        transactions
    )

    return max(
        money(
            principal - principal_paid
        ),
        ZERO,
    )


# =========================================================
# GOOGLE SHEET MONTH CALCULATION
# =========================================================

def calculate_sheet_months(
    start_date: date,
    end_date: date,
) -> int:
    """
    Exact business equivalent of:

        ROUND(
            (end_date - start_date) / 30.44
        )

    Google Sheet formula:

        ((rate / 100) * principal)
        * ROUND(days / 30.44)

    Examples:

        15 days -> 0
        16 days -> 1
        38 days -> 1
        46 days -> 2
    """

    if end_date <= start_date:
        return 0

    days = (
        end_date - start_date
    ).days

    months = (
        Decimal(days)
        / THIRTY_POINT_FOUR_FOUR
    ).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    return max(
        int(months),
        0,
    )


# =========================================================
# GOOGLE SHEET MONTHLY INTEREST
# =========================================================

def calculate_sheet_interest(
    principal: Decimal,
    interest_rate: Decimal,
    start_date: date,
    end_date: date,
) -> Decimal:
    """
    Google Sheet equivalent:

        ((rate / 100) * principal)
        * ROUND(
            (end_date - start_date) / 30.44
        )

    This is the monthly-interest calculation.
    """

    principal = Decimal(
        principal or ZERO
    )

    interest_rate = Decimal(
        interest_rate or ZERO
    )

    if principal <= ZERO:
        return ZERO

    if interest_rate <= ZERO:
        return ZERO

    months = calculate_sheet_months(
        start_date=start_date,
        end_date=end_date,
    )

    if months <= 0:
        return ZERO

    monthly_interest = (
        principal
        * interest_rate
        / ONE_HUNDRED
    )

    return money(
        monthly_interest
        * Decimal(months)
    )


# =========================================================
# MONTHLY INTEREST FOR CURRENT PRINCIPAL
# =========================================================

def calculate_monthly_interest(
    principal: Decimal,
    interest_rate: Decimal,
) -> Decimal:
    """
    One full month interest.

        principal * rate / 100
    """

    principal = Decimal(
        principal or ZERO
    )

    interest_rate = Decimal(
        interest_rate or ZERO
    )

    if principal <= ZERO:
        return ZERO

    if interest_rate <= ZERO:
        return ZERO

    return money(
        principal
        * interest_rate
        / ONE_HUNDRED
    )


# =========================================================
# FULL YEAR COUNT
# =========================================================

def calculate_years(
    start_date: date,
    end_date: date,
) -> int:
    """
    Count completed calendar years.
    """

    if end_date <= start_date:
        return 0

    years = (
        end_date.year
        - start_date.year
    )

    try:
        anniversary = start_date.replace(
            year=start_date.year + years
        )
    except ValueError:
        # Handles Feb 29 -> Feb 28
        anniversary = date(
            start_date.year + years,
            2,
            28,
        )

    if anniversary > end_date:
        years -= 1

    return max(
        years,
        0,
    )


# =========================================================
# YEARLY INTEREST
# =========================================================

def calculate_yearly_interest(
    principal: Decimal,
    interest_rate: Decimal,
    start_date: date,
    end_date: date,
) -> Decimal:
    """
    Yearly loan interest:

        principal
        * rate
        / 100
        * completed years
    """

    principal = Decimal(
        principal or ZERO
    )

    interest_rate = Decimal(
        interest_rate or ZERO
    )

    if principal <= ZERO:
        return ZERO

    if interest_rate <= ZERO:
        return ZERO

    years = calculate_years(
        start_date=start_date,
        end_date=end_date,
    )

    if years <= 0:
        return ZERO

    return money(
        principal
        * interest_rate
        / ONE_HUNDRED
        * Decimal(years)
    )


# =========================================================
# ONE-TIME INTEREST
# =========================================================

def calculate_one_time_interest(
    principal: Decimal,
    interest_rate: Decimal,
    start_date: date,
    end_date: date,
) -> Decimal:
    """
    One-time interest becomes applicable once the
    loan has passed the start date.

        principal * rate / 100
    """

    if end_date <= start_date:
        return ZERO

    principal = Decimal(
        principal or ZERO
    )

    interest_rate = Decimal(
        interest_rate or ZERO
    )

    if principal <= ZERO:
        return ZERO

    if interest_rate <= ZERO:
        return ZERO

    return money(
        principal
        * interest_rate
        / ONE_HUNDRED
    )


# =========================================================
# INTEREST FOR ONE PRINCIPAL PERIOD
# =========================================================

def calculate_interest_for_period(
    loan: Loan,
    principal: Decimal,
    period_start: date,
    period_end: date,
) -> Decimal:
    """
    Calculate interest for a single principal period.
    """

    if period_end <= period_start:
        return ZERO

    if principal <= ZERO:
        return ZERO

    rate = Decimal(
        loan.interest_rate or ZERO
    )

    if rate <= ZERO:
        return ZERO

    # -----------------------------------------------------
    # MONTHLY
    # -----------------------------------------------------

    if loan.interest_type == "monthly":
        return calculate_sheet_interest(
            principal=principal,
            interest_rate=rate,
            start_date=period_start,
            end_date=period_end,
        )

    # -----------------------------------------------------
    # YEARLY
    # -----------------------------------------------------

    if loan.interest_type == "yearly":
        return calculate_yearly_interest(
            principal=principal,
            interest_rate=rate,
            start_date=period_start,
            end_date=period_end,
        )

    # -----------------------------------------------------
    # ONE TIME
    # -----------------------------------------------------

    if loan.interest_type == "one_time":
        return calculate_one_time_interest(
            principal=principal,
            interest_rate=rate,
            start_date=period_start,
            end_date=period_end,
        )

    return ZERO


# =========================================================
# AUTOMATIC INTEREST
# =========================================================

def calculate_automatic_interest(
    db: Session,
    company_id: int,
    loan: Loan,
    transaction_date: date,
) -> Decimal:
    """
    Calculate total accrued interest up to transaction_date.

    MONTHLY:
        Uses the exact Google Sheet formula.

    When principal repayments happen, the loan is divided
    into principal periods.

    Example:

        01-Aug
        Principal = 100000

        15-Sep
        Principal repayment = 40000

        08-Oct
        Remaining principal = 60000

    Interest:

        01-Aug -> 15-Sep on 100000
        15-Sep -> 08-Oct on 60000

    IMPORTANT:
        Interest payments DO NOT reset the interest period.
        Only principal repayments change the principal period.
    """

    if transaction_date <= loan.start_date:
        return ZERO

    initial_principal = Decimal(
        loan.principal_amount or ZERO
    )

    if initial_principal <= ZERO:
        return ZERO

    rate = Decimal(
        loan.interest_rate or ZERO
    )

    if rate <= ZERO:
        return ZERO

    # =====================================================
    # ONE-TIME
    # =====================================================

    if loan.interest_type == "one_time":

        # Use the principal outstanding on the selected date.
        transactions = get_transactions_for_loan(
            db=db,
            company_id=company_id,
            loan_id=loan.id,
            end_date=transaction_date,
        )

        outstanding_principal = (
            calculate_outstanding_principal(
                loan=loan,
                transactions=transactions,
            )
        )

        return calculate_one_time_interest(
            principal=outstanding_principal,
            interest_rate=rate,
            start_date=loan.start_date,
            end_date=transaction_date,
        )

    # =====================================================
    # YEARLY / MONTHLY WITH PRINCIPAL PERIODS
    # =====================================================

    transactions = get_transactions_for_loan(
        db=db,
        company_id=company_id,
        loan_id=loan.id,
        end_date=transaction_date,
    )

    principal_repayments = [
        transaction
        for transaction in transactions
        if (
            transaction.transaction_type
            == "principal_repayment"
            and transaction.transaction_date
            > loan.start_date
            and transaction.transaction_date
            <= transaction_date
        )
    ]

    principal_repayments.sort(
        key=lambda transaction: (
            transaction.transaction_date,
            transaction.id,
        )
    )

    total_interest = ZERO

    period_start = loan.start_date

    period_principal = initial_principal

    # =====================================================
    # PRINCIPAL PERIODS
    # =====================================================

    for repayment in principal_repayments:

        repayment_date = (
            repayment.transaction_date
        )

        if repayment_date <= period_start:
            continue

        # -----------------------------------------------
        # Interest BEFORE principal reduction.
        # -----------------------------------------------

        period_interest = (
            calculate_interest_for_period(
                loan=loan,
                principal=period_principal,
                period_start=period_start,
                period_end=repayment_date,
            )
        )

        total_interest += period_interest

        # -----------------------------------------------
        # Reduce principal AFTER calculating interest
        # for this period.
        # -----------------------------------------------

        repayment_amount = money(
            repayment.principal_amount
            or ZERO
        )

        period_principal = max(
            money(
                period_principal
                - repayment_amount
            ),
            ZERO,
        )

        period_start = repayment_date

        if period_principal <= ZERO:
            break

    # =====================================================
    # CURRENT PRINCIPAL PERIOD
    # =====================================================

    if (
        period_principal > ZERO
        and period_start < transaction_date
    ):
        total_interest += (
            calculate_interest_for_period(
                loan=loan,
                principal=period_principal,
                period_start=period_start,
                period_end=transaction_date,
            )
        )

    return money(total_interest)


# =========================================================
# INTEREST CASH PAID
# =========================================================

def get_interest_paid(
    transactions: list[LoanTransaction],
) -> Decimal:
    """
    Actual interest money paid through UPI + Cash.

    This intentionally does NOT use interest_amount because
    interest_amount can represent gross interest being settled.

    Actual cash movement is:

        UPI + Cash
    """

    total = ZERO

    for transaction in transactions:

        if (
            transaction.transaction_type
            != "interest_payment"
        ):
            continue

        total += (
            Decimal(
                transaction.upi_amount or ZERO
            )
            + Decimal(
                transaction.cash_amount or ZERO
            )
        )

    return money(total)


# =========================================================
# INTEREST DISCOUNT
# =========================================================

def get_total_discount(
    transactions: list[LoanTransaction],
) -> Decimal:
    """
    Total interest discount given.
    """

    total = ZERO

    for transaction in transactions:

        if (
            transaction.transaction_type
            != "interest_payment"
        ):
            continue

        total += Decimal(
            transaction.discount or ZERO
        )

    return money(total)


# =========================================================
# TOTAL ACTUAL PAYMENT
# =========================================================

def get_total_payment_amount(
    transactions: list[LoanTransaction],
) -> Decimal:
    """
    Total actual payment made through UPI + Cash.

    Disbursements are excluded because they are the original
    loan funding/money movement, not loan repayment.
    """

    total = ZERO

    for transaction in transactions:

        if transaction.transaction_type not in {
            "principal_repayment",
            "interest_payment",
        }:
            continue

        total += (
            Decimal(
                transaction.upi_amount or ZERO
            )
            + Decimal(
                transaction.cash_amount or ZERO
            )
        )

    return money(total)


# =========================================================
# CREATE LOAN
# =========================================================

def create_loan(
    db: Session,
    company_id: int,
    created_by: int | None,
    loan_data,
    ip_address: str | None = None,
    user_agent: str | None = None,
):
    """
    Create a new company-scoped loan.
    """

    # -----------------------------------------------------
    # START DATE
    # -----------------------------------------------------

    if loan_data.start_date is None:
        return {
            "error": "invalid_start_date",
            "message": "Start date is required.",
        }

    # -----------------------------------------------------
    # DUE DATE
    # -----------------------------------------------------

    if (
        loan_data.due_date is not None
        and loan_data.due_date
        < loan_data.start_date
    ):
        return {
            "error": "invalid_due_date",
            "message": (
                "Due date cannot be before start date."
            ),
        }

    # -----------------------------------------------------
    # PRINCIPAL
    # -----------------------------------------------------

    principal_amount = Decimal(
        loan_data.principal_amount
        or ZERO
    )

    if principal_amount <= ZERO:
        return {
            "error": "invalid_principal_amount",
            "message": (
                "Principal amount must be "
                "greater than zero."
            ),
        }

    # -----------------------------------------------------
    # INTEREST RATE
    # -----------------------------------------------------

    interest_rate = Decimal(
        loan_data.interest_rate
        or ZERO
    )

    if interest_rate < ZERO:
        return {
            "error": "invalid_interest_rate",
            "message": (
                "Interest rate cannot be negative."
            ),
        }

    # -----------------------------------------------------
    # CREATE
    # -----------------------------------------------------

    loan = Loan(
        company_id=company_id,
        person_name=loan_data.person_name,
        person_mobile=loan_data.person_mobile,
        person_address=loan_data.person_address,
        notes=loan_data.notes,
        direction=loan_data.direction,
        principal_amount=principal_amount,
        interest_rate=interest_rate,
        interest_type=loan_data.interest_type,
        start_date=loan_data.start_date,
        due_date=loan_data.due_date,
        status="active",
        created_by=created_by,
    )

    db.add(loan)
    db.flush()

    create_audit_log(
        db=db,
        company_id=company_id,
        user_id=created_by,
        action="CREATE",
        module="Loans",
        entity_type="Loan",
        entity_id=loan.id,
        description=(
            f"Created loan #{loan.id} for "
            f"'{loan.person_name}'"
        ),
        new_values=_loan_snapshot(loan),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()

    db.refresh(loan)

    return loan


# =========================================================
# GET ALL LOANS
# =========================================================

def get_loans(
    db: Session,
    company_id: int,
    direction: str | None = None,
    status: str | None = None,
):
    """
    Get all loans for a company.
    """

    query = (
        db.query(Loan)
        .filter(
            Loan.company_id == company_id,
        )
    )

    if direction:
        query = query.filter(
            Loan.direction == direction,
        )

    if status:
        query = query.filter(
            Loan.status == status,
        )

    return (
        query
        .order_by(
            Loan.start_date.desc(),
            Loan.id.desc(),
        )
        .all()
    )


# =========================================================
# UPDATE LOAN
# =========================================================

def update_loan(
    db: Session,
    company_id: int,
    loan_id: int,
    loan_data,
    updated_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
):
    """
    Update a company-scoped loan.
    """

    loan = get_loan_for_company(
        db=db,
        company_id=company_id,
        loan_id=loan_id,
    )

    if not loan:
        return {
            "error": "loan_not_found",
        }

    old_values = _loan_snapshot(loan)

    update_data = loan_data.model_dump(
        exclude_unset=True,
    )

    # -----------------------------------------------------
    # DATE VALIDATION
    # -----------------------------------------------------

    new_start_date = update_data.get(
        "start_date",
        loan.start_date,
    )

    new_due_date = update_data.get(
        "due_date",
        loan.due_date,
    )

    if (
        new_due_date is not None
        and new_start_date is not None
        and new_due_date < new_start_date
    ):
        return {
            "error": "invalid_due_date",
            "message": (
                "Due date cannot be before "
                "start date."
            ),
        }

    # -----------------------------------------------------
    # PRINCIPAL VALIDATION
    # -----------------------------------------------------

    transactions = get_transactions_for_loan(
        db=db,
        company_id=company_id,
        loan_id=loan_id,
    )

    principal_paid = get_principal_paid(
        transactions
    )

    if "principal_amount" in update_data:

        new_principal = Decimal(
            update_data["principal_amount"]
        )

        if new_principal <= ZERO:
            return {
                "error": "invalid_principal_amount",
                "message": (
                    "Principal amount must be "
                    "greater than zero."
                ),
            }

        if new_principal < principal_paid:
            return {
                "error": "principal_below_paid_amount",
                "message": (
                    "Principal amount cannot be "
                    "less than principal already paid."
                ),
            }

    # -----------------------------------------------------
    # INTEREST RATE VALIDATION
    # -----------------------------------------------------

    if "interest_rate" in update_data:

        new_rate = Decimal(
            update_data["interest_rate"]
        )

        if new_rate < ZERO:
            return {
                "error": "invalid_interest_rate",
                "message": (
                    "Interest rate cannot be negative."
                ),
            }

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    if (
        update_data.get("status")
        == "cancelled"
    ):
        update_data["status"] = "cancelled"

    # -----------------------------------------------------
    # UPDATE
    # -----------------------------------------------------

    for field, value in update_data.items():

        setattr(
            loan,
            field,
            value,
        )

    db.flush()

    new_values = _loan_snapshot(loan)
    status_changed = (
        old_values["status"]
        != new_values["status"]
    )

    create_audit_log(
        db=db,
        company_id=company_id,
        user_id=updated_by,
        action=(
            "STATUS_CHANGE"
            if status_changed
            else "UPDATE"
        ),
        module="Loans",
        entity_type="Loan",
        entity_id=loan.id,
        description=(
            f"Changed loan #{loan.id} status from "
            f"'{old_values['status']}' to "
            f"'{new_values['status']}'"
            if status_changed
            else f"Updated loan #{loan.id}"
        ),
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()

    db.refresh(loan)

    return loan


# =========================================================
# CANCEL LOAN
# =========================================================

def cancel_loan(
    db: Session,
    company_id: int,
    loan_id: int,
    cancelled_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
):
    """
    Cancel a loan.
    """

    loan = get_loan_for_company(
        db=db,
        company_id=company_id,
        loan_id=loan_id,
    )

    if not loan:
        return {
            "error": "loan_not_found",
        }

    if loan.status == "closed":
        return {
            "error": "loan_closed",
            "message": (
                "A closed loan cannot be cancelled."
            ),
        }

    if loan.status == "cancelled":
        return {
            "error": "loan_already_cancelled",
            "message": (
                "Loan is already cancelled."
            ),
        }

    old_values = _loan_snapshot(loan)

    loan.status = "cancelled"

    db.flush()

    new_values = _loan_snapshot(loan)

    create_audit_log(
        db=db,
        company_id=company_id,
        user_id=cancelled_by,
        action="STATUS_CHANGE",
        module="Loans",
        entity_type="Loan",
        entity_id=loan.id,
        description=(
            f"Cancelled loan #{loan.id} for "
            f"'{loan.person_name}'"
        ),
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()

    db.refresh(loan)

    return loan


# =========================================================
# CREATE TRANSACTION
# =========================================================

def create_loan_transaction(
    db: Session,
    company_id: int,
    loan_id: int,
    created_by: int | None,
    transaction_data,
    ip_address: str | None = None,
    user_agent: str | None = None,
):
    """
    Create a loan transaction.

    Supported transaction types:

        disbursement
        principal_repayment
        interest_payment

    Payment split:

        UPI + Cash
    """

    # =====================================================
    # GET LOAN
    # =====================================================

    loan = get_loan_for_company(
        db=db,
        company_id=company_id,
        loan_id=loan_id,
    )

    if not loan:
        return {
            "error": "loan_not_found",
        }

    if loan.status == "cancelled":
        return {
            "error": "loan_cancelled",
            "message": (
                "Transactions cannot be added "
                "to a cancelled loan."
            ),
        }

    old_loan_values = _loan_snapshot(loan)

    # =====================================================
    # BASIC DATA
    # =====================================================

    transaction_type = (
        transaction_data.transaction_type
    )

    transaction_date = (
        transaction_data.transaction_date
    )

    principal_amount = money(
        transaction_data.principal_amount
        or ZERO
    )

    discount = money(
        transaction_data.discount
        or ZERO
    )

    upi_amount = money(
        transaction_data.upi_amount
        or ZERO
    )

    cash_amount = money(
        transaction_data.cash_amount
        or ZERO
    )

    payment_amount = money(
        upi_amount
        + cash_amount
    )

    # =====================================================
    # DATE VALIDATION
    # =====================================================

    if transaction_date < loan.start_date:
        return {
            "error": "invalid_transaction_date",
            "message": (
                "Transaction date cannot be before "
                "the loan start date."
            ),
        }

    if transaction_date > date.today():
        return {
            "error": "invalid_transaction_date",
            "message": (
                "Transaction date cannot be "
                "in the future."
            ),
        }

    # =====================================================
    # EXISTING TRANSACTIONS UP TO THIS DATE
    # =====================================================

    transactions_up_to_date = (
        get_transactions_for_loan(
            db=db,
            company_id=company_id,
            loan_id=loan_id,
            end_date=transaction_date,
        )
    )

    current_principal_balance = (
        calculate_outstanding_principal(
            loan=loan,
            transactions=transactions_up_to_date,
        )
    )

    # =====================================================
    # DISBURSEMENT
    # =====================================================

    if transaction_type == "disbursement":

        # -------------------------------------------------
        # Only one initial disbursement
        # -------------------------------------------------

        existing_disbursement = next(
            (
                transaction
                for transaction
                in transactions_up_to_date
                if transaction.transaction_type
                == "disbursement"
            ),
            None,
        )

        if existing_disbursement:
            return {
                "error": "disbursement_already_exists",
                "message": (
                    "A disbursement already exists "
                    "for this loan."
                ),
            }

        if principal_amount <= ZERO:
            return {
                "error": "invalid_disbursement_amount",
                "message": (
                    "Disbursement amount must be "
                    "greater than zero."
                ),
            }

        if discount > ZERO:
            return {
                "error": "invalid_discount",
                "message": (
                    "Discount is not allowed "
                    "on a disbursement."
                ),
            }

        if payment_amount <= ZERO:
            return {
                "error": "invalid_payment_amount",
                "message": (
                    "UPI amount or cash amount "
                    "must be greater than zero."
                ),
            }

        if payment_amount != principal_amount:
            return {
                "error": "payment_amount_mismatch",
                "message": (
                    "UPI amount + cash amount must "
                    "equal disbursement amount."
                ),
            }

        interest_amount = ZERO

    # =====================================================
    # PRINCIPAL REPAYMENT
    # =====================================================

    elif transaction_type == "principal_repayment":

        if principal_amount <= ZERO:
            return {
                "error": "invalid_principal_repayment",
                "message": (
                    "Principal repayment must be "
                    "greater than zero."
                ),
            }

        if (
            principal_amount
            > current_principal_balance
        ):
            return {
                "error": (
                    "principal_repayment_exceeds_balance"
                ),
                "message": (
                    "Principal repayment cannot exceed "
                    "the outstanding principal."
                ),
            }

        if discount > ZERO:
            return {
                "error": "invalid_discount",
                "message": (
                    "Discount is not allowed "
                    "on a principal repayment."
                ),
            }

        if payment_amount <= ZERO:
            return {
                "error": "invalid_payment_amount",
                "message": (
                    "UPI amount or cash amount "
                    "must be greater than zero."
                ),
            }

        if payment_amount != principal_amount:
            return {
                "error": "payment_amount_mismatch",
                "message": (
                    "UPI amount + cash amount must "
                    "equal principal repayment amount."
                ),
            }

        interest_amount = ZERO

    # =====================================================
    # INTEREST PAYMENT
    # =====================================================

    elif transaction_type == "interest_payment":

        if principal_amount > ZERO:
            return {
                "error": "invalid_interest_principal",
                "message": (
                    "Principal amount must be zero "
                    "for an interest payment."
                ),
            }

        # -------------------------------------------------
        # Calculate total interest accrued up to payment date
        # -------------------------------------------------

        calculated_interest = (
            calculate_automatic_interest(
                db=db,
                company_id=company_id,
                loan=loan,
                transaction_date=transaction_date,
            )
        )

        # -------------------------------------------------
        # Already settled interest before this transaction
        #
        # IMPORTANT:
        # We use actual payment + discount.
        # We do NOT use interest_amount because that may
        # represent gross interest allocation.
        # -------------------------------------------------

        previous_interest_paid = (
            get_interest_paid(
                transactions_up_to_date
            )
        )

        previous_discount = (
            get_total_discount(
                transactions_up_to_date
            )
        )

        interest_outstanding = max(
            money(
                calculated_interest
                - previous_interest_paid
                - previous_discount
            ),
            ZERO,
        )

        if interest_outstanding <= ZERO:
            return {
                "error": "no_interest_due",
                "message": (
                    "No interest is currently due."
                ),
            }

        # -------------------------------------------------
        # Discount
        # -------------------------------------------------

        if discount > interest_outstanding:
            return {
                "error": "discount_exceeds_interest",
                "message": (
                    "Discount cannot exceed "
                    "outstanding interest."
                ),
            }

        net_interest_payable = money(
            interest_outstanding
            - discount
        )

        if net_interest_payable <= ZERO:
            return {
                "error": "invalid_interest_payment",
                "message": (
                    "Interest payable must be "
                    "greater than zero."
                ),
            }

        # -------------------------------------------------
        # Actual payment
        #
        # Partial interest payment is allowed.
        # -------------------------------------------------

        if payment_amount <= ZERO:
            return {
                "error": "invalid_payment_amount",
                "message": (
                    "UPI amount or cash amount "
                    "must be greater than zero."
                ),
            }

        if payment_amount > net_interest_payable:
            return {
                "error": "payment_exceeds_interest",
                "message": (
                    "UPI amount + cash amount cannot "
                    "exceed the interest payable."
                ),
            }

        # -------------------------------------------------
        # Gross interest being settled in this transaction
        #
        # Example:
        #
        # Outstanding = 3000
        # Discount = 500
        # Paid = 1500
        #
        # Interest settled by this transaction = 2000
        #
        # 1500 actual payment
        # 500 discount
        # -------------------------------------------------

        interest_amount = money(
            payment_amount
            + discount
        )

        principal_amount = ZERO

    # =====================================================
    # INVALID TYPE
    # =====================================================

    else:
        return {
            "error": "invalid_transaction_type",
            "message": (
                "Unsupported transaction type."
            ),
        }

    # =====================================================
    # CREATE TRANSACTION
    # =====================================================

    transaction = LoanTransaction(
        company_id=company_id,
        loan_id=loan_id,
        transaction_date=transaction_date,
        transaction_type=transaction_type,
        principal_amount=principal_amount,
        interest_amount=money(
            interest_amount
        ),
        discount=discount,
        upi_amount=upi_amount,
        cash_amount=cash_amount,
        reference=transaction_data.reference,
        notes=transaction_data.notes,
        created_by=created_by,
    )

    db.add(transaction)

    db.flush()

    # =====================================================
    # UPDATE STATUS
    # =====================================================

    updated_transactions = (
        get_transactions_for_loan(
            db=db,
            company_id=company_id,
            loan_id=loan_id,
        )
    )

    updated_principal_balance = (
        calculate_outstanding_principal(
            loan=loan,
            transactions=updated_transactions,
        )
    )

    updated_interest_calculated = (
        calculate_automatic_interest(
            db=db,
            company_id=company_id,
            loan=loan,
            transaction_date=date.today(),
        )
    )

    updated_interest_paid = (
        get_interest_paid(
            updated_transactions
        )
    )

    updated_discount = (
        get_total_discount(
            updated_transactions
        )
    )

    updated_interest_outstanding = max(
        money(
            updated_interest_calculated
            - updated_interest_paid
            - updated_discount
        ),
        ZERO,
    )

    # -----------------------------------------------------
    # CLOSED
    # -----------------------------------------------------

    if (
        updated_principal_balance <= ZERO
        and updated_interest_outstanding <= ZERO
    ):
        loan.status = "closed"

    # -----------------------------------------------------
    # PARTIALLY SETTLED
    # -----------------------------------------------------

    elif (
        updated_principal_balance
        < money(
            Decimal(
                loan.principal_amount
                or ZERO
            )
        )
        or updated_interest_paid > ZERO
        or updated_discount > ZERO
    ):
        loan.status = "partially_settled"

    # -----------------------------------------------------
    # ACTIVE
    # -----------------------------------------------------

    else:
        loan.status = "active"

    db.flush()

    create_audit_log(
        db=db,
        company_id=company_id,
        user_id=created_by,
        action="CREATE",
        module="Loan Transactions",
        entity_type="LoanTransaction",
        entity_id=transaction.id,
        description=(
            f"Created {transaction.transaction_type} "
            f"transaction #{transaction.id} for loan #{loan.id}"
        ),
        new_values=_loan_transaction_snapshot(transaction),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    new_loan_values = _loan_snapshot(loan)

    if old_loan_values["status"] != new_loan_values["status"]:
        create_audit_log(
            db=db,
            company_id=company_id,
            user_id=created_by,
            action="STATUS_CHANGE",
            module="Loans",
            entity_type="Loan",
            entity_id=loan.id,
            description=(
                f"Changed loan #{loan.id} status from "
                f"'{old_loan_values['status']}' to "
                f"'{new_loan_values['status']}'"
            ),
            old_values=old_loan_values,
            new_values=new_loan_values,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    db.commit()

    db.refresh(transaction)

    return transaction


# =========================================================
# GET LOAN TRANSACTIONS
# =========================================================

def get_loan_transactions(
    db: Session,
    company_id: int,
    loan_id: int,
):
    """
    Get all transactions for a company-scoped loan.
    """

    loan = get_loan_for_company(
        db=db,
        company_id=company_id,
        loan_id=loan_id,
    )

    if not loan:
        return {
            "error": "loan_not_found",
        }

    return get_transactions_for_loan(
        db=db,
        company_id=company_id,
        loan_id=loan_id,
    )


# =========================================================
# SUMMARY
# =========================================================

def get_loan_summary(
    db: Session,
    company_id: int,
    loan_id: int,
):
    """
    Return current financial state of the loan.

    principal_amount
        Original loan principal.

    principal_paid
        Actual principal repaid.

    principal_balance
        Remaining principal.

    monthly_interest
        One full month interest on the CURRENT
        outstanding principal.

    loan_age_days
        Number of days since loan start.

    loan_age_months
        Google Sheet style rounded month count.

    interest_calculated
        Total interest accrued up to today.

    discount
        Total discount given against interest.

    interest_paid
        Actual interest money paid through
        UPI + Cash.

    interest_outstanding
        Accrued interest minus actual interest paid
        minus discount.

    total_paid
        Actual principal + interest money paid,
        excluding disbursement.

    total_outstanding
        Principal balance + interest outstanding.
    """

    loan = get_loan_for_company(
        db=db,
        company_id=company_id,
        loan_id=loan_id,
    )

    if not loan:
        return {
            "error": "loan_not_found",
        }

    today = date.today()

    transactions = get_transactions_for_loan(
        db=db,
        company_id=company_id,
        loan_id=loan_id,
    )

    # =====================================================
    # PRINCIPAL
    # =====================================================

    principal_amount = money(
        Decimal(
            loan.principal_amount
            or ZERO
        )
    )

    principal_paid = get_principal_paid(
        transactions
    )

    principal_balance = max(
        money(
            principal_amount
            - principal_paid
        ),
        ZERO,
    )

    # =====================================================
    # MONTHLY INTEREST
    # =====================================================

    monthly_interest = ZERO

    if loan.interest_type == "monthly":
        monthly_interest = (
            calculate_monthly_interest(
                principal=principal_balance,
                interest_rate=Decimal(
                    loan.interest_rate
                    or ZERO
                ),
            )
        )

    # =====================================================
    # LOAN AGE
    # =====================================================

    loan_age_days = max(
        (
            today - loan.start_date
        ).days,
        0,
    )

    loan_age_months = (
        calculate_sheet_months(
            start_date=loan.start_date,
            end_date=today,
        )
    )

    # =====================================================
    # INTEREST
    # =====================================================

    interest_calculated = (
        calculate_automatic_interest(
            db=db,
            company_id=company_id,
            loan=loan,
            transaction_date=today,
        )
    )

    interest_paid = get_interest_paid(
        transactions
    )

    discount = get_total_discount(
        transactions
    )

    # -----------------------------------------------------
    # Outstanding interest
    # -----------------------------------------------------

    interest_outstanding = max(
        money(
            interest_calculated
            - interest_paid
            - discount
        ),
        ZERO,
    )

    # =====================================================
    # TOTAL PAID
    # =====================================================

    total_paid = get_total_payment_amount(
        transactions
    )

    # =====================================================
    # TOTAL OUTSTANDING
    # =====================================================

    total_outstanding = money(
        principal_balance
        + interest_outstanding
    )

    # =====================================================
    # RESULT
    # =====================================================

    return {
        "principal_amount": money(
            principal_amount
        ),

        "principal_paid": money(
            principal_paid
        ),

        "principal_balance": money(
            principal_balance
        ),

        "interest_rate": money(
            Decimal(
                loan.interest_rate
                or ZERO
            )
        ),

        "interest_type": loan.interest_type,

        "monthly_interest": money(
            monthly_interest
        ),

        "loan_age_days": loan_age_days,

        "loan_age_months": loan_age_months,

        "interest_calculated": money(
            interest_calculated
        ),

        "discount": money(
            discount
        ),

        "interest_paid": money(
            interest_paid
        ),

        "interest_outstanding": money(
            interest_outstanding
        ),

        "total_paid": money(
            total_paid
        ),

        "total_outstanding": money(
            total_outstanding
        ),
    }


# =========================================================
# DETAIL
# =========================================================

def get_loan_detail(
    db: Session,
    company_id: int,
    loan_id: int,
):
    """
    Return complete loan details including:

        loan information
        financial summary
        transactions
    """

    loan = get_loan_for_company(
        db=db,
        company_id=company_id,
        loan_id=loan_id,
    )

    if not loan:
        return {
            "error": "loan_not_found",
        }

    summary = get_loan_summary(
        db=db,
        company_id=company_id,
        loan_id=loan_id,
    )

    transactions = get_loan_transactions(
        db=db,
        company_id=company_id,
        loan_id=loan_id,
    )

    return {
        "id": loan.id,
        "company_id": loan.company_id,

        "person_name": loan.person_name,
        "person_mobile": loan.person_mobile,
        "person_address": loan.person_address,

        "notes": loan.notes,

        "direction": loan.direction,

        "principal_amount": loan.principal_amount,

        "interest_rate": loan.interest_rate,
        "interest_type": loan.interest_type,

        "start_date": loan.start_date,
        "due_date": loan.due_date,

        "status": loan.status,

        "created_by": loan.created_by,
        "created_at": loan.created_at,
        "updated_at": loan.updated_at,

        "summary": summary,

        "transactions": transactions,
    }
