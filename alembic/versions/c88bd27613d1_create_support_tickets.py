"""create support tickets

Revision ID: c88bd27613d1
Revises: 65ad6abc0ac1
Create Date: 2026-09-26 15:55:31.567096

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# =====================================================
# REVISION IDENTIFIERS
# =====================================================

revision: str = "c88bd27613d1"

down_revision: Union[str, Sequence[str], None] = "65ad6abc0ac1"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


# =====================================================
# UPGRADE
# =====================================================

def upgrade() -> None:

    # =================================================
    # SUPPORT TICKETS
    # =================================================

    op.create_table(
        "support_tickets",

        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "ticket_number",
            sa.String(length=30),
            nullable=False,
        ),

        # ---------------------------------------------
        # COMPANY
        # ---------------------------------------------

        sa.Column(
            "company_id",
            sa.BigInteger(),
            nullable=False,
        ),

        # ---------------------------------------------
        # CUSTOMER
        # ---------------------------------------------

        sa.Column(
            "customer_profile_id",
            sa.BigInteger(),
            nullable=False,
        ),

        # ---------------------------------------------
        # TICKET DETAILS
        # ---------------------------------------------

        sa.Column(
            "subject",
            sa.String(length=200),
            nullable=False,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "category",
            sa.String(length=50),
            nullable=False,
            server_default="other",
        ),

        sa.Column(
            "priority",
            sa.String(length=20),
            nullable=False,
            server_default="medium",
        ),

        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="open",
        ),

        # ---------------------------------------------
        # ASSIGNMENT
        # ---------------------------------------------

        sa.Column(
            "assigned_to_user_id",
            sa.BigInteger(),
            nullable=True,
        ),

        # ---------------------------------------------
        # TIMESTAMPS
        # ---------------------------------------------

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.Column(
            "resolved_at",
            sa.DateTime(),
            nullable=True,
        ),

        sa.Column(
            "closed_at",
            sa.DateTime(),
            nullable=True,
        ),

        # ---------------------------------------------
        # FOREIGN KEYS
        # ---------------------------------------------

        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["customer_profile_id"],
            ["customer_profiles.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["assigned_to_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),

        # ---------------------------------------------
        # PRIMARY KEY
        # ---------------------------------------------

        sa.PrimaryKeyConstraint("id"),

        # ---------------------------------------------
        # UNIQUE
        # ---------------------------------------------

        sa.UniqueConstraint(
            "ticket_number",
            name="uq_support_tickets_ticket_number",
        ),
    )

    # =================================================
    # SUPPORT TICKET INDEXES
    # =================================================

    op.create_index(
        "ix_support_tickets_ticket_number",
        "support_tickets",
        ["ticket_number"],
        unique=True,
    )

    op.create_index(
        "ix_support_tickets_company_id",
        "support_tickets",
        ["company_id"],
        unique=False,
    )

    op.create_index(
        "ix_support_tickets_customer_profile_id",
        "support_tickets",
        ["customer_profile_id"],
        unique=False,
    )

    op.create_index(
        "ix_support_tickets_assigned_to_user_id",
        "support_tickets",
        ["assigned_to_user_id"],
        unique=False,
    )

    op.create_index(
        "ix_support_tickets_category",
        "support_tickets",
        ["category"],
        unique=False,
    )

    op.create_index(
        "ix_support_tickets_priority",
        "support_tickets",
        ["priority"],
        unique=False,
    )

    op.create_index(
        "ix_support_tickets_status",
        "support_tickets",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_support_tickets_company_status",
        "support_tickets",
        ["company_id", "status"],
        unique=False,
    )

    op.create_index(
        "ix_support_tickets_company_customer",
        "support_tickets",
        ["company_id", "customer_profile_id"],
        unique=False,
    )

    # =================================================
    # TICKET MESSAGES
    # =================================================

    op.create_table(
        "ticket_messages",

        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),

        # ---------------------------------------------
        # TICKET
        # ---------------------------------------------

        sa.Column(
            "ticket_id",
            sa.BigInteger(),
            nullable=False,
        ),

        # ---------------------------------------------
        # SENDER
        # ---------------------------------------------

        sa.Column(
            "sender_type",
            sa.String(length=20),
            nullable=False,
        ),

        sa.Column(
            "sender_user_id",
            sa.BigInteger(),
            nullable=True,
        ),

        sa.Column(
            "sender_customer_profile_id",
            sa.BigInteger(),
            nullable=True,
        ),

        # ---------------------------------------------
        # MESSAGE
        # ---------------------------------------------

        sa.Column(
            "message",
            sa.Text(),
            nullable=False,
        ),

        # ---------------------------------------------
        # TIMESTAMPS
        # ---------------------------------------------

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),

        # ---------------------------------------------
        # FOREIGN KEYS
        # ---------------------------------------------

        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["support_tickets.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["sender_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["sender_customer_profile_id"],
            ["customer_profiles.id"],
            ondelete="SET NULL",
        ),

        # ---------------------------------------------
        # PRIMARY KEY
        # ---------------------------------------------

        sa.PrimaryKeyConstraint("id"),
    )

    # =================================================
    # TICKET MESSAGE INDEXES
    # =================================================

    op.create_index(
        "ix_ticket_messages_ticket_id",
        "ticket_messages",
        ["ticket_id"],
        unique=False,
    )

    op.create_index(
        "ix_ticket_messages_sender_type",
        "ticket_messages",
        ["sender_type"],
        unique=False,
    )

    op.create_index(
        "ix_ticket_messages_sender_user_id",
        "ticket_messages",
        ["sender_user_id"],
        unique=False,
    )

    op.create_index(
        "ix_ticket_messages_sender_customer_profile_id",
        "ticket_messages",
        ["sender_customer_profile_id"],
        unique=False,
    )

    op.create_index(
        "ix_ticket_messages_ticket_created",
        "ticket_messages",
        ["ticket_id", "created_at"],
        unique=False,
    )


# =====================================================
# DOWNGRADE
# =====================================================

def downgrade() -> None:

    # Drop ticket message indexes
    op.drop_index(
        "ix_ticket_messages_ticket_created",
        table_name="ticket_messages",
    )

    op.drop_index(
        "ix_ticket_messages_sender_customer_profile_id",
        table_name="ticket_messages",
    )

    op.drop_index(
        "ix_ticket_messages_sender_user_id",
        table_name="ticket_messages",
    )

    op.drop_index(
        "ix_ticket_messages_sender_type",
        table_name="ticket_messages",
    )

    op.drop_index(
        "ix_ticket_messages_ticket_id",
        table_name="ticket_messages",
    )

    # Drop ticket messages
    op.drop_table("ticket_messages")

    # Drop support ticket indexes
    op.drop_index(
        "ix_support_tickets_company_customer",
        table_name="support_tickets",
    )

    op.drop_index(
        "ix_support_tickets_company_status",
        table_name="support_tickets",
    )

    op.drop_index(
        "ix_support_tickets_status",
        table_name="support_tickets",
    )

    op.drop_index(
        "ix_support_tickets_priority",
        table_name="support_tickets",
    )

    op.drop_index(
        "ix_support_tickets_category",
        table_name="support_tickets",
    )

    op.drop_index(
        "ix_support_tickets_assigned_to_user_id",
        table_name="support_tickets",
    )

    op.drop_index(
        "ix_support_tickets_customer_profile_id",
        table_name="support_tickets",
    )

    op.drop_index(
        "ix_support_tickets_company_id",
        table_name="support_tickets",
    )

    op.drop_index(
        "ix_support_tickets_ticket_number",
        table_name="support_tickets",
    )

    # Drop support tickets
    op.drop_table("support_tickets")