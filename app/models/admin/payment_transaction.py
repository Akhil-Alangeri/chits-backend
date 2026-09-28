from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)

from sqlalchemy.orm import relationship

from app.core.database import Base


class PaymentTransaction(Base):

    __tablename__ = "payment_transactions"


    # =====================================================
    # ID
    # =====================================================

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )


    # =====================================================
    # INSTALLMENT
    # =====================================================

    installment_id = Column(
        BigInteger,
        ForeignKey(
            "chit_installments.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )


    # =====================================================
    # AMOUNT
    # =====================================================

    amount = Column(
        Numeric(12, 2),
        nullable=False,
    )


    # =====================================================
    # PAYMENT DATE
    # =====================================================

    payment_date = Column(
        Date,
        nullable=False,
    )


    # =====================================================
    # PAYMENT METHOD
    # =====================================================

    payment_method = Column(
        String(30),
        nullable=False,
    )


    # =====================================================
    # REFERENCE NUMBER
    # =====================================================

    reference_number = Column(
        String(100),
        nullable=True,
    )


    # =====================================================
    # NOTES
    # =====================================================

    notes = Column(
        Text,
        nullable=True,
    )


    # =====================================================
    # CREATED BY
    # =====================================================

    created_by = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )


    # =====================================================
    # TIMESTAMPS
    # =====================================================

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    installment = relationship(
        "ChitInstallment",
        back_populates="payments",
    )

    created_by_user = relationship(
        "User",
        back_populates="payment_transactions",
    )