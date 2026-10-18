"""Super Admin password reset challenge metadata; never store plaintext OTPs."""
from alembic import op
import sqlalchemy as sa

revision = "c8e30f4a0103"
down_revision = "b7d20e3f0102"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("reset_hash", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("reset_expires", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("reset_sent_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("reset_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    for name in ("reset_attempts", "reset_sent_at", "reset_expires", "reset_hash"):
        op.drop_column("users", name)
