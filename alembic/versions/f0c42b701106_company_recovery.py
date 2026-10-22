"""Add isolated company recovery and durable rate limits."""
from alembic import op
import sqlalchemy as sa
revision = "f0c42b701106"
down_revision = "e9a42b701105"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("company_password_recovery",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("otp_hash", sa.String(64)), sa.Column("otp_expires", sa.DateTime()),
        sa.Column("sent_at", sa.DateTime()), sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True), sa.Column("token_expires", sa.DateTime()),
        sa.Column("password_fingerprint", sa.String(64)))
    op.create_table("company_recovery_rate", sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.DateTime(), nullable=False), sa.Column("count", sa.Integer(), nullable=False))

def downgrade():
    op.drop_table("company_password_recovery")
    op.drop_table("company_recovery_rate")
