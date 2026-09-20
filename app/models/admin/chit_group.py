from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class ChitGroup(Base):

    __tablename__ = "chit_groups"

    # =====================================================
    # PRIMARY KEY
    # =====================================================

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # =====================================================
    # COMPANY
    # =====================================================

    company_id = Column(
        BigInteger,
        ForeignKey("companies.id"),
        nullable=False,
        index=True
    )

    # =====================================================
    # CHIT INFORMATION
    # =====================================================

    name = Column(
        String(150),
        nullable=False
    )

    code = Column(
        String(50),
        nullable=False,
        index=True
    )

    # =====================================================
    # FINANCIAL DETAILS
    # =====================================================

    chit_value = Column(
        Numeric(15, 2),
        nullable=False
    )

    monthly_emi = Column(
        Numeric(15, 2),
        nullable=False
    )

    duration_months = Column(
        Integer,
        nullable=False
    )

    max_members = Column(
        Integer,
        nullable=False
    )

    # =====================================================
    # START DATE
    # =====================================================

    start_date = Column(
        Date,
        nullable=True
    )

    # =====================================================
    # STATUS
    # =====================================================

    status = Column(
        String(20),
        nullable=False,
        default="draft"
    )

    # =====================================================
    # TIMESTAMPS
    # =====================================================

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )
    status=Column(
        String(20),
        nullable=False,
        default="draft"
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    company = relationship(
        "Company",
        back_populates="chit_groups"
    )
    
    members = relationship(
        "ChitMember",
        back_populates="chit",
        cascade="all, delete-orphan",
    )
    
    lifts = relationship(
        "ChitLift",
        back_populates="chit",
    )
    
    months = relationship(
        "ChitMonth",
        back_populates="chit",
        cascade="all, delete-orphan",
        order_by="ChitMonth.month_number",
    ) 