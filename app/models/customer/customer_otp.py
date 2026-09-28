from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    String,
    Boolean,
    ForeignKey,
)
from sqlalchemy.sql import func

from app.core.database import Base


class CustomerOTP(Base):
    __tablename__ = "customer_otps"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    customer_profile_id = Column(
        BigInteger,
        ForeignKey("customer_profiles.id"),
        nullable=False,
        index=True,
    )

    mobile = Column(
        String(20),
        nullable=False,
        index=True,
    )

    otp_hash = Column(
        String(255),
        nullable=False,
    )

    expires_at = Column(
        DateTime,
        nullable=False,
        index=True,
    )

    is_used = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    attempts = Column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    used_at = Column(
        DateTime,
        nullable=True,
    )