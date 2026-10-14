from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.dependencies import get_current_company_id
from app.models.admin.company import Company
from app.models.admin.subscription import SubscriptionPlan, Feature, PlanFeature, CompanyFeatureOverride
from app.schemas.subscription import PlanInput, CompanySubscriptionInput
from app.services.entitlement_service import get_company_entitlements, plan_response
from app.services.audit_log_service import create_audit_log

# Login-free platform management, per the requested Super Admin behavior.
# Deployment must restrict these routes externally if exposed to a public network.
router = APIRouter(prefix="/super-admin", tags=["Subscriptions"])
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


def save_plan(db, plan, data):
    validate_features(db, data.features)
    for key, value in data.model_dump(exclude={"features"}).items():
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
    commit(db)
    return plan_response(db, plan)


@router.post("/plans", status_code=201)
def create_plan(data: PlanInput, db=Depends(get_db)):
    return save_plan(db, SubscriptionPlan(), data)


@router.put("/plans/{plan_id}")
def update_plan(plan_id: int, data: PlanInput, db=Depends(get_db)):
    plan = db.get(SubscriptionPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found.")
    return save_plan(db, plan, data)


@router.get("/companies/{company_id}/subscription")
def company_subscription(company_id: int, db=Depends(get_db)):
    return get_company_entitlements(db, company_id)


@router.put("/companies/{company_id}/subscription")
def set_company_subscription(company_id: int, data: CompanySubscriptionInput,
                             db=Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found.")
    plan = db.get(SubscriptionPlan, data.plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found.")
    if not plan.is_active and company.subscription_plan_id != plan.id:
        raise HTTPException(422, "Inactive plans cannot be assigned.")
    validate_features(db, data.overrides)
    before = get_company_entitlements(db, company_id)
    company.subscription_plan_id = plan.id
    for key, enabled in data.overrides.items():
        row = db.get(CompanyFeatureOverride, (company_id, key))
        if enabled is None:
            if row is not None:
                db.delete(row)
        elif row is not None:
            row.enabled = enabled
        else:
            db.add(CompanyFeatureOverride(company_id=company_id, feature_key=key, enabled=enabled))
    db.flush()
    after = get_company_entitlements(db, company_id)
    create_audit_log(db, company_id=company_id, user_id=None, action="update",
                     module="subscription", description="Company subscription and feature overrides updated",
                     entity_type="company", entity_id=company_id, old_values=before, new_values=after)
    commit(db)
    return after


@company_router.get("/entitlements")
def own_entitlements(company_id=Depends(get_current_company_id), db=Depends(get_db)):
    return get_company_entitlements(db, company_id)
