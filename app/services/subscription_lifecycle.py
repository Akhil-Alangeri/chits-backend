"""Explicit administrative subscription transitions; never bills or auto-renews."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException

from app.services.entitlement_service import capacity_usage, restriction, utc_naive, LIMIT_FIELDS


def require_administrative_workflow(data, actor):
    if (data.workflow != "administrative" or not data.reason or not data.reason.strip()
            or actor is None or actor.role != "super_admin" or actor.company_id is not None):
        restriction("SUBSCRIPTION_APPROVAL_REQUIRED",
                    "An authenticated administrative workflow and reason are required. No payment is charged or verified by this API.")


def prorated_upgrade_quote(company, current_plan, target_plan, *, now=None):
    now = utc_naive(now) if now else datetime.now(timezone.utc).replace(tzinfo=None)
    start, end = utc_naive(company.subscription_started_at), utc_naive(company.subscription_ends_at)
    if not current_plan or not start or not end or not start <= now < end:
        raise HTTPException(422, "An active subscription term is required for a mid-year upgrade.")
    if (current_plan.duration_months != 12 or target_plan.duration_months != 12 or not target_plan.is_active
            or current_plan.id == target_plan.id
            or any(getattr(current_plan, field) is None or getattr(target_plan, field) is None
                   or getattr(target_plan, field) < getattr(current_plan, field) for field in LIMIT_FIELDS.values())):
        raise HTTPException(422, "Select an active annual plan that preserves or increases every capacity.")
    # The denominator is the annual term ending on the unchanged renewal date;
    # sequential upgrades must not shorten it to the last upgrade date.
    annual_start = end - relativedelta(months=12)
    fraction = Decimal(str((end - now).total_seconds())) / Decimal(str((end - annual_start).total_seconds()))
    difference = Decimal(target_plan.price) - Decimal(current_plan.price)
    if difference < 0:
        raise HTTPException(422, "Use the scheduled downgrade workflow for a lower-priced plan.")
    return {"amount": (difference * min(fraction, Decimal(1))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "currency": "INR", "renewal_at": end, "quoted_at": now,
            "requires_administrative_approval": True, "charged": False}


def check_target_capacity(db, company_id, plan):
    usage = capacity_usage(db, company_id, current=True)
    for resource, field in LIMIT_FIELDS.items():
        limit = getattr(plan, field)
        if limit is not None and usage[resource] > limit:
            restriction("PLAN_LIMIT_REACHED", "Current resource usage exceeds the selected plan's capacity.",
                        resource=resource, used=usage[resource], limit=limit, plan_code=plan.code)


def apply_transition(db, company, current_plan, target_plan, data, actor):
    """Caller holds the company lock and commits state, event and audit together."""
    action = data.action
    changing = company.subscription_plan_id != target_plan.id
    commercial = target_plan.duration_months is not None
    managed = company.subscription_started_at is not None or (current_plan and current_plan.duration_months is not None)
    if not action:
        if changing and (commercial or managed):
            restriction("SUBSCRIPTION_APPROVAL_REQUIRED", "Select an approved administrative subscription action.")
        if changing:
            company.subscription_plan_id = target_plan.id  # Existing custom-plan API contract.
        return "assignment" if changing else "overrides", None
    require_administrative_workflow(data, actor)
    if data.starts_at is not None and action != "assign":
        raise HTTPException(422, "starts_at is only accepted for initial assignment.")
    if not commercial or target_plan.duration_months != 12:
        raise HTTPException(422, "Commercial transitions require a configured 12-month plan.")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    quote = None
    if action == "assign":
        if company.subscription_started_at is not None or company.subscription_ends_at is not None:
            raise HTTPException(422, "Use upgrade, renewal or scheduled downgrade for an existing commercial subscription.")
        start = utc_naive(data.starts_at) if data.starts_at else now
        company.subscription_started_at = start
        company.subscription_ends_at = start + relativedelta(months=12)
        company.subscription_status = "active"
        company.subscription_plan_id = target_plan.id
    elif action == "upgrade":
        if not current_plan or not changing or any(
            getattr(current_plan, field) is None or getattr(target_plan, field) is None
            or getattr(target_plan, field) < getattr(current_plan, field) for field in LIMIT_FIELDS.values()
        ):
            raise HTTPException(422, "An upgrade must preserve or increase every plan capacity.")
        quote = prorated_upgrade_quote(company, current_plan, target_plan, now=now)
        company.subscription_plan_id = target_plan.id
        company.pending_subscription_plan_id = None
        company.pending_subscription_effective_at = None



    elif action == "correct_plan":
        # Immediate administrative correction of an
        # incorrectly assigned commercial plan.

        if not current_plan or not changing:
            raise HTTPException(
                status_code=422,
                detail="Select a different plan for correction.",
            )

        if current_plan.duration_months != 12:
            raise HTTPException(
                status_code=422,
                detail="Only existing annual plans can be corrected.",
            )

        start = utc_naive(company.subscription_started_at)
        end = utc_naive(company.subscription_ends_at)

        if not start or not end or not (start <= now < end):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Plan correction requires a currently active "
                    "subscription term."
                ),
            )

        if company.subscription_status != "active":
            raise HTTPException(
                status_code=422,
                detail="Subscription must be active for plan correction.",
            )

        # Prevent conflicting scheduled operations.
        if (
            company.pending_subscription_plan_id is not None
            or company.pending_subscription_effective_at is not None
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Cancel the pending downgrade before "
                    "correcting the assigned plan."
                ),
            )

        # Prevent losing access to existing active resources.
        check_target_capacity(db, company.id, target_plan)

        # Preserve the original subscription term.
        company.subscription_plan_id = target_plan.id


    elif action == "schedule_downgrade":
        if (not current_plan or not changing or not company.subscription_ends_at
                or now >= company.subscription_ends_at
                or Decimal(target_plan.price) >= Decimal(current_plan.price)
                or any(getattr(target_plan, field) is None or getattr(current_plan, field) is None
                       or getattr(target_plan, field) > getattr(current_plan, field) for field in LIMIT_FIELDS.values())):
            raise HTTPException(422, "A downgrade must reduce plan price without increasing capacity and be scheduled before renewal.")
        check_target_capacity(db, company.id, target_plan)
        company.pending_subscription_plan_id = target_plan.id
        company.pending_subscription_effective_at = company.subscription_ends_at
    elif action == "cancel_downgrade":
        if target_plan.id != company.subscription_plan_id:
            raise HTTPException(422, "Use the current plan when cancelling a scheduled downgrade.")
        company.pending_subscription_plan_id = None
        company.pending_subscription_effective_at = None
    elif action in {"renew", "apply_downgrade"}:
        if not company.subscription_ends_at or now < company.subscription_ends_at:
            raise HTTPException(422, "Renewal is not due yet.")
        if action == "renew" and (changing or company.pending_subscription_plan_id):
            raise HTTPException(422, "Apply or cancel the scheduled downgrade before renewal.")
        if action == "apply_downgrade":
            if (target_plan.id != company.pending_subscription_plan_id or not company.pending_subscription_effective_at
                    or now < company.pending_subscription_effective_at):
                raise HTTPException(422, "This plan has no downgrade due for application.")
            check_target_capacity(db, company.id, target_plan)
        start = company.subscription_ends_at if now < company.subscription_ends_at + timedelta(days=15) else now
        company.subscription_started_at = start
        company.subscription_ends_at = start + relativedelta(months=12)
        company.subscription_status = "active"
        company.subscription_plan_id = target_plan.id
        company.pending_subscription_plan_id = None
        company.pending_subscription_effective_at = None
    return action, quote
