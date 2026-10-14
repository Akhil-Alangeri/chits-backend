from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    String,
    Text,
    DateTime,
    JSON,
    Index,
)

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(
        BigInteger,
        primary_key=True,
        index=True,
    )

    # =====================================================
    # COMPANY
    # =====================================================

    company_id = Column(
        BigInteger,
        ForeignKey(
            "companies.id",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # =====================================================
    # USER WHO PERFORMED THE ACTION
    # =====================================================

    user_id = Column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    # =====================================================
    # ACTION
    # =====================================================

    action = Column(
        String(30),
        nullable=False,
        index=True,
    )

    # Examples:
    # CREATE
    # UPDATE
    # DELETE
    # LOGIN
    # LOGOUT
    # STATUS_CHANGE
    # PAYMENT_CREATE
    # PAYMENT_UPDATE
    # etc.

    # =====================================================
    # MODULE
    # =====================================================

    module = Column(
        String(50),
        nullable=False,
        index=True,
    )

    # Examples:
    # Customers
    # Chit Groups
    # Chit Members
    # Payments
    # Chit Lifts
    # Expenses
    # Loans
    # Company Profile

    # =====================================================
    # ENTITY
    # =====================================================

    entity_type = Column(
        String(100),
        nullable=True,
        index=True,
    )

    entity_id = Column(
        BigInteger,
        nullable=True,
        index=True,
    )

    # =====================================================
    # HUMAN READABLE DESCRIPTION
    # =====================================================

    description = Column(
        Text,
        nullable=False,
    )

    # =====================================================
    # BEFORE / AFTER DATA
    # =====================================================

    old_values = Column(
        JSON,
        nullable=True,
    )

    new_values = Column(
        JSON,
        nullable=True,
    )

    # =====================================================
    # REQUEST INFORMATION
    # =====================================================

    ip_address = Column(
        String(45),
        nullable=True,
    )

    user_agent = Column(
        Text,
        nullable=True,
    )

    # =====================================================
    # CREATED TIME
    # =====================================================

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )


# =========================================================
# COMPOSITE INDEXES
# =========================================================

Index(
    "ix_audit_company_created",
    AuditLog.company_id,
    AuditLog.created_at,
)

Index(
    "ix_audit_company_module",
    AuditLog.company_id,
    AuditLog.module,
)

Index(
    "ix_audit_company_user",
    AuditLog.company_id,
    AuditLog.user_id,
)
