"""Add Super Admin authentication using the existing users table."""
from alembic import op
import sqlalchemy as sa
import bcrypt

revision = "b7d20e3f0102"
down_revision = "a6c91e2f0101"
branch_labels = None
depends_on = None


def upgrade():
    users = sa.table("users", sa.column("login_id", sa.String), sa.column("role", sa.String),
                     sa.column("company_id", sa.BigInteger), sa.column("password_hash", sa.String),
                     sa.column("status", sa.String), sa.column("session_version", sa.Integer),
                     sa.column("failed_attempts", sa.Integer))
    existing = op.get_bind().execute(sa.select(users.c.role, users.c.company_id)
                                     .where(users.c.login_id == "admin")).first()
    if existing and (existing.role != "super_admin" or existing.company_id is not None):
        raise RuntimeError("Login ID admin already belongs to another user; it will not be overwritten.")
    op.add_column("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(), nullable=True))
    if not existing:
        op.bulk_insert(users, [{"login_id":"admin", "role":"super_admin", "company_id":None,
            "password_hash":bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode(), "status":"active",
            "session_version":0, "failed_attempts":0}])


def downgrade():
    # Keep user accounts and credentials; only remove authentication metadata.
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_attempts")
    op.drop_column("users", "session_version")
