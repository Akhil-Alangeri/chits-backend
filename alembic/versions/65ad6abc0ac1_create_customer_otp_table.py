"""create customer otp table

Revision ID: 65ad6abc0ac1
Revises: 5677c916e407
Create Date: 2026-09-20 17:33:31.234182

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# =====================================================
# REVISION IDENTIFIERS
# =====================================================

revision: str = "65ad6abc0ac1"

down_revision: Union[str, Sequence[str], None] = "5677c916e407"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


# =====================================================
# UPGRADE
# =====================================================

def upgrade() -> None:
    """
    Create customer_otps table.
    """

    op.create_table(
        "customer_otps",

        # -------------------------------------------------
        # PRIMARY KEY
        # -------------------------------------------------

        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
        ),

        # -------------------------------------------------
        # CUSTOMER PROFILE
        # -------------------------------------------------

        sa.Column(
            "customer_profile_id",
            mysql.BIGINT(),
            nullable=False,
        ),

        # -------------------------------------------------
        # MOBILE NUMBER
        # -------------------------------------------------

        sa.Column(
            "mobile",
            mysql.VARCHAR(length=20),
            nullable=False,
        ),

        # -------------------------------------------------
        # HASHED OTP
        # -------------------------------------------------

        sa.Column(
            "otp_hash",
            mysql.VARCHAR(length=255),
            nullable=False,
        ),

        # -------------------------------------------------
        # OTP EXPIRY
        # -------------------------------------------------

        sa.Column(
            "expires_at",
            mysql.DATETIME(),
            nullable=False,
        ),

        # -------------------------------------------------
        # OTP STATUS
        # -------------------------------------------------

        sa.Column(
            "is_used",
            mysql.BOOLEAN(),
            nullable=False,
            server_default=sa.text("0"),
        ),

        # -------------------------------------------------
        # FAILED ATTEMPTS
        # -------------------------------------------------

        sa.Column(
            "attempts",
            mysql.INTEGER(),
            nullable=False,
            server_default=sa.text("0"),
        ),

        # -------------------------------------------------
        # CREATED TIME
        # -------------------------------------------------

        sa.Column(
            "created_at",
            mysql.DATETIME(),
            nullable=False,
            server_default=sa.text("(now())"),
        ),

        # -------------------------------------------------
        # USED TIME
        # -------------------------------------------------

        sa.Column(
            "used_at",
            mysql.DATETIME(),
            nullable=True,
        ),

        # -------------------------------------------------
        # PRIMARY KEY
        # -------------------------------------------------

        sa.PrimaryKeyConstraint(
            "id",
        ),

        # -------------------------------------------------
        # FOREIGN KEY
        # -------------------------------------------------

        sa.ForeignKeyConstraint(
            ["customer_profile_id"],
            ["customer_profiles.id"],
        ),

        # -------------------------------------------------
        # MYSQL SETTINGS
        # -------------------------------------------------

        mysql_collate="utf8mb4_0900_ai_ci",

        mysql_default_charset="utf8mb4",

        mysql_engine="InnoDB",
    )

    # =====================================================
    # INDEXES
    # =====================================================

    op.create_index(
        "ix_customer_otps_customer_profile_id",
        "customer_otps",
        ["customer_profile_id"],
        unique=False,
    )

    op.create_index(
        "ix_customer_otps_mobile",
        "customer_otps",
        ["mobile"],
        unique=False,
    )

    op.create_index(
        "ix_customer_otps_expires_at",
        "customer_otps",
        ["expires_at"],
        unique=False,
    )


# =====================================================
# DOWNGRADE
# =====================================================

def downgrade() -> None:
    """
    Drop customer_otps table.
    """

    op.drop_index(
        "ix_customer_otps_expires_at",
        table_name="customer_otps",
    )

    op.drop_index(
        "ix_customer_otps_mobile",
        table_name="customer_otps",
    )

    op.drop_index(
        "ix_customer_otps_customer_profile_id",
        table_name="customer_otps",
    )

    op.drop_table(
        "customer_otps",
    )