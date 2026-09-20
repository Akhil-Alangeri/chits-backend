from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    String,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ChitMember(Base):

    __tablename__ = "chit_members"

    __table_args__ = (
        UniqueConstraint(
            "chit_id",
            "member_number",
            name="uq_chit_member_number",
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
    # CHIT
    # =====================================================

    chit_id = Column(
        BigInteger,
        ForeignKey("chit_groups.id"),
        nullable=False,
        index=True,
    )

    # =====================================================
    # COMPANY CUSTOMER PROFILE
    # =====================================================

    customer_profile_id = Column(
        BigInteger,
        ForeignKey("customer_profiles.id"),
        nullable=False,
        index=True,
    )

    # =====================================================
    # MEMBER / SLOT INFORMATION
    # =====================================================

    member_number = Column(
        Integer,
        nullable=False,
    )

    # Name displayed for this particular chit slot.
    member_name = Column(
        String(150),
        nullable=False,
    )

    # =====================================================
    # MEMBERSHIP STATUS
    # =====================================================

    status = Column(
        String(20),
        nullable=False,
        default="confirmed",
    )

    # confirmed
    # active
    # cancelled
    # removed
    # completed

    # =====================================================
    # DATES
    # =====================================================

    joined_at = Column(
        DateTime,
        server_default=func.now(),
    )

    confirmed_at = Column(
        DateTime,
        nullable=True,
    )

    cancelled_at = Column(
        DateTime,
        nullable=True,
    )

    # =====================================================
    # CANCELLATION
    # =====================================================

    cancel_reason = Column(
        Text,
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
    slot_number = Column(
        Integer,
        nullable=False,
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    chit = relationship(
        "ChitGroup",
        back_populates="members",
    )

    customer_profile = relationship(
        "CustomerProfile",
        back_populates="chit_members",
    )
    
    #===========================
    # CHIT MEMBER RELATIONSHIP
    
    #====================
    
    installments = relationship(
        "ChitInstallment",
        back_populates="chit_member",
        cascade="all, delete-orphan",
    )
    
    lifts = relationship(
        "ChitLift",
        back_populates="member",
    )