from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class ChitMonth(Base):
    __tablename__ = "chit_months"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    company_id = Column(
        BigInteger,
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    chit_id = Column(
        BigInteger,
        ForeignKey("chit_groups.id"),
        nullable=False,
        index=True,
    )

    # =========================================================
    # MONTH
    # =========================================================

    month_number = Column(
        Integer,
        nullable=False,
    )

    month_date = Column(
        Date,
        nullable=False,
    )

    # =========================================================
    # MONTHLY FINANCIAL VALUES
    # =========================================================

    monthly_emi = Column(
        Numeric(12, 2),
        nullable=False,
    )

    monthly_lift_amount = Column(
        Numeric(12, 2),
        nullable=False,
    )

    # =========================================================
    # TIMESTAMPS
    # =========================================================

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    company = relationship(
        "Company",
        back_populates="chit_months",
    )

    chit = relationship(
        "ChitGroup",
        back_populates="months",
    )
    
    lifts = relationship(
        "ChitLift",
        back_populates="chit_month",
    )

    # =========================================================
    # CONSTRAINTS
    # =========================================================

    __table_args__ = (
        UniqueConstraint(
            "chit_id",
            "month_number",
            name="uq_chit_month_number",
        ),
    )