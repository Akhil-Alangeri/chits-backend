"""Durable membership notification intent; stores no email bodies or credentials."""
from datetime import datetime, UTC

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, UniqueConstraint

from app.core.database import Base


def utc_now():
    # Match the application's UTC, timezone-naive MySQL DATETIME convention.
    return datetime.now(UTC).replace(tzinfo=None)


class WelcomeOutbox(Base):
    __tablename__ = "membership_welcome_outbox"
    __table_args__ = (
        UniqueConstraint("membership_id", "notification_type", name="uq_membership_welcome_type"),
        Index("ix_welcome_due", "status", "available_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # Deliberately no FK: retain deduplication history without blocking existing deletes.
    membership_id = Column(BigInteger, nullable=False)
    company_id = Column(BigInteger, nullable=False)
    notification_type = Column(String(50), nullable=False, default="membership_welcome")
    status = Column(String(20), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, nullable=True, default=utc_now)
    claim_token = Column(String(36), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    last_error = Column(String(80), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
