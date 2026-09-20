from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class CustomerProfile(Base):

    __tablename__ = "customer_profiles"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "customer_code",
            name="uq_customer_profile_company_code",
        ),
    )

    # =====================================================
    # PRIMARY KEY
    # =====================================================

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # =====================================================
    # OPTIONAL GLOBAL CUSTOMER LOGIN
    #
    # NULL when company creates the customer but the
    # customer has not activated portal login yet.
    # =====================================================

    user_id = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    # =====================================================
    # COMPANY
    # =====================================================

    company_id = Column(
        BigInteger,
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    # =====================================================
    # BUSINESS CUSTOMER IDENTIFIER
    # =====================================================

    customer_code = Column(
        String(30),
        nullable=False,
    )

    # =====================================================
    # CUSTOMER INFORMATION
    # =====================================================

    display_name = Column(
        String(150),
        nullable=False,
    )

    legal_name = Column(
        String(150),
        nullable=True,
    )

    mobile = Column(
        String(20),
        nullable=False,
    )

    email = Column(
        String(150),
        nullable=True,
    )

    address = Column(
        Text,
        nullable=True,
    )

    # =====================================================
    # STATUS
    # =====================================================

    status = Column(
        String(20),
        nullable=False,
        default="active",
    )

    # =====================================================
    # TIMESTAMPS
    # =====================================================

    created_at = Column(
        DateTime,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    company = relationship(
        "Company",
        back_populates="customer_profiles",
    )

    user = relationship(
        "User",
        back_populates="customer_profiles",
    )

    chit_members = relationship(
        "ChitMember",
        back_populates="customer_profile",
    )