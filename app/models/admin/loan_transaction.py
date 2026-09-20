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


class LoanTransaction(Base):
    __tablename__ = "loan_transactions"

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
    # LOAN
    # =========================================================

    loan_id = Column(
        BigInteger,
        ForeignKey("loans.id"),
        nullable=False,
        index=True,
    )

    # =========================================================
    # TRANSACTION
    # =========================================================

    transaction_date = Column(
        Date,
        nullable=False,
    )

    transaction_type = Column(
        String(30),
        nullable=False,
        index=True,
    )

    # =========================================================
    # PRINCIPAL
    # =========================================================

    principal_amount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    # =========================================================
    # INTEREST
    # =========================================================

    # Backend-calculated gross interest amount.
    #
    # For:
    #   disbursement          -> 0
    #   principal_repayment   -> 0
    #   interest_payment     -> payment_amount + discount
    #
    interest_amount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    # Discount given against interest.
    discount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    # =========================================================
    # PAYMENT SPLIT
    # =========================================================

    # Actual UPI amount received/paid.
    upi_amount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    # Actual cash amount received/paid.
    cash_amount = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    # =========================================================
    # OPTIONAL DETAILS
    # =========================================================

    reference = Column(
        String(150),
        nullable=True,
    )

    notes = Column(
        Text,
        nullable=True,
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

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    company = relationship(
        "Company",
    )

    loan = relationship(
        "Loan",
        back_populates="transactions",
    )