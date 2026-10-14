from fastapi import Depends, HTTPException
from app.core.database import get_db
from app.core.dependencies import get_current_company_id
from app.models.admin.company import Company
from app.models.admin.subscription import SubscriptionPlan, Feature, PlanFeature, CompanyFeatureOverride

LOANS = "loans"
EXPENSES = "expenses"


def plan_response(db, plan):
    if plan is None:
        return None
    return {**{key: getattr(plan, key) for key in (
        "id", "name", "code", "description", "price", "billing_cycle", "is_active", "created_at", "updated_at")},
        "features": {row.feature_key: row.enabled for row in db.query(PlanFeature).filter_by(plan_id=plan.id)}}


def get_company_entitlements(db, company_id):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found.")
    plan = db.get(SubscriptionPlan, company.subscription_plan_id) if company.subscription_plan_id else None
    defaults = {feature.key: False for feature in db.query(Feature).all()}
    # Inactive plans retain existing assignments/access, but cannot be newly assigned.
    if plan:
        defaults.update({row.feature_key: bool(row.enabled) for row in db.query(PlanFeature).filter_by(plan_id=plan.id)})
    overrides = {row.feature_key: bool(row.enabled) for row in db.query(CompanyFeatureOverride).filter_by(company_id=company_id)}
    return {"plan": plan_response(db, plan), "plan_features": defaults,
            "overrides": overrides, "features": {**defaults, **overrides}}


def get_company_effective_features(db, company_id):
    return get_company_entitlements(db, company_id)["features"]


def has_company_feature(db, company_id, feature_key):
    return get_company_effective_features(db, company_id).get(feature_key, False)


def require_company_feature(feature_key):
    def check(company_id=Depends(get_current_company_id), db=Depends(get_db)):
        if not has_company_feature(db, company_id, feature_key):
            label = {LOANS: "Loan", EXPENSES: "Expenses"}.get(feature_key, feature_key)
            raise HTTPException(403, f"{label} module is not available in your current subscription plan.")
    return check
