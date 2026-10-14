"""create audit logs

Revision ID: 9b2a09344687
Revises: c88bd27613d1
Create Date: 2026-09-29 19:33:11.026932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = "9b2a09344687"
down_revision: Union[str, Sequence[str], None] = "c88bd27613d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create audit_logs table."""

    op.create_table(
        "audit_logs",

        # =====================================================
        # PRIMARY KEY
        # =====================================================

        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
        ),

        # =====================================================
        # COMPANY
        # =====================================================

        sa.Column(
            "company_id",
            mysql.BIGINT(),
            autoincrement=False,
            nullable=False,
        ),

        # =====================================================
        # USER
        # =====================================================

        sa.Column(
            "user_id",
            mysql.BIGINT(),
            autoincrement=False,
            nullable=True,
        ),

        # =====================================================
        # ACTION
        # =====================================================

        sa.Column(
            "action",
            mysql.VARCHAR(length=30),
            nullable=False,
        ),

        # =====================================================
        # MODULE
        # =====================================================

        sa.Column(
            "module",
            mysql.VARCHAR(length=50),
            nullable=False,
        ),

        # =====================================================
        # ENTITY
        # =====================================================

        sa.Column(
            "entity_type",
            mysql.VARCHAR(length=100),
            nullable=True,
        ),

        sa.Column(
            "entity_id",
            mysql.BIGINT(),
            autoincrement=False,
            nullable=True,
        ),

        # =====================================================
        # DESCRIPTION
        # =====================================================

        sa.Column(
            "description",
            mysql.TEXT(),
            nullable=False,
        ),

        # =====================================================
        # BEFORE / AFTER VALUES
        # =====================================================

        sa.Column(
            "old_values",
            mysql.JSON(),
            nullable=True,
        ),

        sa.Column(
            "new_values",
            mysql.JSON(),
            nullable=True,
        ),

        # =====================================================
        # REQUEST INFORMATION
        # =====================================================

        sa.Column(
            "ip_address",
            mysql.VARCHAR(length=45),
            nullable=True,
        ),

        sa.Column(
            "user_agent",
            mysql.TEXT(),
            nullable=True,
        ),

        # =====================================================
        # CREATED TIME
        # =====================================================

        sa.Column(
            "created_at",
            mysql.DATETIME(),
            nullable=False,
        ),

        # =====================================================
        # PRIMARY KEY
        # =====================================================

        sa.PrimaryKeyConstraint(
            "id",
        ),

        # =====================================================
        # FOREIGN KEYS
        # =====================================================

        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_audit_logs_company",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_audit_logs_user",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),

        # =====================================================
        # MYSQL TABLE SETTINGS
        # =====================================================

        mysql_engine="InnoDB",
        mysql_default_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )

    # =========================================================
    # SINGLE-COLUMN INDEXES
    # =========================================================

    op.create_index(
        op.f("ix_audit_logs_id"),
        "audit_logs",
        ["id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_audit_logs_company_id"),
        "audit_logs",
        ["company_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_audit_logs_user_id"),
        "audit_logs",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_audit_logs_action"),
        "audit_logs",
        ["action"],
        unique=False,
    )

    op.create_index(
        op.f("ix_audit_logs_module"),
        "audit_logs",
        ["module"],
        unique=False,
    )

    op.create_index(
        op.f("ix_audit_logs_entity_type"),
        "audit_logs",
        ["entity_type"],
        unique=False,
    )

    op.create_index(
        op.f("ix_audit_logs_entity_id"),
        "audit_logs",
        ["entity_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_audit_logs_created_at"),
        "audit_logs",
        ["created_at"],
        unique=False,
    )

    # =========================================================
    # COMPOSITE INDEXES
    # =========================================================

    op.create_index(
        op.f("ix_audit_company_user"),
        "audit_logs",
        ["company_id", "user_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_audit_company_module"),
        "audit_logs",
        ["company_id", "module"],
        unique=False,
    )

    op.create_index(
        op.f("ix_audit_company_created"),
        "audit_logs",
        ["company_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop audit_logs table."""

    op.drop_index(
        op.f("ix_audit_company_created"),
        table_name="audit_logs",
    )

    op.drop_index(
        op.f("ix_audit_company_module"),
        table_name="audit_logs",
    )

    op.drop_index(
        op.f("ix_audit_company_user"),
        table_name="audit_logs",
    )

    op.drop_index(
        op.f("ix_audit_logs_created_at"),
        table_name="audit_logs",
    )

    op.drop_index(
        op.f("ix_audit_logs_entity_id"),
        table_name="audit_logs",
    )

    op.drop_index(
        op.f("ix_audit_logs_entity_type"),
        table_name="audit_logs",
    )

    op.drop_index(
        op.f("ix_audit_logs_module"),
        table_name="audit_logs",
    )

    op.drop_index(
        op.f("ix_audit_logs_action"),
        table_name="audit_logs",
    )

    op.drop_index(
        op.f("ix_audit_logs_user_id"),
        table_name="audit_logs",
    )

    op.drop_index(
        op.f("ix_audit_logs_company_id"),
        table_name="audit_logs",
    )

    op.drop_index(
        op.f("ix_audit_logs_id"),
        table_name="audit_logs",
    )

    op.drop_table("audit_logs")
