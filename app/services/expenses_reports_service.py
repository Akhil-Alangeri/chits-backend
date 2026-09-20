from __future__ import annotations

from calendar import month_name
from datetime import date
from math import ceil
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.admin.company import Company
from app.models.admin.expenses import Expense


# =========================================================
# MONEY HELPER
# =========================================================

def money(value) -> int:
    """
    Safely convert DB numeric values into integer money.
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


# =========================================================
# DATE HELPER
# =========================================================

def _format_datetime(value) -> Optional[str]:
    """
    Convert datetime/date value into ISO string.
    """

    if value is None:
        return None

    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


# =========================================================
# PAYMENT METHOD
# =========================================================

def _normalize_payment_method(
    payment_method,
) -> str:
    """
    Normalize payment method.
    """

    return (
        str(payment_method or "")
        .strip()
        .lower()
    )


# =========================================================
# BUILD REPORT DATA
# =========================================================

def _build_expense_report_data(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category: Optional[str] = None,
    payment_method: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    Build complete company-scoped Expense Report data.

    Pagination is intentionally NOT applied here.
    """

    # =====================================================
    # COMPANY
    # =====================================================

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

    # =====================================================
    # BASE QUERY
    # =====================================================

    query = (
        db.query(Expense)
        .filter(
            Expense.company_id == company_id
        )
    )

    # =====================================================
    # DATE FILTER
    # =====================================================

    if date_from:
        query = query.filter(
            Expense.expense_date >= date_from
        )

    if date_to:
        query = query.filter(
            Expense.expense_date <= date_to
        )

    # =====================================================
    # CATEGORY FILTER
    # =====================================================

    if category and category.strip():

        query = query.filter(
            func.lower(
                Expense.category
            )
            == category.strip().lower()
        )

    # =====================================================
    # PAYMENT METHOD FILTER
    # =====================================================

    if (
        payment_method
        and payment_method.strip()
        and payment_method.lower() != "all"
    ):

        query = query.filter(
            func.lower(
                Expense.payment_method
            )
            == payment_method.strip().lower()
        )

    # =====================================================
    # SEARCH
    #
    # Search:
    # - category
    # - description
    # - reference
    # - notes
    # =====================================================

    if search and search.strip():

        search_value = (
            f"%{search.strip()}%"
        )

        query = query.filter(
            or_(
                Expense.category.ilike(
                    search_value
                ),

                Expense.description.ilike(
                    search_value
                ),

                Expense.reference.ilike(
                    search_value
                ),

                Expense.notes.ilike(
                    search_value
                ),
            )
        )

    # =====================================================
    # ORDER
    # =====================================================

    expenses = (
        query
        .order_by(
            Expense.expense_date.desc(),
            Expense.id.desc(),
        )
        .all()
    )

    # =====================================================
    # SUMMARY VARIABLES
    # =====================================================

    total_expenses = 0

    cash_expenses = 0
    upi_expenses = 0
    other_expenses = 0

    highest_expense = 0

    categories_map = {}

    monthly_map = {}

    report_items = []

    # =====================================================
    # PROCESS EXPENSES
    # =====================================================

    for expense in expenses:

        amount = money(
            expense.amount
        )

        total_expenses += amount

        # -------------------------------------------------
        # PAYMENT METHOD
        # -------------------------------------------------

        method = (
            _normalize_payment_method(
                expense.payment_method
            )
        )

        if method == "cash":

            cash_expenses += amount

        elif method in {
            "upi",
            "bank_transfer",
        }:

            upi_expenses += amount

        else:

            other_expenses += amount

        # -------------------------------------------------
        # HIGHEST EXPENSE
        # -------------------------------------------------

        if amount > highest_expense:
            highest_expense = amount

        # -------------------------------------------------
        # CATEGORY SUMMARY
        # -------------------------------------------------

        category_name = (
            expense.category
            or "Other"
        )

        category_key = (
            category_name.strip()
            if isinstance(
                category_name,
                str,
            )
            else str(
                category_name
            )
        )

        if not category_key:
            category_key = "Other"

        if category_key not in categories_map:

            categories_map[
                category_key
            ] = {
                "amount": 0,
                "record_count": 0,
            }

        categories_map[
            category_key
        ]["amount"] += amount

        categories_map[
            category_key
        ]["record_count"] += 1

        # -------------------------------------------------
        # MONTHLY SUMMARY
        # -------------------------------------------------

        if expense.expense_date:

            month_key = (
                expense.expense_date.year,
                expense.expense_date.month,
            )

            if (
                month_key
                not in monthly_map
            ):

                monthly_map[
                    month_key
                ] = {
                    "amount": 0,
                    "record_count": 0,
                }

            monthly_map[
                month_key
            ]["amount"] += amount

            monthly_map[
                month_key
            ]["record_count"] += 1

        # -------------------------------------------------
        # ITEM
        # -------------------------------------------------

        report_items.append(
            {
                "id": expense.id,

                "category": category_key,

                "amount": amount,

                "description": (
                    expense.description
                ),

                "expense_date": (
                    expense.expense_date
                ),

                "payment_method": (
                    expense.payment_method
                    or ""
                ),

                "reference": (
                    expense.reference
                ),

                "notes": (
                    expense.notes
                ),

                "created_by": (
                    expense.created_by
                ),

                "created_at": (
                    _format_datetime(
                        expense.created_at
                    )
                ),

                "updated_at": (
                    _format_datetime(
                        expense.updated_at
                    )
                ),
            }
        )

    # =====================================================
    # CATEGORY RESPONSE
    # =====================================================

    categories = []

    for category_name, values in sorted(
        categories_map.items(),
        key=lambda item: (
            item[1]["amount"]
        ),
        reverse=True,
    ):

        categories.append(
            {
                "category": category_name,
                "amount": money(
                    values["amount"]
                ),
                "record_count": int(
                    values["record_count"]
                ),
            }
        )

    # =====================================================
    # MONTHLY RESPONSE
    # =====================================================

    monthly_summary = []

    for (
        year,
        month,
    ), values in sorted(
        monthly_map.items()
    ):

        monthly_summary.append(
            {
                "year": year,
                "month": month,
                "month_name": month_name[
                    month
                ],
                "amount": money(
                    values["amount"]
                ),
                "record_count": int(
                    values["record_count"]
                ),
            }
        )

    # =====================================================
    # AVERAGE
    # =====================================================

    total_records = len(
        report_items
    )

    average_expense = (
        round(
            total_expenses
            / total_records
        )
        if total_records > 0
        else 0
    )

    # =====================================================
    # FINAL RESPONSE
    # =====================================================

    return {
        "company_id": company.id,

        "company_name": (
            company.company_name
        ),

        "logo_url": (
            company.logo_url
        ),

        "date_from": date_from,

        "date_to": date_to,

        "summary": {
            "total_expenses": (
                total_expenses
            ),

            "total_records": (
                total_records
            ),

            "cash_expenses": (
                cash_expenses
            ),

            "upi_expenses": (
                upi_expenses
            ),

            "other_expenses": (
                other_expenses
            ),

            "average_expense": (
                average_expense
            ),

            "highest_expense": (
                highest_expense
            ),

            "unique_categories": (
                len(categories)
            ),
        },

        "categories": categories,

        "monthly_summary": (
            monthly_summary
        ),

        "items": report_items,

        "total_records": total_records,
    }


# =========================================================
# PAGINATED REPORT
# =========================================================

def get_expense_report(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category: Optional[str] = None,
    payment_method: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
):
    """
    Get paginated Expense Report.
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

    report = _build_expense_report_data(
        db=db,
        company_id=company_id,

        date_from=date_from,
        date_to=date_to,

        category=category,

        payment_method=payment_method,

        search=search,
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

def get_expense_report_export_data(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category: Optional[str] = None,
    payment_method: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    Complete filtered Expense Report data.

    Pagination is NOT applied.
    """

    return _build_expense_report_data(
        db=db,
        company_id=company_id,

        date_from=date_from,
        date_to=date_to,

        category=category,

        payment_method=payment_method,

        search=search,
    )