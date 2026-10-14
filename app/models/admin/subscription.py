from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Numeric, String, Text, func
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
