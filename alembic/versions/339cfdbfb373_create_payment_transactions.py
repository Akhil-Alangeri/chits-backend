"""create payment transactions

Revision ID: f8a1b2c3d4e5
Revises: 66847ed2df47
Create Date: 2026-08-28 18:30:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f8a1b2c3d4e5"

down_revision: Union[str, Sequence[str], None] = "66847ed2df47"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Payment transactions table already exists
    in the database.

    This migration records the schema change
    in Alembic history.
    """
    pass


def downgrade() -> None:
    """
    Payment transactions table already exists
    and should not be dropped automatically.
    """
    pass