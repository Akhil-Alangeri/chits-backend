from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from app.core.database import Base


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    company_id = Column(
        BigInteger,
        ForeignKey("companies.id"),
        nullable=False,
    )

    chit_member_id = Column(
        BigInteger,
        ForeignKey("chit_members.id"),
        nullable=False,
    )

    notification_type = Column(
        String(50),
        nullable=False,
    )

    notification_month = Column(
        String(7),
        nullable=False,
    )

    status = Column(
        String(20),
        nullable=False,
        default="sent",
    )

    sent_at = Column(
        DateTime,
        nullable=True,
    )

    error_message = Column(
        String(500),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "chit_member_id",
            "notification_type",
            "notification_month",
            name="uq_member_notification_month",
        ),
    )