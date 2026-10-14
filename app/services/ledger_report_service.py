from app.services.entitlement_service import has_company_feature
from datetime import date
from decimal import Decimal
from math import ceil
from typing import Optional

from sqlalchemy.orm import Session

from app.models.admin.company import Company
from app.models.admin.payment_transaction import PaymentTransaction
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_group import ChitGroup
from app.models.admin.loan import Loan
from app.models.admin.loan_transaction import LoanTransaction
from app.models.admin.expenses import Expense
from app.models.admin.chitlift import ChitLift


# =========================================================
# CONSTANTS
# =========================================================

ZERO = Decimal("0")


# =========================================================
# MONEY HELPER
# =========================================================

def money(value) -> Decimal:
    """
    Safely convert a database numeric value into Decimal.
    """

    try:
        return Decimal(str(value or 0))
    except Exception:
        return ZERO


# =========================================================
# DATE HELPER
# =========================================================

def _date(value) -> Optional[date]:
    """
    Normalize date values.
    """

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    return None


# =========================================================
# PAYMENT METHOD HELPER
# =========================================================

def _method(value: Optional[str]) -> str:
    """
    Normalize payment method.
    """

    value = (value or "").strip().lower()

    return value or "other"


# =========================================================
# PAYMENT METHOD FILTER
# =========================================================

def _method_matches(
    method: str,
    requested: Optional[str],
) -> bool:

    if not requested or requested == "all":
        return True

    if requested == "other":
        return method not in {
            "cash",
            "upi",
            "bank_transfer",
            "cheque",
        }

    return method == requested


# =========================================================
# SEARCH FILTER
# =========================================================

def _matches_search(
    item: dict,
    search: Optional[str],
) -> bool:

    if not search:
        return True

    needle = search.strip().lower()

    if not needle:
        return True

    haystack = " ".join(
        str(item.get(key) or "")
        for key in (
            "description",
            "reference",
            "person_name",
            "chit_name",
            "transaction_type",
            "loan_direction",
            "payment_method",
        )
    ).lower()

    return needle in haystack


# =========================================================
# ADD LEDGER ROW
# =========================================================

def _add_row(
    rows: list,
    *,
    row_id: str,
    transaction_date,
    transaction_type: str,
    description: str,
    reference: Optional[str],
    person_name: Optional[str],
    chit_name: Optional[str],
    loan_direction: Optional[str],
    payment_method: str,
    amount,
    cash_amount,
    bank_amount,
    flow: str,
):

    amount = money(amount)

    cash_amount = money(cash_amount)

    bank_amount = money(bank_amount)

    rows.append(
        {
            "id": row_id,

            "date": _date(transaction_date),

            "transaction_type": transaction_type,

            "description": description,

            "reference": reference,

            "person_name": person_name,

            "chit_name": chit_name,

            "loan_direction": loan_direction,

            "payment_method": payment_method,

            "amount": amount,

            "cash_amount": cash_amount,

            "bank_amount": bank_amount,

            "money_flow": flow,
        }
    )


# =========================================================
# BUILD ALL LEDGER ROWS
# =========================================================

def _build_ledger_rows(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    transaction_type: str = "all",
    payment_method: str = "all",
    search: Optional[str] = None,
):

    rows = []

    # =====================================================
    # 1. CHIT COLLECTIONS
    # =====================================================

    if transaction_type in {
        "all",
        "chit_collection",
    }:

        query = (
            db.query(
                PaymentTransaction,
                ChitInstallment,
                ChitMember,
                ChitGroup,
            )
            .join(
                ChitInstallment,
                ChitInstallment.id
                == PaymentTransaction.installment_id,
            )
            .join(
                ChitMember,
                ChitMember.id
                == ChitInstallment.chit_member_id,
            )
            .join(
                ChitGroup,
                ChitGroup.id
                == ChitMember.chit_id,
            )
            .filter(
                ChitGroup.company_id == company_id,

                ChitMember.status.in_(
                    [
                        "confirmed",
                        "active",
                    ]
                ),
            )
        )

        if date_from:
            query = query.filter(
                PaymentTransaction.payment_date
                >= date_from
            )

        if date_to:
            query = query.filter(
                PaymentTransaction.payment_date
                <= date_to
            )

        collection_rows = query.all()

        for (
            payment,
            installment,
            member,
            chit,
        ) in collection_rows:

            method = _method(
                payment.payment_method
            )

            if not _method_matches(
                method,
                payment_method,
            ):
                continue

            _add_row(
                rows,

                row_id=f"collection:{payment.id}",

                transaction_date=payment.payment_date,

                transaction_type="chit_collection",

                description=(
                    f"Chit collection - "
                    f"{chit.name}"
                ),

                reference=getattr(
                    payment,
                    "reference_number",
                    None,
                ),

                person_name=getattr(
                    member,
                    "member_name",
                    None,
                ),

                chit_name=getattr(
                    chit,
                    "name",
                    None,
                ),

                loan_direction=None,

                payment_method=method,

                amount=payment.amount,

                cash_amount=(
                    payment.amount
                    if method == "cash"
                    else 0
                ),

                bank_amount=(
                    payment.amount
                    if method
                    in {
                        "upi",
                        "bank_transfer",
                    }
                    else 0
                ),

                flow="in",
            )

    # =====================================================
    # 2. LOAN TRANSACTIONS
    # =====================================================

    if has_company_feature(db, company_id, "loans") and transaction_type in {
        "all",
        "loan_taken",
        "loan_given",
        "loan_repayment_received",
        "loan_repayment_paid",
    }:

        query = (
            db.query(
                LoanTransaction,
                Loan,
            )
            .join(
                Loan,
                Loan.id
                == LoanTransaction.loan_id,
            )
            .filter(
                Loan.company_id == company_id,

                LoanTransaction.company_id
                == company_id,
            )
        )

        if date_from:
            query = query.filter(
                LoanTransaction.transaction_date
                >= date_from
            )

        if date_to:
            query = query.filter(
                LoanTransaction.transaction_date
                <= date_to
            )

        loan_rows = query.all()

        for transaction, loan in loan_rows:

            transaction_kind = (
                transaction.transaction_type
            )

            # -------------------------------------------------
            # DISBURSEMENT
            # -------------------------------------------------

            if transaction_kind == "disbursement":

                if loan.direction == "given":

                    ledger_type = "loan_given"

                    flow = "out"

                    description = (
                        f"Loan given - "
                        f"{loan.person_name}"
                    )

                else:

                    ledger_type = "loan_taken"

                    flow = "in"

                    description = (
                        f"Loan taken - "
                        f"{loan.person_name}"
                    )

            # -------------------------------------------------
            # REPAYMENT
            # -------------------------------------------------

            elif transaction_kind in {
                "principal_repayment",
                "interest_payment",
            }:

                if loan.direction == "given":

                    ledger_type = (
                        "loan_repayment_received"
                    )

                    flow = "in"

                    description = (
                        f"Loan repayment received - "
                        f"{loan.person_name}"
                    )

                else:

                    ledger_type = (
                        "loan_repayment_paid"
                    )

                    flow = "out"

                    description = (
                        f"Loan repayment paid - "
                        f"{loan.person_name}"
                    )

            else:
                continue

            # -------------------------------------------------
            # TRANSACTION TYPE FILTER
            # -------------------------------------------------

            if (
                transaction_type != "all"
                and ledger_type
                != transaction_type
            ):
                continue

            cash_amount = money(
                transaction.cash_amount
            )

            bank_amount = money(
                transaction.upi_amount
            )

            total_amount = (
                cash_amount
                + bank_amount
            )

            # -------------------------------------------------
            # METHOD
            # -------------------------------------------------

            if (
                cash_amount > ZERO
                and bank_amount <= ZERO
            ):
                method = "cash"

            elif (
                bank_amount > ZERO
                and cash_amount <= ZERO
            ):
                method = "upi"

            elif (
                cash_amount > ZERO
                and bank_amount > ZERO
            ):
                method = "cash+upi"

            else:
                method = "other"

            # -------------------------------------------------
            # PAYMENT METHOD FILTER
            # -------------------------------------------------

            if payment_method != "all":

                if (
                    payment_method == "cash"
                    and cash_amount <= ZERO
                ):
                    continue

                if (
                    payment_method
                    in {
                        "upi",
                        "bank_transfer",
                    }
                    and bank_amount <= ZERO
                ):
                    continue

                if (
                    payment_method == "other"
                    and (
                        cash_amount
                        + bank_amount
                    ) > ZERO
                ):
                    continue

                if payment_method == "cheque":
                    continue

            _add_row(
                rows,

                row_id=f"loan:{transaction.id}",

                transaction_date=(
                    transaction.transaction_date
                ),

                transaction_type=ledger_type,

                description=description,

                reference=getattr(
                    transaction,
                    "reference",
                    None,
                ),

                person_name=getattr(
                    loan,
                    "person_name",
                    None,
                ),

                chit_name=None,

                loan_direction=getattr(
                    loan,
                    "direction",
                    None,
                ),

                payment_method=method,

                amount=total_amount,

                cash_amount=cash_amount,

                bank_amount=bank_amount,

                flow=flow,
            )

    # =====================================================
    # 3. EXPENSES
    # =====================================================

    if has_company_feature(db, company_id, "expenses") and transaction_type in {
        "all",
        "expense",
    }:

        query = (
            db.query(Expense)
            .filter(
                Expense.company_id
                == company_id
            )
        )

        if date_from:
            query = query.filter(
                Expense.expense_date
                >= date_from
            )

        if date_to:
            query = query.filter(
                Expense.expense_date
                <= date_to
            )

        expense_rows = query.all()

        for expense in expense_rows:

            method = _method(
                expense.payment_method
            )

            if not _method_matches(
                method,
                payment_method,
            ):
                continue

            amount = money(
                expense.amount
            )

            if method == "cash":

                cash_amount = amount
                bank_amount = ZERO

            elif method in {
                "upi",
                "bank_transfer",
            }:

                cash_amount = ZERO
                bank_amount = amount

            else:

                cash_amount = ZERO
                bank_amount = ZERO

            _add_row(
                rows,

                row_id=f"expense:{expense.id}",

                transaction_date=(
                    expense.expense_date
                ),

                transaction_type="expense",

                description=(
                    f"Expense - "
                    f"{expense.category}"
                ),

                reference=getattr(
                    expense,
                    "reference",
                    None,
                ),

                person_name=None,

                chit_name=None,

                loan_direction=None,

                payment_method=method,

                amount=amount,

                cash_amount=cash_amount,

                bank_amount=bank_amount,

                flow="out",
            )

    # =====================================================
    # 4. CHIT PAYOUTS
    # =====================================================

    if transaction_type in {
        "all",
        "chit_payout",
    }:

        query = (
            db.query(
                ChitLift,
                ChitGroup,
            )
            .join(
                ChitGroup,
                ChitGroup.id
                == ChitLift.chit_id,
            )
            .filter(
                ChitLift.company_id
                == company_id,

                ChitGroup.company_id
                == company_id,

                ChitLift.payout_status
                == "paid",
            )
        )

        if date_from:
            query = query.filter(
                ChitLift.lift_date
                >= date_from
            )

        if date_to:
            query = query.filter(
                ChitLift.lift_date
                <= date_to
            )

        lift_rows = query.all()

        for lift, chit in lift_rows:

            cash_amount = money(
                lift.cash_amount
            )

            bank_amount = money(
                lift.upi_amount
            )

            amount = (
                cash_amount
                + bank_amount
            )

            if (
                cash_amount > ZERO
                and bank_amount <= ZERO
            ):
                method = "cash"

            elif (
                bank_amount > ZERO
                and cash_amount <= ZERO
            ):
                method = "upi"

            elif (
                cash_amount > ZERO
                and bank_amount > ZERO
            ):
                method = "cash+upi"

            else:
                method = "other"

            # -------------------------------------------------
            # PAYMENT METHOD FILTER
            # -------------------------------------------------

            if payment_method != "all":

                if (
                    payment_method == "cash"
                    and cash_amount <= ZERO
                ):
                    continue

                if (
                    payment_method
                    in {
                        "upi",
                        "bank_transfer",
                    }
                    and bank_amount <= ZERO
                ):
                    continue

                if (
                    payment_method == "other"
                    and amount > ZERO
                ):
                    continue

                if payment_method == "cheque":
                    continue

            _add_row(
                rows,

                row_id=f"chit-payout:{lift.id}",

                transaction_date=(
                    lift.lift_date
                ),

                transaction_type="chit_payout",

                description=(
                    f"Chit payout - "
                    f"{chit.name}"
                ),

                reference=None,

                person_name=getattr(
                    lift,
                    "customer_name",
                    None,
                ),

                chit_name=getattr(
                    chit,
                    "name",
                    None,
                ),

                loan_direction=None,

                payment_method=method,

                amount=amount,

                cash_amount=cash_amount,

                bank_amount=bank_amount,

                flow="out",
            )

    # =====================================================
    # SEARCH
    # =====================================================

    rows = [
        row
        for row in rows
        if row["date"]
        and _matches_search(
            row,
            search,
        )
    ]

    # =====================================================
    # CHRONOLOGICAL ORDER
    # =====================================================

    rows.sort(
        key=lambda row: (
            row["date"],
            row["id"],
        )
    )

    return rows


# =========================================================
# SUMMARY
# =========================================================

def _summary(rows):

    total_money_in = sum(
        (
            row["amount"]
            for row in rows
            if row["money_flow"] == "in"
        ),
        ZERO,
    )

    total_money_out = sum(
        (
            row["amount"]
            for row in rows
            if row["money_flow"] == "out"
        ),
        ZERO,
    )

    cash_in = sum(
        (
            row["cash_amount"]
            for row in rows
            if row["money_flow"] == "in"
        ),
        ZERO,
    )

    cash_out = sum(
        (
            row["cash_amount"]
            for row in rows
            if row["money_flow"] == "out"
        ),
        ZERO,
    )

    bank_in = sum(
        (
            row["bank_amount"]
            for row in rows
            if row["money_flow"] == "in"
        ),
        ZERO,
    )

    bank_out = sum(
        (
            row["bank_amount"]
            for row in rows
            if row["money_flow"] == "out"
        ),
        ZERO,
    )

    return {
        "total_transactions": len(rows),

        "total_money_in": int(
            total_money_in
        ),

        "total_money_out": int(
            total_money_out
        ),

        "net_movement": int(
            total_money_in
            - total_money_out
        ),

        "cash_in": int(cash_in),

        "cash_out": int(cash_out),

        "cash_net": int(
            cash_in - cash_out
        ),

        "bank_in": int(bank_in),

        "bank_out": int(bank_out),

        "bank_net": int(
            bank_in - bank_out
        ),
    }


# =========================================================
# RUNNING BALANCES
# =========================================================

def _prepare_items(rows):

    cash_balance = ZERO

    bank_balance = ZERO

    items = []

    for row in rows:

        if row["money_flow"] == "in":

            cash_balance += (
                row["cash_amount"]
            )

            bank_balance += (
                row["bank_amount"]
            )

        else:

            cash_balance -= (
                row["cash_amount"]
            )

            bank_balance -= (
                row["bank_amount"]
            )

        items.append(
            {
                **row,

                "amount": int(
                    row["amount"]
                ),

                "cash_amount": int(
                    row["cash_amount"]
                ),

                "bank_amount": int(
                    row["bank_amount"]
                ),

                "cash_balance": int(
                    cash_balance
                ),

                "bank_balance": int(
                    bank_balance
                ),

                "total_balance": int(
                    cash_balance
                    + bank_balance
                ),
            }
        )

    return items


# =========================================================
# COMPANY
# =========================================================

def _company(
    db: Session,
    company_id: int,
):

    return (
        db.query(Company)
        .filter(
            Company.id == company_id
        )
        .first()
    )


# =========================================================
# MAIN REPORT
# =========================================================

def get_ledger_report(
    db: Session,
    company_id: int,

    date_from: Optional[date] = None,

    date_to: Optional[date] = None,

    transaction_type: str = "all",

    payment_method: str = "all",

    search: Optional[str] = None,

    page: int = 1,

    page_size: int = 10,
):

    company = _company(
        db,
        company_id,
    )

    if not company:

        return {
            "error": "company_not_found"
        }

    page = max(
        page,
        1,
    )

    page_size = min(
        max(
            page_size,
            1,
        ),
        100,
    )

    rows = _build_ledger_rows(
        db=db,

        company_id=company_id,

        date_from=date_from,

        date_to=date_to,

        transaction_type=transaction_type,

        payment_method=payment_method,

        search=search,
    )

    summary = _summary(rows)

    items = _prepare_items(rows)

    total_records = len(items)

    total_pages = (
        ceil(
            total_records
            / page_size
        )
        if total_records
        else 0
    )

    start = (
        page - 1
    ) * page_size

    end = (
        start
        + page_size
    )

    return {
        "company_id": company.id,

        "company_name": company.company_name,

        "logo_url": getattr(
            company,
            "logo_url",
            None,
        ),

        "date_from": date_from,

        "date_to": date_to,

        "summary": summary,

        "items": items[
            start:end
        ],

        "total_records": total_records,

        "page": page,

        "page_size": page_size,

        "total_pages": total_pages,
    }


# =========================================================
# EXPORT DATA
# =========================================================

def get_ledger_report_export_data(
    db: Session,
    company_id: int,

    date_from: Optional[date] = None,

    date_to: Optional[date] = None,

    transaction_type: str = "all",

    payment_method: str = "all",

    search: Optional[str] = None,
):

    company = _company(
        db,
        company_id,
    )

    if not company:

        return {
            "error": "company_not_found"
        }

    rows = _build_ledger_rows(
        db=db,

        company_id=company_id,

        date_from=date_from,

        date_to=date_to,

        transaction_type=transaction_type,

        payment_method=payment_method,

        search=search,
    )

    items = _prepare_items(rows)

    return {
        "company_id": company.id,

        "company_name": company.company_name,

        "logo_url": getattr(
            company,
            "logo_url",
            None,
        ),

        "date_from": date_from,

        "date_to": date_to,

        "summary": _summary(rows),

        "items": items,

        "total_records": len(items),
    }