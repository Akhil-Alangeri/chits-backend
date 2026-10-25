from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
from app.core.database import Base


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    code = Column(String(80), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    price = Column(Numeric(12, 2), nullable=False)
    billing_cycle = Column(String(20), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    # NULL preserves the behavior of plans configured before capacity enforcement.
    active_group_limit = Column(Integer, nullable=True)
    admin_account_limit = Column(Integer, nullable=True)
    staff_account_limit = Column(Integer, nullable=True)
    duration_months = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class Feature(Base):
    __tablename__ = "features"
    key = Column(String(80), primary_key=True)
    name = Column(String(150), nullable=False)


class PlanFeature(Base):
    __tablename__ = "plan_features"
    plan_id = Column(BigInteger, ForeignKey("subscription_plans.id"), primary_key=True)
    feature_key = Column(String(80), ForeignKey("features.key"), primary_key=True)
    enabled = Column(Boolean, nullable=False)


class CompanyFeatureOverride(Base):
    __tablename__ = "company_feature_overrides"
    company_id = Column(BigInteger, ForeignKey("companies.id"), primary_key=True)
    feature_key = Column(String(80), ForeignKey("features.key"), primary_key=True)
    enabled = Column(Boolean, nullable=False)


class CompanySubscriptionEvent(Base):
    """Append-only subscription/catalog history, separate from financial audits.

    A NULL company denotes a platform catalog event; company lifecycle events
    always retain their company identifier.
    """

    __tablename__ = "company_subscription_events"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(BigInteger, ForeignKey("companies.id"), nullable=True, index=True)
    actor_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    event_type = Column(String(50), nullable=False)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=False)
    reason = Column(Text, nullable=True)
    approved_reference = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class CompanyAddon(Base):
    """Paid add-on approvals; a plan feature or override alone cannot grant access."""

    __tablename__ = "company_addons"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    addon_key = Column(String(80), nullable=False)
    status = Column(String(30), nullable=False)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    approved_payment_reference = Column(String(255), nullable=False)
    approved_by_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
