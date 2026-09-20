"""add chit month reference to chit lifts

Revision ID: aadf820ce94a
Revises: e2c2a76f4d0c
Create Date: 2026-09-04 12:58:13.996514

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aadf820ce94a"
down_revision: Union[str, Sequence[str], None] = "e2c2a76f4d0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chit_lifts",
        sa.Column("chit_month_id", sa.BigInteger(), nullable=True),
    )

    op.create_index(
        op.f("ix_chit_lifts_chit_month_id"),
        "chit_lifts",
        ["chit_month_id"],
        unique=False,
    )

    op.create_unique_constraint(
        "uq_chit_lift_month",
        "chit_lifts",
        ["chit_month_id"],
    )

    op.create_foreign_key(
        None,
        "chit_lifts",
        "chit_months",
        ["chit_month_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        None,
        "chit_lifts",
        type_="foreignkey",
    )

    op.drop_constraint(
        "uq_chit_lift_month",
        "chit_lifts",
        type_="unique",
    )

    op.drop_index(
        op.f("ix_chit_lifts_chit_month_id"),
        table_name="chit_lifts",
    )

    op.drop_column(
        "chit_lifts",
        "chit_month_id",
    )