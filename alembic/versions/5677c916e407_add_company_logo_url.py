"""add company logo url

Revision ID: 5677c916e407
Revises: 350d05fd1983
Create Date: 2026-09-13 08:37:29.383883
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5677c916e407"
down_revision: Union[str, Sequence[str], None] = "350d05fd1983"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "logo_url",
            sa.String(length=500),
            nullable=True
        )
    )


def downgrade() -> None:
    op.drop_column(
        "companies",
        "logo_url"
    )