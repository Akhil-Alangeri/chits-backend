"""Add membership welcome outbox, without seeding historical notifications."""
from alembic import op
import sqlalchemy as sa

revision = "e9a42b701105"
down_revision = "c8e30f4a0103"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "membership_welcome_outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("membership_id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("notification_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime()),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("claimed_at", sa.DateTime()),
        sa.Column("sent_at", sa.DateTime()),
        sa.Column("last_error", sa.String(80)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("membership_id", "notification_type", name="uq_membership_welcome_type"),
    )
    op.create_index("ix_welcome_due", "membership_welcome_outbox", ["status", "available_at"])


def downgrade():
    # Retain notification history to prevent duplicate sends after a rollback/redeploy.
    raise RuntimeError("Outbox history must be retained; roll back application code only.")
