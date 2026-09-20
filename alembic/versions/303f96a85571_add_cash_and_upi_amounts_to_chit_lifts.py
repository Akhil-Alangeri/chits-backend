"""add cash and upi amounts to chit lifts

Revision ID: 303f96a85571
Revises: aadf820ce94a
Create Date: 2026-09-06 16:18:02.096715

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "303f96a85571"
down_revision: Union[str, Sequence[str], None] = "aadf820ce94a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add UPI and cash payment amounts to chit lifts."""

    op.add_column(
        "chit_lifts",
        sa.Column(
            "upi_amount",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "chit_lifts",
        sa.Column(
            "cash_amount",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    """Remove UPI and cash payment amounts from chit lifts."""

    op.drop_column(
        "chit_lifts",
        "cash_amount",
    )

    op.drop_column(
        "chit_lifts",
        "upi_amount",
    )