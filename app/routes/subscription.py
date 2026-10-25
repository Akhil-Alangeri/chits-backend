from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.routes.super_admin_auth import require_super_admin
from app.core.dependencies import get_current_company_id
from app.models.admin.company import Company
from app.models.admin.subscription import SubscriptionPlan, Feature, PlanFeature, CompanyFeatureOverride, CompanySubscriptionEvent
from app.schemas.subscription import PlanInput, CompanySubscriptionInput
from app.services.entitlement_service import get_company_entitlements, plan_response, lock_company, assigned_plan
from app.services.audit_log_service import create_audit_log
from app.services.subscription_lifecycle import apply_transition, prorated_upgrade_quote
from app.services.subscription_transactions import retry_subscription_transaction

router = APIRouter(prefix="/super-admin", tags=["Subscriptions"], dependencies=[Depends(require_super_admin)])
company_router = APIRouter(prefix="/company", tags=["Company entitlements"])


def validate_features(db, keys):
    known = {f.key for f in db.query(Feature).all()}
    if set(keys) - known:
        raise HTTPException(422, "Unknown feature key.")


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Plan code already exists or subscription data conflicts.")


@router.get("/features")
def features(db=Depends(get_db)):
    return [{"key": f.key, "name": f.name} for f in db.query(Feature).order_by(Feature.key)]


@router.get("/plans")
def plans(db=Depends(get_db)):
    return [plan_response(db, p) for p in db.query(SubscriptionPlan).order_by(SubscriptionPlan.id)]


def save_plan(db, plan, data, actor=None):
    validate_features(db, data.features)
    before = plan_response(db, plan) if plan.id is not None else None
    commercial = {"starter": (9999, 3, 0), "growth": (14999, 7, 3), "business": (19999, 12, 5)}
    code = plan.code if plan.id is not None else data.code
    if code in commercial or data.code in commercial:
        if data.code != code:
            raise HTTPException(422, "Commercial plan codes cannot be changed or reused.")
        price, groups, staff = commercial[code]
        expected = {"price": Decimal(price), "billing_cycle": "yearly", "active_group_limit": groups,
                    "admin_account_limit": 1, "staff_account_limit": staff, "duration_months": 12}
        supplied = data.model_dump(exclude_unset=True)
        for field, value in expected.items():
            if supplied.get(field, getattr(plan, field, None)) != value:
                raise HTTPException(422, "Finalized commercial prices, capacities and duration cannot be changed.")
        matrix = {key: code == "business" if key == "audit_export" else
                  False if key == "whatsapp_automation" else code != "starter"
                  for key in ("loans", "expenses", "reports", "staff_permissions", "support_tickets", "audit_export", "whatsapp_automation")}
        if any(data.features.get(key, False) != value for key, value in matrix.items()):
            raise HTTPException(422, "Finalized commercial feature availability cannot be changed.")
    # Old clients omit new capacity fields; omission must preserve configured limits.
    for key, value in data.model_dump(exclude={"features"}, exclude_unset=True).items():
        setattr(plan, key, value)
    db.add(plan)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Plan code already exists.")
    db.query(PlanFeature).filter_by(plan_id=plan.id).delete()
    for key, enabled in data.features.items():
        db.add(PlanFeature(plan_id=plan.id, feature_key=key, enabled=enabled))
    db.flush()
    db.add(CompanySubscriptionEvent(company_id=None, actor_user_id=actor.id if actor else None,
        event_type="plan_update" if before else "plan_create", before_state=jsonable_encoder(before),
        after_state=jsonable_encoder(plan_response(db, plan))))
    commit(db)
    return plan_response(db, plan)


@router.post("/plans", status_code=201)
def create_plan(data: PlanInput, db=Depends(get_db), actor=Depends(require_super_admin)):
    return save_plan(db, SubscriptionPlan(), data, actor)


@router.put("/plans/{plan_id}")
def update_plan(plan_id: int, data: PlanInput, db=Depends(get_db), actor=Depends(require_super_admin)):
    plan = db.query(SubscriptionPlan).filter_by(id=plan_id).populate_existing().with_for_update().first()
    if plan is None:
        raise HTTPException(404, "Plan not found.")
    return save_plan(db, plan, data, actor)


@router.get("/companies/{company_id}/subscription")
def company_subscription(company_id: int, db=Depends(get_db)):
    return get_company_entitlements(db, company_id)


@router.get("/companies/{company_id}/subscription/upgrade-quote")
def upgrade_quote(company_id: int, plan_id: int = Query(gt=0), db=Depends(get_db)):
    company = db.get(Company, company_id)
    target = db.get(SubscriptionPlan, plan_id)
    if company is None or target is None:
        raise HTTPException(404, "Company or plan not found.")
    return prorated_upgrade_quote(company, assigned_plan(db, company), target)


@router.get("/companies/{company_id}/subscription/events")
def subscription_events(company_id: int, db=Depends(get_db), limit: int = Query(default=50, ge=1, le=100)):
    if db.get(Company, company_id) is None:
        raise HTTPException(404, "Company not found.")
    rows = db.query(CompanySubscriptionEvent).filter_by(company_id=company_id).order_by(CompanySubscriptionEvent.id.desc()).limit(limit).all()
    return [{field: getattr(row, field) for field in ("id", "company_id", "actor_user_id", "event_type",
             "before_state", "after_state", "reason", "approved_reference", "created_at")} for row in rows]


@router.put("/companies/{company_id}/subscription")
@retry_subscription_transaction
def set_company_subscription(company_id: int, data: CompanySubscriptionInput,
                             db=Depends(get_db), actor=Depends(require_super_admin)):
    company = lock_company(db, company_id)
    current_plan = assigned_plan(db, company, current=True)
    plan = db.query(SubscriptionPlan).filter_by(id=data.plan_id).populate_existing().with_for_update(read=True).first()
    if plan is None:
        raise HTTPException(404, "Plan not found.")
    if not plan.is_active and company.subscription_plan_id != plan.id:
        raise HTTPException(422, "Inactive plans cannot be assigned.")
    validate_features(db, data.overrides)
    before = get_company_entitlements(db, company_id, current=True)
    event_type, quote = apply_transition(db, company, current_plan, plan, data, actor)
    for key, enabled in data.overrides.items():
        row = (db.query(CompanyFeatureOverride).filter_by(company_id=company_id, feature_key=key)
               .populate_existing().with_for_update().first())
        if enabled is None:
            if row is not None:
                db.delete(row)
        elif row is not None:
            row.enabled = enabled
        else:
            db.add(CompanyFeatureOverride(company_id=company_id, feature_key=key, enabled=enabled))
    db.flush()
    after = get_company_entitlements(db, company_id, current=True)
    event_state = {**after, "upgrade_quote": quote} if quote else after
    db.add(CompanySubscriptionEvent(company_id=company_id, actor_user_id=actor.id if actor else None,
        event_type=event_type, before_state=jsonable_encoder(before), after_state=jsonable_encoder(event_state),
        reason=data.reason, approved_reference=data.approved_reference))
    create_audit_log(db, company_id=company_id, user_id=actor.id if actor else None, action="update",
                     module="subscription", description="Company subscription and feature overrides updated",
                     entity_type="company", entity_id=company_id, old_values=before, new_values=after)
    commit(db)
    return after


@company_router.get("/entitlements")
def own_entitlements(company_id=Depends(get_current_company_id), db=Depends(get_db)):
    return get_company_entitlements(db, company_id)
