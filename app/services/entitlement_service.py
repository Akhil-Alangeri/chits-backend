"""Company entitlements and transaction-local capacity checks. No helper commits."""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from sqlalchemy import func

from app.core.database import get_db
from app.core.dependencies import get_current_company_id
from app.models.admin.company import Company
from app.models.admin.chit_group import ChitGroup
from app.models.admin.user import User
from app.models.admin.subscription import (
    SubscriptionPlan, Feature, PlanFeature, CompanyFeatureOverride, CompanyAddon,
)

LOANS = "loans"
EXPENSES = "expenses"
CAPACITY_STATUSES = frozenset({"active", "upcoming", "paused"})
GRACE_DAYS = 15
CORE_FEATURES = {key: True for key in (
    "customer_management", "chit_groups", "payments", "collections", "auctions",
    "customer_portal", "audit_history",
)}
LEGACY_FEATURES = {"reports": True, "staff_permissions": True, "support_tickets": True}
LIMIT_FIELDS = {
    "active_groups": "active_group_limit",
    "admin_accounts": "admin_account_limit",
    "staff_accounts": "staff_account_limit",
}


def utc_naive(value):
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def restriction(code, message, **context):
    raise HTTPException(403, {"code": code, "message": message, **context})


def lock_company(db, company_id):
    # Authentication may already have cached the row. This must be a fresh,
    # locking current read even with a prior MySQL REPEATABLE READ snapshot.
    company = (db.query(Company).filter(Company.id == company_id)
               .populate_existing().with_for_update().first())
    if company is None:
        raise HTTPException(404, "Company not found.")
    return company


def assigned_plan(db, company, *, current=False):
    if not company.subscription_plan_id:
        return None
    query = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == company.subscription_plan_id)
    if current:
        query = query.populate_existing().with_for_update(read=True)
    return query.first()


def is_legacy(company, plan):
    # Existing custom/unassigned accounts have no invented commercial contract.
    return (company.subscription_status is None
            and company.subscription_started_at is None and company.subscription_ends_at is None
            and (plan is None or all(getattr(plan, field) is None for field in LIMIT_FIELDS.values())))


def subscription_state(company, plan, *, now=None):
    now = utc_naive(now) if now is not None else datetime.now(timezone.utc).replace(tzinfo=None)
    start, end = utc_naive(company.subscription_started_at), utc_naive(company.subscription_ends_at)
    grace_end = end + timedelta(days=GRACE_DAYS) if end else None
    if is_legacy(company, plan):
        state, allowed = "legacy", True
    elif (plan is None or start is None or end is None or end <= start
          or company.subscription_status not in {"active", "expired"}):
        state, allowed = "needs_review", False
    elif now < start:
        state, allowed = "scheduled", False
    elif now < end:
        state, allowed = "active", True
    elif now < grace_end:
        state, allowed = "grace", True
    else:
        state, allowed = "expired", False
    return {"status": state, "started_at": start, "ends_at": end,
            "grace_ends_at": grace_end, "grace_days": GRACE_DAYS,
            "capacity_increases_allowed": allowed,
            "pending_plan_id": company.pending_subscription_plan_id,
            "pending_effective_at": company.pending_subscription_effective_at}


def plan_response(db, plan, *, current=False):
    if plan is None:
        return None
    fields = ("id", "name", "code", "description", "price", "billing_cycle", "is_active",
              "active_group_limit", "admin_account_limit", "staff_account_limit", "duration_months",
              "created_at", "updated_at")
    query = db.query(PlanFeature).filter_by(plan_id=plan.id)
    if current:
        query = query.populate_existing().with_for_update(read=True)
    return {**{key: getattr(plan, key) for key in fields},
            "features": {row.feature_key: row.enabled for row in query}}


def capacity_usage(db, company_id, *, current=False):
    groups = db.query(ChitGroup.id).filter(
        ChitGroup.company_id == company_id,
        func.lower(func.trim(ChitGroup.status)).in_(CAPACITY_STATUSES))
    users = db.query(User.id, User.role).filter(
        User.company_id == company_id, User.status == "active",
        User.role.in_(["company_admin", "company_user"]))
    if current:
        # Read rows instead of a snapshot COUNT(*). This sees a predecessor's
        # commit after waiting for the company mutex, including under MySQL RR.
        groups, users = groups.with_for_update(), users.with_for_update()
    group_rows, user_rows = groups.all(), users.all()
    return {"active_groups": len(group_rows),
            "admin_accounts": sum(role == "company_admin" for _, role in user_rows),
            "staff_accounts": sum(role == "company_user" for _, role in user_rows)}


def get_company_entitlements(db, company_id, *, current=False, include_usage=True):
    company = lock_company(db, company_id) if current else db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found.")
    plan = assigned_plan(db, company, current=current)
    def read(query):
        return query.populate_existing().with_for_update(read=True) if current else query
    defaults = {feature.key: False for feature in read(db.query(Feature)).all()}
    if is_legacy(company, plan):
        defaults.update(LEGACY_FEATURES)
    # Inactive catalog plans retain already assigned company access.
    if plan:
        defaults.update({row.feature_key: bool(row.enabled) for row in read(db.query(PlanFeature).filter_by(plan_id=plan.id))})
    overrides = {row.feature_key: bool(row.enabled) for row in read(db.query(CompanyFeatureOverride).filter_by(company_id=company_id))}
    features = {**defaults, **overrides, **CORE_FEATURES}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    addon = read(db.query(CompanyAddon.id).filter(
        CompanyAddon.company_id == company_id, CompanyAddon.addon_key == "whatsapp_automation",
        CompanyAddon.status == "active", CompanyAddon.starts_at <= now, CompanyAddon.ends_at > now,
        CompanyAddon.approved_payment_reference.isnot(None),
        func.length(func.trim(CompanyAddon.approved_payment_reference)) > 0,
        CompanyAddon.approved_by_user_id.isnot(None))).first()
    features["whatsapp_automation"] = bool(addon) and overrides.get("whatsapp_automation", True)
    return {"plan": plan_response(db, plan, current=current), "plan_features": {**defaults, **CORE_FEATURES},
            "overrides": overrides, "features": features,
            "limits": {key: getattr(plan, field) if plan else None for key, field in LIMIT_FIELDS.items()},
            "usage": capacity_usage(db, company_id, current=current) if include_usage else None,
            "subscription": subscription_state(company, plan, now=now)}


def get_company_effective_features(db, company_id):
    return get_company_entitlements(db, company_id, include_usage=False)["features"]


def has_company_feature(db, company_id, feature_key):
    return get_company_effective_features(db, company_id).get(feature_key, False)


def ensure_company_feature(db, company_id, feature_key, *, current=False):
    if not get_company_entitlements(db, company_id, current=current, include_usage=False)["features"].get(feature_key, False):
        restriction("FEATURE_NOT_AVAILABLE", "This feature requires an eligible subscription plan.", feature=feature_key)


def require_company_feature(feature_key):
    def check(company_id=Depends(get_current_company_id), db=Depends(get_db)):
        ensure_company_feature(db, company_id, feature_key)
    return check


def ensure_capacity(db, company_id, resource, *, bootstrap_admin=False):
    company = lock_company(db, company_id)
    plan = assigned_plan(db, company, current=True)
    used = capacity_usage(db, company_id, current=True)[resource]
    state = subscription_state(company, plan)
    if not (bootstrap_admin and used == 0) and not state["capacity_increases_allowed"]:
        code = "SUBSCRIPTION_EXPIRED" if state["status"] == "expired" else "SUBSCRIPTION_REVIEW_REQUIRED"
        restriction(code, "Renew or review the subscription before increasing capacity.", resource=resource,
                    subscription_status=state["status"])
    limit = getattr(plan, LIMIT_FIELDS[resource]) if plan else None
    if limit is not None and used >= limit:
        restriction("PLAN_LIMIT_REACHED", "Your plan capacity has been reached. Review your plan to add capacity.",
                    resource=resource, used=used, limit=limit, plan_code=plan.code)


def ensure_group_capacity(db, company_id):
    ensure_capacity(db, company_id, "active_groups")


def ensure_staff_capacity(db, company_id):
    ensure_capacity(db, company_id, "staff_accounts")


def ensure_admin_capacity(db, company_id):
    ensure_capacity(db, company_id, "admin_accounts", bootstrap_admin=True)
