"""Dedicated recovery state; never shared with Super Admin recovery."""
from sqlalchemy import Column, String, Integer, DateTime, BigInteger, ForeignKey
from app.core.database import Base

class CompanyRecovery(Base):
    __tablename__ = "company_password_recovery"
    user_id = Column(BigInteger, ForeignKey("users.id"), primary_key=True)
    otp_hash = Column(String(64))
    otp_expires = Column(DateTime)
    sent_at = Column(DateTime)
    attempts = Column(Integer, nullable=False, default=0)
    token_hash = Column(String(64), unique=True)
    token_expires = Column(DateTime)
    password_fingerprint = Column(String(64))

class RecoveryRate(Base):
    __tablename__ = "company_recovery_rate"
    key = Column(String(64), primary_key=True)
    window_start = Column(DateTime, nullable=False)
    count = Column(Integer, nullable=False)
