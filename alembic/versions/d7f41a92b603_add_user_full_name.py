"""Add optional full name without changing existing credentials or roles."""
from alembic import op
import sqlalchemy as sa

revision = "d7f41a92b603"
down_revision = "9b2a09344687"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("full_name", sa.String(150), nullable=True))


def downgrade():
    op.drop_column("users", "full_name")
