from __future__ import annotations

from datetime import date
from math import ceil
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.admin.company import Company
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_months import ChitMonth
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.payment_transaction import PaymentTransaction
from app.models.admin.chitlift import ChitLift


# =========================================================
# MONEY
# =========================================================

def money(value) -> int:
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
# DATE
# =========================================================

def _date_value(value):
    if value is None:
        return None

    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(
            str(value)[:10]
        )
    except (TypeError, ValueError):
        return None


# =========================================================
# BUILD REPORT
# =========================================================

def _build_chit_report_data(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    chit_id: Optional[int] = None,
    report_status: str = "all",
    search: Optional[str] = None,
):
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
    # CHITS
    # =====================================================

    query = (
        db.query(ChitGroup)
        .filter(
            ChitGroup.company_id == company_id
        )
    )

    if chit_id:
        query = query.filter(
            ChitGroup.id == chit_id
        )

    if report_status != "all":
        query = query.filter(
            ChitGroup.status == report_status
        )

    # =====================================================
    # DATE FILTER
    # =====================================================

    if date_from:
        query = query.filter(
            ChitGroup.start_date >= date_from
        )

    if date_to:
        query = query.filter(
            ChitGroup.start_date <= date_to
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
                ChitGroup.name.ilike(
                    search_value
                ),

                ChitGroup.code.ilike(
                    search_value
                ),
            )
        )

    chits = (
        query
        .order_by(
            ChitGroup.start_date.desc(),
            ChitGroup.id.desc(),
        )
        .all()
    )

    # =====================================================
    # EARLY EMPTY RESPONSE
    # =====================================================

    if not chits:

        return {
            "company_id": company.id,
            "company_name": company.company_name,
            "logo_url": company.logo_url,

            "summary": {
                "total_chits": 0,

                "draft_chits": 0,
                "active_chits": 0,
                "completed_chits": 0,
                "cancelled_chits": 0,

                "total_chit_value": 0,

                "total_members": 0,
                "confirmed_members": 0,
                "active_members": 0,

                "total_scheduled_amount": 0,
                "total_collected_amount": 0,
                "total_outstanding_amount": 0,

                "collection_rate": 0.0,

                "total_lifts": 0,
                "completed_payouts": 0,
                "pending_payouts": 0,

                "total_lifted_amount": 0,
                "total_discount_amount": 0,
            },

            "items": [],

            "monthly_summary": [],

            "total_records": 0,
        }

    chit_ids = [
        chit.id
        for chit in chits
    ]

    # =====================================================
    # MEMBERS
    # =====================================================

    members = (
        db.query(ChitMember)
        .filter(
            ChitMember.chit_id.in_(
                chit_ids
            )
        )
        .all()
    )

    members_by_chit = {}

    for member in members:

        members_by_chit.setdefault(
            member.chit_id,
            [],
        ).append(member)

    member_ids = [
        member.id
        for member in members
    ]

    # =====================================================
    # INSTALLMENTS
    # =====================================================

    installments = []

    if member_ids:

        installments = (
            db.query(ChitInstallment)
            .filter(
                ChitInstallment.chit_member_id.in_(
                    member_ids
                )
            )
            .all()
        )

    installment_ids = [
        installment.id
        for installment in installments
    ]

    # =====================================================
    # PAYMENTS
    # =====================================================

    payments = []

    if installment_ids:

        payments = (
            db.query(
                PaymentTransaction
            )
            .filter(
                PaymentTransaction.installment_id.in_(
                    installment_ids
                )
            )
            .all()
        )

    paid_by_installment = {}

    last_payment_by_chit = {}

    for payment in payments:

        installment_id = (
            payment.installment_id
        )

        amount = money(
            payment.amount
        )

        paid_by_installment[
            installment_id
        ] = (
            paid_by_installment.get(
                installment_id,
                0,
            )
            + amount
        )

    # =====================================================
    # MAP INSTALLMENTS TO CHIT
    # =====================================================

    member_to_chit = {
        member.id: member.chit_id
        for member in members
    }

    installments_by_chit = {}

    for installment in installments:

        current_chit_id = (
            member_to_chit.get(
                installment.chit_member_id
            )
        )

        if current_chit_id is None:
            continue

        installments_by_chit.setdefault(
            current_chit_id,
            [],
        ).append(installment)

    # =====================================================
    # LAST COLLECTION DATE
    # =====================================================

    for payment in payments:

        installment = next(
            (
                item
                for item in installments
                if item.id
                == payment.installment_id
            ),
            None,
        )

        if not installment:
            continue

        current_chit_id = (
            member_to_chit.get(
                installment.chit_member_id
            )
        )

        if current_chit_id is None:
            continue

        payment_date = _date_value(
            payment.payment_date
        )

        if not payment_date:
            continue

        previous = last_payment_by_chit.get(
            current_chit_id
        )

        if (
            previous is None
            or payment_date > previous
        ):
            last_payment_by_chit[
                current_chit_id
            ] = payment_date

    # =====================================================
    # LIFTS
    # =====================================================

    lifts = (
        db.query(ChitLift)
        .filter(
            ChitLift.company_id == company_id,
            ChitLift.chit_id.in_(
                chit_ids
            ),
        )
        .all()
    )

    lifts_by_chit = {}

    for lift in lifts:

        lifts_by_chit.setdefault(
            lift.chit_id,
            [],
        ).append(lift)

    # =====================================================
    # SUMMARY
    # =====================================================

    total_chit_value = 0

    total_members = 0
    confirmed_members = 0
    active_members = 0

    total_scheduled = 0
    total_collected = 0

    total_lifts = 0
    completed_payouts = 0
    pending_payouts = 0

    total_lifted_amount = 0
    total_discount_amount = 0

    draft_chits = 0
    active_chits = 0
    completed_chits = 0
    cancelled_chits = 0

    report_items = []

    # =====================================================
    # CHIT PROCESSING
    # =====================================================

    for chit in chits:

        chit_members = (
            members_by_chit.get(
                chit.id,
                [],
            )
        )

        chit_installments = (
            installments_by_chit.get(
                chit.id,
                [],
            )
        )

        chit_lifts = (
            lifts_by_chit.get(
                chit.id,
                [],
            )
        )

        # -------------------------------------------------
        # MEMBERS
        # -------------------------------------------------

        member_count = len(
            chit_members
        )

        confirmed_count = sum(
            1
            for member in chit_members
            if member.status == "confirmed"
        )

        active_count = sum(
            1
            for member in chit_members
            if member.status == "active"
        )

        total_members += member_count
        confirmed_members += (
            confirmed_count
        )
        active_members += (
            active_count
        )

        # -------------------------------------------------
        # CHIT STATUS
        # -------------------------------------------------

        status_value = (
            chit.status or ""
        ).lower()

        if status_value == "draft":
            draft_chits += 1

        elif status_value == "active":
            active_chits += 1

        elif status_value == "completed":
            completed_chits += 1

        elif status_value == "cancelled":
            cancelled_chits += 1

        # -------------------------------------------------
        # CHIT VALUE
        # -------------------------------------------------

        chit_value = money(
            chit.chit_value
        )

        total_chit_value += (
            chit_value
        )

        # -------------------------------------------------
        # INSTALLMENTS
        # -------------------------------------------------

        scheduled_amount = 0
        collected_amount = 0

        last_collection_date = (
            last_payment_by_chit.get(
                chit.id
            )
        )

        for installment in (
            chit_installments
        ):

            due_amount = money(
                installment.due_amount
            )

            paid_amount = money(
                paid_by_installment.get(
                    installment.id,
                    0,
                )
            )

            scheduled_amount += (
                due_amount
            )

            collected_amount += min(
                paid_amount,
                due_amount,
            )

        outstanding_amount = max(
            scheduled_amount
            - collected_amount,
            0,
        )

        total_scheduled += (
            scheduled_amount
        )

        total_collected += (
            collected_amount
        )

        # -------------------------------------------------
        # LIFTS
        # -------------------------------------------------

        chit_lift_count = len(
            chit_lifts
        )

        chit_lifted_amount = sum(
            money(
                lift.lifted_amount
            )
            for lift in chit_lifts
        )

        chit_discount_amount = sum(
            money(
                lift.discount_amount
            )
            for lift in chit_lifts
        )

        chit_completed_payouts = sum(
            1
            for lift in chit_lifts
            if str(
                lift.payout_status or ""
            ).lower()
            in {
                "completed",
                "paid",
                "success",
            }
        )

        chit_pending_payouts = (
            chit_lift_count
            - chit_completed_payouts
        )

        total_lifts += (
            chit_lift_count
        )

        completed_payouts += (
            chit_completed_payouts
        )

        pending_payouts += (
            chit_pending_payouts
        )

        total_lifted_amount += (
            chit_lifted_amount
        )

        total_discount_amount += (
            chit_discount_amount
        )

        # -------------------------------------------------
        # COLLECTION RATE
        # -------------------------------------------------

        collection_rate = (
            round(
                (
                    collected_amount
                    / scheduled_amount
                )
                * 100,
                2,
            )
            if scheduled_amount > 0
            else 0.0
        )

        # -------------------------------------------------
        # LAST LIFT DATE
        # -------------------------------------------------

        last_lift_date = None

        for lift in chit_lifts:

            lift_date = _date_value(
                lift.lift_date
            )

            if not lift_date:
                continue

            if (
                last_lift_date is None
                or lift_date > last_lift_date
            ):
                last_lift_date = lift_date

        # -------------------------------------------------
        # ITEM
        # -------------------------------------------------

        report_items.append(
            {
                "id": chit.id,

                "name": chit.name,

                "code": chit.code,

                "chit_value": chit_value,

                "monthly_emi": money(
                    chit.monthly_emi
                ),

                "duration_months": int(
                    chit.duration_months or 0
                ),

                "max_members": int(
                    chit.max_members or 0
                ),

                "start_date": (
                    _date_value(
                        chit.start_date
                    )
                ),

                "status": status_value,

                "member_count": member_count,

                "confirmed_members": (
                    confirmed_count
                ),

                "active_members": (
                    active_count
                ),

                "scheduled_amount": (
                    scheduled_amount
                ),

                "collected_amount": (
                    collected_amount
                ),

                "outstanding_amount": (
                    outstanding_amount
                ),

                "collection_rate": (
                    collection_rate
                ),

                "total_lifts": (
                    chit_lift_count
                ),

                "lifted_amount": (
                    chit_lifted_amount
                ),

                "discount_amount": (
                    chit_discount_amount
                ),

                "payout_completed": (
                    chit_completed_payouts
                ),

                "payout_pending": (
                    chit_pending_payouts
                ),

                "last_collection_date": (
                    last_collection_date
                ),

                "last_lift_date": (
                    last_lift_date
                ),
            }
        )

    # =====================================================
    # MONTHLY SUMMARY
    # =====================================================

    monthly_summary = []

    for chit in chits:

        chit_installments = (
            installments_by_chit.get(
                chit.id,
                [],
            )
        )

        chit_lifts = (
            lifts_by_chit.get(
                chit.id,
                [],
            )
        )

        lifts_by_month = {}

        for lift in chit_lifts:

            month_number = (
                lift.cycle_number
            )

            if (
                lift.chit_month_id
                and month_number is None
            ):
                month = (
                    db.query(ChitMonth)
                    .filter(
                        ChitMonth.id
                        == lift.chit_month_id
                    )
                    .first()
                )

                if month:
                    month_number = (
                        month.month_number
                    )

            if month_number is not None:
                lifts_by_month[
                    month_number
                ] = lift

        # -------------------------------------------------
        # MONTHS
        # -------------------------------------------------

        months = (
            db.query(ChitMonth)
            .filter(
                ChitMonth.chit_id == chit.id,
                ChitMonth.company_id
                == company_id,
            )
            .order_by(
                ChitMonth.month_number.asc()
            )
            .all()
        )

        for month in months:

            month_installments = [
                installment
                for installment
                in chit_installments
                if (
                    installment.installment_number
                    == month.month_number
                )
            ]

            scheduled_amount = sum(
                money(
                    installment.due_amount
                )
                for installment
                in month_installments
            )

            collected_amount = 0

            paid_installments = 0
            partial_installments = 0
            pending_installments = 0

            for installment in (
                month_installments
            ):

                due_amount = money(
                    installment.due_amount
                )

                paid_amount = money(
                    paid_by_installment.get(
                        installment.id,
                        0,
                    )
                )

                collected_amount += min(
                    paid_amount,
                    due_amount,
                )

                if paid_amount >= due_amount:
                    paid_installments += 1

                elif paid_amount > 0:
                    partial_installments += 1

                else:
                    pending_installments += 1

            outstanding_amount = max(
                scheduled_amount
                - collected_amount,
                0,
            )

            collection_rate = (
                round(
                    (
                        collected_amount
                        / scheduled_amount
                    )
                    * 100,
                    2,
                )
                if scheduled_amount > 0
                else 0.0
            )

            lift = lifts_by_month.get(
                month.month_number
            )

            if lift:

                lift_status = (
                    str(
                        lift.payout_status
                        or "pending"
                    )
                    .lower()
                )

                lifted_amount = money(
                    lift.lifted_amount
                )

                discount_amount = money(
                    lift.discount_amount
                )

            else:

                lift_status = "not_lifted"

                lifted_amount = 0
                discount_amount = 0

            monthly_summary.append(
                {
                    "chit_id": chit.id,

                    "chit_name": chit.name,

                    "chit_code": chit.code,

                    "installment_number": (
                        month.month_number
                    ),

                    "month_date": (
                        _date_value(
                            month.month_date
                        )
                    ),

                    "monthly_emi": money(
                        month.monthly_emi
                    ),

                    "monthly_lift_amount": money(
                        month.monthly_lift_amount
                    ),

                    "scheduled_amount": (
                        scheduled_amount
                    ),

                    "collected_amount": (
                        collected_amount
                    ),

                    "outstanding_amount": (
                        outstanding_amount
                    ),

                    "collection_rate": (
                        collection_rate
                    ),

                    "paid_installments": (
                        paid_installments
                    ),

                    "partial_installments": (
                        partial_installments
                    ),

                    "pending_installments": (
                        pending_installments
                    ),

                    "lift_status": lift_status,

                    "lifted_amount": (
                        lifted_amount
                    ),

                    "discount_amount": (
                        discount_amount
                    ),
                }
            )

    # =====================================================
    # GLOBAL COLLECTION RATE
    # =====================================================

    collection_rate = (
        round(
            (
                total_collected
                / total_scheduled
            )
            * 100,
            2,
        )
        if total_scheduled > 0
        else 0.0
    )

    # =====================================================
    # RESPONSE
    # =====================================================

    return {
        "company_id": company.id,

        "company_name": (
            company.company_name
        ),

        "logo_url": (
            company.logo_url
        ),

        "summary": {
            "total_chits": len(chits),

            "draft_chits": draft_chits,
            "active_chits": active_chits,
            "completed_chits": completed_chits,
            "cancelled_chits": cancelled_chits,

            "total_chit_value": (
                total_chit_value
            ),

            "total_members": (
                total_members
            ),

            "confirmed_members": (
                confirmed_members
            ),

            "active_members": (
                active_members
            ),

            "total_scheduled_amount": (
                total_scheduled
            ),

            "total_collected_amount": (
                total_collected
            ),

            "total_outstanding_amount": (
                max(
                    total_scheduled
                    - total_collected,
                    0,
                )
            ),

            "collection_rate": (
                collection_rate
            ),

            "total_lifts": (
                total_lifts
            ),

            "completed_payouts": (
                completed_payouts
            ),

            "pending_payouts": (
                pending_payouts
            ),

            "total_lifted_amount": (
                total_lifted_amount
            ),

            "total_discount_amount": (
                total_discount_amount
            ),
        },

        "items": report_items,

        "monthly_summary": (
            monthly_summary
        ),

        "total_records": len(
            report_items
        ),
    }


# =========================================================
# PAGINATED REPORT
# =========================================================

def get_chit_report(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    chit_id: Optional[int] = None,
    report_status: str = "all",
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
):

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

    report = _build_chit_report_data(
        db=db,
        company_id=company_id,

        date_from=date_from,
        date_to=date_to,

        chit_id=chit_id,

        report_status=report_status,

        search=search,
    )

    total_records = (
        report["total_records"]
    )

    total_pages = (
        ceil(
            total_records
            / page_size
        )
        if total_records > 0
        else 0
    )

    report["items"] = (
        report["items"][
            offset:
            offset + page_size
        ]
    )

    report["page"] = page
    report["page_size"] = page_size
    report["total_pages"] = total_pages

    return report


# =========================================================
# EXPORT DATA
# =========================================================

def get_chit_report_export_data(
    db: Session,
    company_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    chit_id: Optional[int] = None,
    report_status: str = "all",
    search: Optional[str] = None,
):

    return _build_chit_report_data(
        db=db,
        company_id=company_id,

        date_from=date_from,
        date_to=date_to,

        chit_id=chit_id,

        report_status=report_status,

        search=search,
    )