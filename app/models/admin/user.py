from sqlalchemy import (
    BigInteger,
    Integer,
    Column,
    ForeignKey,
    String,
    DateTime,
    func,
)

from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):

    __tablename__ = "users"

    full_name = Column(String(150), nullable=True)

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    company_id = Column(
        BigInteger,
        ForeignKey("companies.id"),
        nullable=True
    )

    login_id = Column(
        String(50),
        unique=True,
        nullable=False
    )

    password_hash = Column(
        String(255),
        nullable=False
    )

    role = Column(
        String(30),
        nullable=False
    )

    status = Column(
        String(20),
        nullable=False,
        default="active"
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    last_login_at = Column(
        DateTime,
        nullable=True
    )

    session_version = Column(Integer, nullable=False, default=0, server_default="0")
    failed_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    locked_until = Column(DateTime, nullable=True)
    reset_hash = Column(String(64), nullable=True)
    reset_expires = Column(DateTime, nullable=True)
    reset_sent_at = Column(DateTime, nullable=True)
    reset_attempts = Column(Integer, nullable=False, default=0, server_default="0")

    # Company relationship

    company = relationship(
        "Company",
        back_populates="users"
    )
    customer_profiles = relationship(
        "CustomerProfile",
        back_populates="user",
    )
    
    # =====================================================
    # PAYMENT TRANSACTIONS
    # =====================================================

    payment_transactions = relationship(
        "PaymentTransaction",
        back_populates="created_by_user",
    )
