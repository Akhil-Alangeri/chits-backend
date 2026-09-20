from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Loan(Base):
    __tablename__ = "loans"

    # =========================================================
    # PRIMARY KEY
    # =========================================================

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # =========================================================
    # COMPANY
    # =========================================================

    company_id = Column(
        BigInteger,
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    # =========================================================
    # PERSON DETAILS
    # =========================================================

    person_name = Column(
        String(150),
        nullable=False,
    )

    person_mobile = Column(
        String(20),
        nullable=True,
    )

    person_address = Column(
        Text,
        nullable=True,
    )

    notes = Column(
        Text,
        nullable=True,
    )

    # =========================================================
    # LOAN DETAILS
    # =========================================================

    # given  -> company gave money to person
    # taken  -> company took money from person
    direction = Column(
        String(10),
        nullable=False,
    )

    principal_amount = Column(
        Numeric(12, 2),
        nullable=False,
    )

    # Example:
    # 3 = 3%
    interest_rate = Column(
        Numeric(8, 2),
        nullable=False,
        default=0,
    )

    # monthly
    # yearly
    # one_time
    interest_type = Column(
        String(20),
        nullable=False,
        default="monthly",
    )

    # =========================================================
    # DATES
    # =========================================================

    start_date = Column(
        Date,
        nullable=False,
    )

    due_date = Column(
        Date,
        nullable=True,
    )

    # =========================================================
    # STATUS
    # =========================================================

    # active
    # partially_settled
    # closed
    # cancelled
    status = Column(
        String(30),
        nullable=False,
        default="active",
        index=True,
    )

    # =========================================================
    # AUDIT
    # =========================================================

    created_by = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime,nullable=False,default=datetime.utcnow,)
    updated_at = Column(DateTime,nullable=False,default=datetime.utcnow,onupdate=datetime.utcnow,)

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    company = relationship("Company",)
    created_by_user = relationship("User",)
    transactions = relationship(
        "LoanTransaction",
        back_populates="loan",
        cascade="all, delete-orphan",
    )
    
    
    
    