from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)

from sqlalchemy.orm import relationship

from app.core.database import Base


class ChitInstallment(Base):

    __tablename__ = "chit_installments"


    # =====================================================
    # ID
    # =====================================================

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )


    # =====================================================
    # CHIT MEMBER
    # =====================================================

    chit_member_id = Column(
        BigInteger,
        ForeignKey(
            "chit_members.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )


    # =====================================================
    # INSTALLMENT NUMBER
    # =====================================================

    installment_number = Column(
        BigInteger,
        nullable=False,
    )


    # =====================================================
    # DUE DATE
    # =====================================================

    due_date = Column(
        Date,
        nullable=False,
    )


    # =====================================================
    # DUE AMOUNT
    # =====================================================

    due_amount = Column(
        Numeric(12, 2),
        nullable=False,
    )


    # =====================================================
    # STATUS
    # =====================================================

    status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )


    # =====================================================
    # CREATED / UPDATED
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
    # RELATIONSHIP
    # =====================================================

    chit_member = relationship(
        "ChitMember",
        back_populates="installments",
    )


    payments = relationship(
        "PaymentTransaction",
        back_populates="installment",
        cascade="all, delete-orphan",
    )