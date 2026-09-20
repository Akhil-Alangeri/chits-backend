
"""add discount to loan transactions

Revision ID: 10b47ffbc7fa
Revises: 42cdc27a6f0a
Create Date: 2026-09-07

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "10b47ffbc7fa"

down_revision: Union[str, Sequence[str], None] = "42cdc27a6f0a"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add discount column to loan_transactions."""

    op.add_column(
        "loan_transactions",
        sa.Column(
            "discount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    """Remove discount column from loan_transactions."""

    op.drop_column(
        "loan_transactions",
        "discount",
    )

