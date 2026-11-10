"""Allow expenses and other costs to be assigned to a chit.

Existing expenses remain company expenses until explicitly assigned.
"""
from alembic import op
import sqlalchemy as sa

revision = "h2e63c811110"
down_revision = "g1d52b701107"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("expenses", sa.Column("chit_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_expenses_chit_id", "expenses", ["chit_id"])
    op.create_foreign_key(
        "fk_expenses_chit_id", "expenses", "chit_groups", ["chit_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_expenses_chit_id", "expenses", type_="foreignkey")
    op.drop_index("ix_expenses_chit_id", table_name="expenses")
    op.drop_column("expenses", "chit_id")
