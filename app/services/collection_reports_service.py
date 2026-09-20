from datetime import date
from math import ceil
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.admin.payment_transaction import PaymentTransaction
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_group import ChitGroup
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.company import Company


# =========================================================
# HELPERS
# =========================================================


def _safe_int(value) -> int:
    return int(value or 0)


def _get_installment_status(
    due_amount: int,
    paid_amount: int,
) -> str:

    if paid_amount <= 0:
        return "due"

    if paid_amount < due_amount:
        return "partial"

    return "paid"


def _get_collected_by_name(
    db: Session,
    created_by: Optional[int],
) -> Optional[str]:

    """
    Resolve the user who recorded the payment.

    The existing PaymentTransaction stores created_by.
    We intentionally keep this helper isolated so the report
    does not depend on a specific User display field.
    """

    if not created_by:
        return None

    # Import locally to avoid unnecessary model import coupling.
    from app.models.user import User

    user = (
        db.query(User)
        .filter(
            User.id == created_by
        )
        .first()
    )

    if not user:
        return None

    # Use whichever common display field is available.
    if getattr(user, "full_name", None):
        return user.full_name

    if getattr(user, "name", None):
        return user.name

    if getattr(user, "username", None):
        return user.username

    if getattr(user, "email", None):
        return user.email

    return str(user.id)


# =========================================================
# SHARED COLLECTION REPORT DATA BUILDER
# =========================================================

def _build_collection_report_data(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    chit_id: Optional[int] = None,
    member_id: Optional[int] = None,
    payment_method: Optional[str] = None,
    report_status: str = "all",
    search: Optional[str] = None,
):
    """
    Build the complete company-scoped collection report dataset.

    This function contains the shared:
    - company lookup/isolation
    - filters
    - transaction query
    - installment paid calculation
    - status calculation
    - report item construction

    It intentionally does NOT apply pagination.
    """

    # =====================================================
    # COMPANY DETAILS
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
        db.query(
            PaymentTransaction,
            ChitInstallment,
            ChitMember,
            ChitGroup,
            CustomerProfile,
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
        .join(
            CustomerProfile,
            CustomerProfile.id
            == ChitMember.customer_profile_id,
        )
        .filter(
            # =================================================
            # COMPANY ISOLATION
            # =================================================
            ChitGroup.company_id
            == company_id,

            # Only valid chit members.
            ChitMember.status.in_(
                [
                    "confirmed",
                    "active",
                ]
            ),
        )
    )

    # =====================================================
    # DATE FILTER
    # =====================================================

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

    # =====================================================
    # CHIT FILTER
    # =====================================================

    if chit_id is not None:
        query = query.filter(
            ChitGroup.id
            == chit_id
        )

    # =====================================================
    # MEMBER FILTER
    # =====================================================

    if member_id is not None:
        query = query.filter(
            ChitMember.id
            == member_id
        )

    # =====================================================
    # PAYMENT METHOD FILTER
    # =====================================================

    if payment_method:
        normalized_method = (
            payment_method
            .strip()
            .lower()
        )

        if normalized_method not in (
            "",
            "all",
        ):
            query = query.filter(
                func.lower(
                    PaymentTransaction.payment_method
                )
                == normalized_method
            )

    # =====================================================
    # SEARCH
    # =====================================================

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
                PaymentTransaction.reference_number.ilike(
                    search_value
                ),
            )
        )

    # =====================================================
    # GET ALL MATCHING TRANSACTIONS
    # =====================================================

    rows = (
        query
        .order_by(
            PaymentTransaction.payment_date.desc(),
            PaymentTransaction.id.desc(),
        )
        .all()
    )

    # =====================================================
    # CACHE INSTALLMENT PAID AMOUNTS
    # =====================================================

    installment_ids = [
        installment.id
        for (
            payment,
            installment,
            member,
            chit,
            customer,
        ) in rows
    ]

    paid_by_installment = {}

    if installment_ids:
        paid_rows = (
            db.query(
                PaymentTransaction.installment_id,
                func.coalesce(
                    func.sum(
                        PaymentTransaction.amount
                    ),
                    0,
                ).label(
                    "paid_amount"
                ),
            )
            .filter(
                PaymentTransaction.installment_id.in_(
                    installment_ids
                )
            )
            .group_by(
                PaymentTransaction.installment_id
            )
            .all()
        )

        paid_by_installment = {
            row.installment_id:
                _safe_int(
                    row.paid_amount
                )
            for row in paid_rows
        }

    # =====================================================
    # BUILD REPORT DATA
    # =====================================================

    report_items = []

    total_collected = 0
    total_payments = 0
    unique_members = set()
    pending_amount = 0

    for (
        payment,
        installment,
        member,
        chit,
        customer,
    ) in rows:

        due_amount = _safe_int(
            installment.due_amount
        )

        installment_paid = _safe_int(
            paid_by_installment.get(
                installment.id,
                0,
            )
        )

        remaining_amount = max(
            due_amount
            - installment_paid,
            0,
        )

        status_value = (
            _get_installment_status(
                due_amount,
                installment_paid,
            )
        )

        # =================================================
        # STATUS FILTER
        # =================================================

        if (
            report_status != "all"
            and status_value != report_status
        ):
            continue

        # =================================================
        # SUMMARY
        # =================================================

        total_collected += _safe_int(
            payment.amount
        )

        total_payments += 1

        unique_members.add(
            member.id
        )

        pending_amount += remaining_amount

        # =================================================
        # RECEIPT NUMBER
        # =================================================

        receipt_no = (
            f"PAY-{payment.id:06d}"
            if payment.id
            else None
        )

        # =================================================
        # MEMBER NUMBER
        # =================================================

        member_number = None

        if member.member_number is not None:
            member_number = str(
                member.member_number
            )

        # =================================================
        # PAYMENT METHOD
        # =================================================

        payment_method_value = (
            payment.payment_method
            or ""
        ).strip()

        # =================================================
        # REPORT ITEM
        # =================================================

        report_items.append(
            {
                "id": payment.id,
                "date": payment.payment_date,
                "receipt_no": receipt_no,
                "member_id": member.id,
                "member_name": (
                    customer.display_name
                    or member.member_name
                    or ""
                ),
                "member_number": member_number,
                "chit_id": chit.id,
                "chit_name": chit.name,
                "installment_id": installment.id,
                "installment_number":
                    installment.installment_number,
                "due_amount": due_amount,

                # Actual payment transaction amount.
                "paid_amount": _safe_int(
                    payment.amount
                ),

                "remaining_amount":
                    remaining_amount,
                "payment_method":
                    payment_method_value,
                "reference_number":
                    payment.reference_number,
                "status": status_value,
                "collected_by":
                    _get_collected_by_name(
                        db,
                        payment.created_by,
                    ),
            }
        )

    return {
        "company_id": company.id,
        "company_name": company.company_name,
        "logo_url": company.logo_url,
        "summary": {
            "total_collected":
                total_collected,
            "total_payments":
                total_payments,
            "unique_members":
                len(unique_members),
            "pending_amount":
                pending_amount,
        },
        "items": report_items,
        "total_records":
            len(report_items),
    }


# =========================================================
# COLLECTION REPORT - UI
# =========================================================

def get_collection_report(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    chit_id: Optional[int] = None,
    member_id: Optional[int] = None,
    payment_method: Optional[str] = None,
    report_status: str = "all",
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
):
    """
    Generate the paginated company-scoped collection report.

    All business/data-building logic is shared with exports.
    Pagination is applied only here for the UI report.
    """

    # =====================================================
    # NORMALIZE PAGINATION
    # =====================================================

    page = max(page, 1)

    page_size = min(
        max(page_size, 1),
        100,
    )

    offset = (
        page - 1
    ) * page_size

    # =====================================================
    # BUILD COMPLETE DATASET
    # =====================================================

    report = _build_collection_report_data(
        db=db,
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        chit_id=chit_id,
        member_id=member_id,
        payment_method=payment_method,
        report_status=report_status,
        search=search,
    )

    total_records = report["total_records"]

    total_pages = (
        ceil(
            total_records
            / page_size
        )
        if total_records > 0
        else 0
    )

    # =====================================================
    # PAGINATION
    # =====================================================

    report["items"] = report["items"][
        offset:
        offset + page_size
    ]

    # =====================================================
    # UI RESPONSE
    # =====================================================

    report["page"] = page
    report["page_size"] = page_size
    report["total_pages"] = total_pages

    return report


# =========================================================
# COLLECTION REPORT - EXPORT DATA
# =========================================================

def get_collection_report_export_data(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    chit_id: Optional[int] = None,
    member_id: Optional[int] = None,
    payment_method: Optional[str] = None,
    report_status: str = "all",
    search: Optional[str] = None,
):
    """
    Generate the complete company-scoped collection report
    dataset for Excel/PDF export.

    No pagination is applied.
    """

    return _build_collection_report_data(
        db=db,
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        chit_id=chit_id,
        member_id=member_id,
        payment_method=payment_method,
        report_status=report_status,
        search=search,
    )
