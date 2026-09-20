from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class ChitLift(Base):
    __tablename__ = "chit_lifts"

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

    chit_member_id = Column(
        BigInteger,
        ForeignKey("chit_members.id"),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------------------
    # Historical snapshot
    # ---------------------------------------------------------

    customer_name = Column(
        String(150),
        nullable=False,
    )

    member_number = Column(
        String(50),
        nullable=False,
    )

    slot_number = Column(
        Integer,
        nullable=True,
    )

    # ---------------------------------------------------------
    # Lift details
    # ---------------------------------------------------------

    # Legacy field - keep temporarily for old lift records
    cycle_number = Column(
        Integer,
        nullable=True,
    )

    # New authoritative month reference
    chit_month_id = Column(
        BigInteger,
        ForeignKey("chit_months.id"),
        nullable=True,
        index=True,
    )

    lift_date = Column(
        Date,
        nullable=False,
    )

    # ---------------------------------------------------------
    # Additional / discount amount
    #
    # Business meaning in our application:
    #
    # monthly_lift_amount + discount_amount
    # = actual lifted_amount
    # ---------------------------------------------------------

    discount_amount = Column(
        Numeric(12, 2),
        nullable=True,
        default=0,
    )

    # ---------------------------------------------------------
    # Actual amount given to the customer
    # ---------------------------------------------------------

    lifted_amount = Column(
        Numeric(12, 2),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Payout
    # ---------------------------------------------------------

    payout_status = Column(
        String(30),
        nullable=False,
        default="pending",
    )

    payout_date = Column(
        Date,
        nullable=True,
    )

    # ---------------------------------------------------------
    # Notes / audit
    # ---------------------------------------------------------

    notes = Column(
        Text,
        nullable=True,
    )

    edit_reason = Column(
        Text,
        nullable=True,
    )

    # ---------------------------------------------------------
    # Timestamps
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    company = relationship(
        "Company",
        back_populates="chit_lifts",
    )

    chit = relationship(
        "ChitGroup",
        back_populates="lifts",
    )

    member = relationship(
        "ChitMember",
        back_populates="lifts",
    )

    chit_month = relationship(
        "ChitMonth",
        back_populates="lifts",
    )
    
    # ---------------------------------------------------------
# Payment split
# ---------------------------------------------------------

    upi_amount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    cash_amount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    # ---------------------------------------------------------
    # Business uniqueness
    # ---------------------------------------------------------

    __table_args__ = (
        # Legacy uniqueness - keep temporarily
        UniqueConstraint(
            "chit_id",
            "cycle_number",
            name="uq_chit_lift_cycle",
        ),

        # One actual lift per chit month
        UniqueConstraint(
            "chit_month_id",
            name="uq_chit_lift_month",
        ),

        # One specific chit member / slot can be lifted only once
        UniqueConstraint(
            "chit_id",
            "chit_member_id",
            name="uq_chit_member_lift",
        ),
    )