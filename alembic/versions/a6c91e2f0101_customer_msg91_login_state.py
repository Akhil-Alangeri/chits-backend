"""Persistent MSG91 customer resend and verification metadata (no OTP)."""
from alembic import op
import sqlalchemy as sa

revision = "a6c91e2f0101"
down_revision = "f8b3c2d1a904"
branch_labels = None
depends_on = None


def upgrade():
    if not sa.inspect(op.get_bind()).has_table("customer_msg91_login_state"):
        op.create_table("customer_msg91_login_state",
            sa.Column("mobile", sa.String(10), primary_key=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("next_send_at", sa.DateTime(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False))


def downgrade():
    op.drop_table("customer_msg91_login_state")
