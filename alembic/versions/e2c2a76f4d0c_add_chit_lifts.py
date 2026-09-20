"""add chit lifts

Revision ID: e2c2a76f4d0c
Revises: f8a1b2c3d4e5
Create Date: 2026-09-03 13:34:48.202637

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2c2a76f4d0c"
down_revision: Union[str, Sequence[str], None] = "f8a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "chit_lifts",
        sa.Column(
            "customer_name",
            sa.String(length=150),
            nullable=False,
        ),
    )

    op.add_column(
        "chit_lifts",
        sa.Column(
            "member_number",
            sa.String(length=50),
            nullable=False,
        ),
    )

    op.add_column(
        "chit_lifts",
        sa.Column(
            "slot_number",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "chit_lifts",
        sa.Column(
            "edit_reason",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column(
        "chit_lifts",
        "edit_reason",
    )

    op.drop_column(
        "chit_lifts",
        "slot_number",
    )

    op.drop_column(
        "chit_lifts",
        "member_number",
    )

    op.drop_column(
        "chit_lifts",
        "customer_name",
    )