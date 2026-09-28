from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.chit_member import ChitMember
from app.models.admin.chitlift import ChitLift
from app.models.admin.company import Company
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.payment_transaction import PaymentTransaction


ZERO = Decimal("0.00")


def _decimal(value) -> Decimal:
    """Convert database numeric values without introducing float rounding."""

    return Decimal(str(value or 0))


def get_customer_dashboard(db: Session, mobile: str) -> dict:
    """
    Build the dashboard from records owned by the authenticated customer's mobile.

    The customer portal already uses mobile as the cross-company identity for
    ``/customer/my-chits``.  Keeping the same rule here means the dashboard
    includes every company membership visible to that customer.
    """

    active_portfolio = (
        db.query(
            ChitMember.id.label("chit_member_id"),
            ChitMember.status.label("member_status"),
            ChitGroup.id.label("chit_id"),
            ChitGroup.name.label("chit_name"),
            ChitGroup.code.label("chit_code"),
            ChitGroup.chit_value,
            ChitGroup.monthly_emi,
            ChitGroup.duration_months,
            ChitGroup.start_date,
            Company.id.label("company_id"),
            Company.company_name,
        )
        .join(CustomerProfile, CustomerProfile.id == ChitMember.customer_profile_id)
        .join(ChitGroup, ChitGroup.id == ChitMember.chit_id)
        .join(Company, Company.id == ChitGroup.company_id)
        .filter(
            CustomerProfile.mobile == mobile,
            CustomerProfile.status == "active",
            Company.status == "active",
            ChitGroup.status == "active",
            ChitMember.status.in_(["confirmed", "active"]),
        )
        .order_by(Company.company_name.asc(), ChitGroup.name.asc(), ChitMember.slot_number.asc())
        .all()
    )

    active_companies = len({row.company_id for row in active_portfolio})
    active_chit_net_worth = sum(
        (_decimal(row.chit_value) for row in active_portfolio),
        ZERO,
    )

    # Payments and dues intentionally include every customer slot, even a
    # completed one. They represent the customer's all-time payment position.
    total_due_amount = _decimal(
        db.query(func.coalesce(func.sum(ChitInstallment.due_amount), 0))
        .join(ChitMember, ChitMember.id == ChitInstallment.chit_member_id)
        .join(CustomerProfile, CustomerProfile.id == ChitMember.customer_profile_id)
        .filter(CustomerProfile.mobile == mobile)
        .scalar()
    )

    total_paid_amount = _decimal(
        db.query(func.coalesce(func.sum(PaymentTransaction.amount), 0))
        .join(ChitInstallment, ChitInstallment.id == PaymentTransaction.installment_id)
        .join(ChitMember, ChitMember.id == ChitInstallment.chit_member_id)
        .join(CustomerProfile, CustomerProfile.id == ChitMember.customer_profile_id)
        .filter(CustomerProfile.mobile == mobile)
        .scalar()
    )

    lift_rows = (
        db.query(
            ChitLift.id.label("lift_id"),
            ChitLift.chit_member_id,
            ChitLift.lift_date,
            ChitLift.lifted_amount,
            ChitLift.payout_status,
            ChitGroup.chit_value,
            ChitGroup.name.label("chit_name"),
            ChitGroup.code.label("chit_code"),
            Company.company_name,
        )
        .join(ChitMember, ChitMember.id == ChitLift.chit_member_id)
        .join(CustomerProfile, CustomerProfile.id == ChitMember.customer_profile_id)
        .join(ChitGroup, ChitGroup.id == ChitLift.chit_id)
        .join(Company, Company.id == ChitLift.company_id)
        .filter(CustomerProfile.mobile == mobile)
        .order_by(ChitLift.lift_date.desc(), ChitLift.id.desc())
        .all()
    )

    total_lifted_amount = sum(
        (_decimal(row.lifted_amount) for row in lift_rows),
        ZERO,
    )

    # The comparison is made only for actually lifted slots. This avoids
    # treating unlifted active chits as a loss and keeps the metric transparent
    # for the customer: payout received minus that chit's subscribed value.
    net_lift_result = sum(
        (_decimal(row.lifted_amount) - _decimal(row.chit_value) for row in lift_rows),
        ZERO,
    )
    lift_profit_amount = max(net_lift_result, ZERO)
    lift_loss_amount = abs(min(net_lift_result, ZERO))

    if net_lift_result > ZERO:
        lift_result_status = "profit"
    elif net_lift_result < ZERO:
        lift_result_status = "loss"
    else:
        lift_result_status = "neutral"

    active_chits = [
        {
            "chit_member_id": row.chit_member_id,
            "chit_id": row.chit_id,
            "company_id": row.company_id,
            "company_name": row.company_name,
            "chit_name": row.chit_name,
            "chit_code": row.chit_code,
            "chit_value": _decimal(row.chit_value),
            "monthly_emi": _decimal(row.monthly_emi),
            "duration_months": row.duration_months,
            "start_date": row.start_date,
            "member_status": row.member_status,
        }
        for row in active_portfolio
    ]

    recent_lifts = [
        {
            "lift_id": row.lift_id,
            "chit_member_id": row.chit_member_id,
            "company_name": row.company_name,
            "chit_name": row.chit_name,
            "chit_code": row.chit_code,
            "lift_date": row.lift_date,
            "lifted_amount": _decimal(row.lifted_amount),
            "payout_status": row.payout_status,
            "net_result": _decimal(row.lifted_amount) - _decimal(row.chit_value),
        }
        for row in lift_rows[:5]
    ]

    return {
        "summary": {
            "active_companies": active_companies,
            "active_chits": len(active_portfolio),
            "active_chit_net_worth": active_chit_net_worth,
            "total_lift_records": len(lift_rows),
            "total_lifted_amount": total_lifted_amount,
            "net_lift_result": net_lift_result,
            "lift_profit_amount": lift_profit_amount,
            "lift_loss_amount": lift_loss_amount,
            "lift_result_status": lift_result_status,
            "total_paid_amount": total_paid_amount,
            "total_pending_amount": max(total_due_amount - total_paid_amount, ZERO),
        },
        "active_chits": active_chits,
        "recent_lifts": recent_lifts,
    }
