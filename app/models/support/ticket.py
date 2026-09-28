from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # =====================================================
    # TICKET IDENTITY
    # =====================================================

    ticket_number = Column(
        String(30),
        nullable=False,
        unique=True,
        index=True,
    )

    # =====================================================
    # COMPANY / CUSTOMER
    # =====================================================

    company_id = Column(
        BigInteger,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    customer_profile_id = Column(
        BigInteger,
        ForeignKey("customer_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # =====================================================
    # TICKET DETAILS
    # =====================================================

    subject = Column(
        String(200),
        nullable=False,
    )

    description = Column(
        Text,
        nullable=False,
    )

    category = Column(
        String(50),
        nullable=False,
        default="other",
        index=True,
    )

    priority = Column(
        String(20),
        nullable=False,
        default="medium",
        index=True,
    )

    status = Column(
        String(30),
        nullable=False,
        default="open",
        index=True,
    )

    # =====================================================
    # ASSIGNMENT
    # =====================================================

    assigned_to_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # =====================================================
    # TIMESTAMPS
    # =====================================================

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

    resolved_at = Column(
        DateTime,
        nullable=True,
    )

    closed_at = Column(
        DateTime,
        nullable=True,
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    company = relationship(
        "Company",
    )

    customer_profile = relationship(
        "CustomerProfile",
    )

    assigned_to = relationship(
        "User",
        foreign_keys=[assigned_to_user_id],
    )

    messages = relationship(
        "TicketMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketMessage.created_at",
    )

    __table_args__ = (
        Index(
            "ix_support_tickets_company_status",
            "company_id",
            "status",
        ),
        Index(
            "ix_support_tickets_company_customer",
            "company_id",
            "customer_profile_id",
        ),
    )


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # =====================================================
    # TICKET
    # =====================================================

    ticket_id = Column(
        BigInteger,
        ForeignKey(
            "support_tickets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # =====================================================
    # SENDER
    # =====================================================

    sender_type = Column(
        String(20),
        nullable=False,
        index=True,
    )

    sender_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    sender_customer_profile_id = Column(
        BigInteger,
        ForeignKey(
            "customer_profiles.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # =====================================================
    # MESSAGE
    # =====================================================

    message = Column(
        Text,
        nullable=False,
    )

    # =====================================================
    # TIMESTAMPS
    # =====================================================

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

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    ticket = relationship(
        "SupportTicket",
        back_populates="messages",
    )

    sender_user = relationship(
        "User",
        foreign_keys=[sender_user_id],
    )

    sender_customer = relationship(
        "CustomerProfile",
        foreign_keys=[sender_customer_profile_id],
    )

    __table_args__ = (
        Index(
            "ix_ticket_messages_ticket_created",
            "ticket_id",
            "created_at",
        ),
    )