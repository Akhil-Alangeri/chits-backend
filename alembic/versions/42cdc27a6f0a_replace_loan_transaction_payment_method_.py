"""replace loan transaction payment method with upi cash

Revision ID: 42cdc27a6f0a
Revises: 70717a9cc101
Create Date: 2026-09-07 16:49:25.194172

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "42cdc27a6f0a"

down_revision: Union[str, Sequence[str], None] = "70717a9cc101"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # ADD UPI AMOUNT
    # ---------------------------------------------------------
    op.add_column(
        "loan_transactions",
        sa.Column(
            "upi_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )

    # ---------------------------------------------------------
    # ADD CASH AMOUNT
    # ---------------------------------------------------------
    op.add_column(
        "loan_transactions",
        sa.Column(
            "cash_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )

    # ---------------------------------------------------------
    # REMOVE OLD PAYMENT METHOD
    # ---------------------------------------------------------
    op.drop_column(
        "loan_transactions",
        "payment_method",
    )


def downgrade() -> None:
    # ---------------------------------------------------------
    # RESTORE PAYMENT METHOD
    # ---------------------------------------------------------
    op.add_column(
        "loan_transactions",
        sa.Column(
            "payment_method",
            sa.String(20),
            nullable=True,
        ),
    )

    # ---------------------------------------------------------
    # REMOVE UPI / CASH
    # ---------------------------------------------------------
    op.drop_column(
        "loan_transactions",
        "upi_amount",
    )

    op.drop_column(
        "loan_transactions",
        "cash_amount",
    )