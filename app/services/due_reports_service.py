from datetime import date, datetime
from math import ceil
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.admin.company import Company
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.chit_member import ChitMember
from app.models.admin.payment_transaction import PaymentTransaction


def _safe_int(value) -> int:
    """
    Safely convert money/numeric values into integer.
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


def _calculate_days_overdue(due_date: Optional[date]) -> int:
    """
    Calculate number of overdue days.

    Future/today due dates return 0.
    """
    if not due_date:
        return 0

    today = date.today()

    if due_date >= today:
        return 0

    return (today - due_date).days


def _get_due_status(
    due_date: Optional[date],
    paid_amount: int,
    remaining_amount: int,
) -> str:
    """
    Determine installment status.

    overdue:
        Remaining amount exists and due date has passed.

    partial:
        Some amount is paid but amount is still remaining.

    due:
        Nothing has been paid and amount is still remaining.
    """

    if remaining_amount <= 0:
        return "paid"

    if due_date and due_date < date.today():
        return "overdue"

    if paid_amount > 0:
        return "partial"

    return "due"


def _build_due_report_data(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    chit_id: Optional[int] = None,
    member_id: Optional[int] = None,
    report_status: str = "all",
    search: Optional[str] = None,
):
    """
    Build the complete company-scoped Due Report dataset.

    This function intentionally does not paginate.
    Pagination is applied by get_due_report().
    """

    # ---------------------------------------------------------
    # Company
    # ---------------------------------------------------------

    company = (
        db.query(Company)
        .filter(Company.id == company_id)
        .first()
    )

    if not company:
        raise ValueError("Company not found.")

    # ---------------------------------------------------------
    # Payment aggregation
    #
    # Instead of loading every payment row separately, aggregate
    # all payments for each installment.
    # ---------------------------------------------------------

    paid_subquery = (
        db.query(
            PaymentTransaction.installment_id.label(
                "installment_id"
            ),
            func.coalesce(
                func.sum(PaymentTransaction.amount),
                0,
            ).label("paid_amount"),
        )
        .group_by(
            PaymentTransaction.installment_id
        )
        .subquery()
    )

    # ---------------------------------------------------------
    # Base query
    # ---------------------------------------------------------

    query = (
        db.query(
            ChitInstallment,
            ChitMember,
            ChitGroup,
            CustomerProfile,
            func.coalesce(
                paid_subquery.c.paid_amount,
                0,
            ).label("paid_amount"),
        )
        .join(
            ChitMember,
            ChitInstallment.chit_member_id
            == ChitMember.id,
        )
        .join(
            ChitGroup,
            ChitMember.chit_id
            == ChitGroup.id,
        )
        .join(
            CustomerProfile,
            ChitMember.member_number
            == CustomerProfile.id,
        )
        .outerjoin(
            paid_subquery,
            ChitInstallment.id
            == paid_subquery.c.installment_id,
        )
        .filter(
            ChitGroup.company_id == company_id,

            # Only active chits
            ChitGroup.status == "active",

            # Only valid/active chit members
            ChitMember.status.in_(
                ["confirmed", "active"]
            ),
        )
    )

    # ---------------------------------------------------------
    # Date filters
    #
    # These filters apply to installment due date.
    # ---------------------------------------------------------

    if date_from:
        query = query.filter(
            ChitInstallment.due_date >= date_from
        )

    if date_to:
        query = query.filter(
            ChitInstallment.due_date <= date_to
        )

    # ---------------------------------------------------------
    # Chit filter
    # ---------------------------------------------------------

    if chit_id is not None:
        query = query.filter(
            ChitGroup.id == chit_id
        )

    # ---------------------------------------------------------
    # Member filter
    # ---------------------------------------------------------

    if member_id is not None:
        query = query.filter(
            ChitMember.member_id == member_id
        )

    # ---------------------------------------------------------
    # Search
    #
    # Search supports:
    # - member name
    # - customer code
    # - chit name
    # - chit code
    # - member number
    # ---------------------------------------------------------

    if search and search.strip():
        search_value = (
            f"%{search.strip()}%"
        )

        query = query.filter(
            or_(
                CustomerProfile.display_name.ilike(
                    search_value
                ),
                CustomerProfile.customer_code.ilike(
                    search_value
                ),
                ChitGroup.name.ilike(
                    search_value
                ),
                ChitGroup.code.ilike(
                    search_value
                ),
                ChitMember.member_number.ilike(
                    search_value
                ),
            )
        )

    # ---------------------------------------------------------
    # Ordering
    #
    # Oldest due dates first so overdue items appear naturally
    # at the top.
    # ---------------------------------------------------------

    query = query.order_by(
        ChitInstallment.due_date.asc(),
        ChitInstallment.id.asc(),
    )

    rows = query.all()

    # ---------------------------------------------------------
    # Build report items
    # ---------------------------------------------------------

    report_items = []

    total_due = 0
    total_paid = 0
    total_remaining = 0

    due_records = 0
    partial_records = 0
    overdue_records = 0

    unique_members = set()

    for (
        installment,
        chit_member,
        chit,
        customer,
        paid_amount_raw,
    ) in rows:

        due_amount = _safe_int(
            installment.due_amount
        )

        paid_amount = _safe_int(
            paid_amount_raw
        )

        # Never allow negative remaining balance.
        remaining_amount = max(
            due_amount - paid_amount,
            0,
        )

        # Fully paid installments are NOT Due Report records.
        if remaining_amount <= 0:
            continue

        status = _get_due_status(
            due_date=installment.due_date,
            paid_amount=paid_amount,
            remaining_amount=remaining_amount,
        )

        # -----------------------------------------------------
        # Status filter
        # -----------------------------------------------------

        if (
            report_status
            and report_status != "all"
            and status != report_status
        ):
            continue

        # -----------------------------------------------------
        # Summary
        # -----------------------------------------------------

        total_due += due_amount
        total_paid += paid_amount
        total_remaining += remaining_amount

        if status == "due":
            due_records += 1

        elif status == "partial":
            partial_records += 1

        elif status == "overdue":
            overdue_records += 1

        if chit_member.customer_profile_id is not None:
            unique_members.add(
                chit_member.customer_profile_id
            )

        # -----------------------------------------------------
        # Member number
        # -----------------------------------------------------

        member_number = getattr(
            chit_member,
            "member_number",
            None,
        )

        # -----------------------------------------------------
        # Customer details
        # -----------------------------------------------------

        member_name = (
            getattr(
                customer,
                "display_name",
                None,
            )
            or "Unknown Member"
        )

        customer_code = getattr(
            customer,
            "customer_code",
            None,
        )

        # -----------------------------------------------------
        # Chit details
        # -----------------------------------------------------

        chit_name = (
            getattr(
                chit,
                "name",
                None,
            )
            or getattr(
                chit,
                "chit_name",
                None,
            )
            or "Unknown Chit"
        )

        chit_code = (
            getattr(
                chit,
                "code",
                None,
            )
            or getattr(
                chit,
                "chit_code",
                None,
            )
        )

        days_overdue = (
            _calculate_days_overdue(
                installment.due_date
            )
            if status == "overdue"
            else 0
        )

        # -----------------------------------------------------
        # Report item
        # -----------------------------------------------------

        report_items.append(
            {
                "id": installment.id,

                "chit_id": chit.id,
                "chit_name": chit_name,
                "chit_code": chit_code,

                "chit_member_id": chit_member.id,
                "member_id": chit_member.customer_profile_id,

                "member_number": (
                    str(member_number)
                    if member_number is not None
                    else None
                ),

                "member_name": member_name,
                "customer_code": customer_code,

                "installment_number": (
                    installment.installment_number
                ),

                "due_date": installment.due_date,

                "due_amount": due_amount,
                "paid_amount": paid_amount,
                "remaining_amount": remaining_amount,

                "status": status,
                "days_overdue": days_overdue,
            }
        )

    # ---------------------------------------------------------
    # Final response data
    # ---------------------------------------------------------

    return {
        "company_id": company.id,
        "company_name": company.company_name,
        "logo_url": company.logo_url,

        "summary": {
            "total_due": total_due,
            "total_paid": total_paid,
            "total_remaining": total_remaining,

            "total_records": len(report_items),

            "due_records": due_records,
            "partial_records": partial_records,
            "overdue_records": overdue_records,

            "unique_members": len(unique_members),
        },

        "items": report_items,

        "total_records": len(report_items),
    }


def get_due_report(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    chit_id: Optional[int] = None,
    member_id: Optional[int] = None,
    report_status: str = "all",
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
):
    """
    Get paginated Due Report.
    """

    # ---------------------------------------------------------
    # Normalize pagination
    # ---------------------------------------------------------

    page = max(page, 1)

    page_size = min(
        max(page_size, 1),
        100,
    )

    offset = (
        page - 1
    ) * page_size

    # ---------------------------------------------------------
    # Build complete filtered dataset
    # ---------------------------------------------------------

    report = _build_due_report_data(
        db=db,
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        chit_id=chit_id,
        member_id=member_id,
        report_status=report_status,
        search=search,
    )

    # ---------------------------------------------------------
    # Pagination
    # ---------------------------------------------------------

    total_records = report["total_records"]

    total_pages = (
        ceil(
            total_records / page_size
        )
        if total_records > 0
        else 0
    )

    report["items"] = report["items"][
        offset: offset + page_size
    ]

    report["page"] = page
    report["page_size"] = page_size
    report["total_pages"] = total_pages

    return report


def get_due_report_export_data(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    chit_id: Optional[int] = None,
    member_id: Optional[int] = None,
    report_status: str = "all",
    search: Optional[str] = None,
):
    """
    Get complete filtered Due Report data for Excel/PDF export.

    No pagination is applied here.
    """

    return _build_due_report_data(
        db=db,
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        chit_id=chit_id,
        member_id=member_id,
        report_status=report_status,
        search=search,
    )