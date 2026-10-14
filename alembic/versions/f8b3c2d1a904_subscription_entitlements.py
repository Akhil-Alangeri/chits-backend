"""Configurable plans and company feature overrides; preserve existing access."""
from alembic import op, context
import sqlalchemy as sa

revision = "f8b3c2d1a904"
down_revision = "d7f41a92b603"
branch_labels = None
depends_on = None


def _inspector():
    return None if context.is_offline_mode() else sa.inspect(op.get_bind())


def _create_table(name, *columns):
    inspector = _inspector()
    # Older application startup may have created these tables via create_all.
    if inspector is not None and inspector.has_table(name):
        expected = {column.name for column in columns}
        actual = {column['name'] for column in inspector.get_columns(name)}
        if not expected.issubset(actual):
            raise RuntimeError(f"Existing {name} has an incompatible schema; review before migration.")
        return
    op.create_table(name, *columns)


def upgrade():
    _create_table("subscription_plans",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("billing_cycle", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    _create_table("features", sa.Column("key", sa.String(80), primary_key=True),
                    sa.Column("name", sa.String(150), nullable=False))
    _create_table("plan_features",
        sa.Column("plan_id", sa.BigInteger(), sa.ForeignKey("subscription_plans.id"), primary_key=True),
        sa.Column("feature_key", sa.String(80), sa.ForeignKey("features.key"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False))
    _create_table("company_feature_overrides",
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("companies.id"), primary_key=True),
        sa.Column("feature_key", sa.String(80), sa.ForeignKey("features.key"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False))
    inspector = _inspector()
    if inspector is None or 'subscription_plan_id' not in {c['name'] for c in inspector.get_columns('companies')}:
        op.add_column("companies", sa.Column("subscription_plan_id", sa.BigInteger(), nullable=True))
    inspector = _inspector()
    if inspector is None or not any(fk['constrained_columns'] == ['subscription_plan_id'] for fk in inspector.get_foreign_keys('companies')):
        op.create_foreign_key("fk_company_subscription_plan", "companies", "subscription_plans", ["subscription_plan_id"], ["id"])
    if inspector is None or 'ix_companies_subscription_plan_id' not in {i['name'] for i in inspector.get_indexes('companies')}:
        op.create_index("ix_companies_subscription_plan_id", "companies", ["subscription_plan_id"])

    bind = None if context.is_offline_mode() else op.get_bind()
    feature_table = sa.table("features", sa.column("key", sa.String()), sa.column("name", sa.String()))
    for key, name in [('loans', 'Loans'), ('expenses', 'Expenses')]:
        if bind is None or bind.execute(sa.select(feature_table.c.key).where(feature_table.c.key == key)).first() is None:
            op.bulk_insert(feature_table, [{"key": key, "name": name}])
    plan_table = sa.table("subscription_plans", sa.column("id", sa.BigInteger()), sa.column("name", sa.String()),
        sa.column("code", sa.String()), sa.column("description", sa.Text()), sa.column("price", sa.Numeric()),
        sa.column("billing_cycle", sa.String()), sa.column("is_active", sa.Boolean()))
    legacy_id = None if bind is None else bind.execute(sa.select(plan_table.c.id).where(plan_table.c.code == 'legacy_access')).scalar()
    if legacy_id is None:
        legacy_id = 1 if bind is None else (bind.execute(sa.select(sa.func.max(plan_table.c.id))).scalar() or 0) + 1
        op.bulk_insert(plan_table, [{"id": legacy_id, "name": "Existing company access", "code": "legacy_access",
            "description": "Migration-only plan preserving existing Loan and Expenses access. Price is unconfigured (0); review before billing.",
            "price": 0, "billing_cycle": "yearly", "is_active": False}])
    mapping = sa.table("plan_features", sa.column("plan_id", sa.BigInteger()), sa.column("feature_key", sa.String()), sa.column("enabled", sa.Boolean()))
    for key in ('loans', 'expenses'):
        if bind is None or bind.execute(sa.select(mapping.c.plan_id).where(mapping.c.plan_id == legacy_id, mapping.c.feature_key == key)).first() is None:
            op.bulk_insert(mapping, [{"plan_id": legacy_id, "feature_key": key, "enabled": True}])
    op.execute(sa.text("UPDATE companies SET subscription_plan_id = :plan_id WHERE subscription_plan_id IS NULL").bindparams(plan_id=legacy_id))



def downgrade():
    op.drop_index("ix_companies_subscription_plan_id", table_name="companies")
    op.drop_constraint("fk_company_subscription_plan", "companies", type_="foreignkey")
    op.drop_column("companies", "subscription_plan_id")
    op.drop_table("company_feature_overrides")
    op.drop_table("plan_features")
    op.drop_table("features")
    op.drop_table("subscription_plans")
