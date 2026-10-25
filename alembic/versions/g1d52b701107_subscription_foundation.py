"""Subscription capacity, lifecycle history and insert-only commercial catalog.

Requires an online connection to a reviewed database: catalog conflicts are
checked before MySQL's implicitly committed DDL. No company is assigned a plan
or given an invented subscription term. Existing catalog rows are never updated.
"""
from decimal import Decimal

from alembic import context, op
import sqlalchemy as sa

revision = "g1d52b701107"
down_revision = "f0c42b701106"
branch_labels = None
depends_on = None

FEATURES = {
    "loans": "Loans",
    "expenses": "Expenses",
    "reports": "Reports",
    "staff_permissions": "Staff management",
    "support_tickets": "Support tickets",
    "audit_export": "Audit export",
    "whatsapp_automation": "WhatsApp automation (paid add-on)",
}
CATALOG = (
    {"code": "starter", "name": "Starter", "price": Decimal("9999.00"),
     "active_group_limit": 3, "admin_account_limit": 1, "staff_account_limit": 0},
    {"code": "growth", "name": "Growth", "price": Decimal("14999.00"),
     "active_group_limit": 7, "admin_account_limit": 1, "staff_account_limit": 3},
    {"code": "business", "name": "Business", "price": Decimal("19999.00"),
     "active_group_limit": 12, "admin_account_limit": 1, "staff_account_limit": 5},
)


def _feature_matrix(code):
    return {key: (
        code == "business" if key == "audit_export" else
        False if key == "whatsapp_automation" else code != "starter"
    ) for key in FEATURES}


def _plan_values(plan):
    return {**plan, "billing_cycle": "yearly", "is_active": True, "duration_months": 12}


def _preflight_catalog(bind):
    """Fail before DDL when reserved commercial codes already mean something else."""
    metadata = sa.MetaData()
    plans = sa.Table("subscription_plans", metadata, autoload_with=bind)
    mappings = sa.Table("plan_features", metadata, autoload_with=bind)
    conflicts = []
    for specification in CATALOG:
        row = bind.execute(sa.select(plans).where(plans.c.code == specification["code"])).mappings().first()
        if row is None:
            continue
        expected = _plan_values(specification)
        for key in ("price", "billing_cycle", "active_group_limit",
                    "admin_account_limit", "staff_account_limit", "duration_months"):
            if row.get(key) != expected[key]:
                conflicts.append(f"{specification['code']}.{key}")
        configured = dict(bind.execute(sa.select(mappings.c.feature_key, mappings.c.enabled)
                                      .where(mappings.c.plan_id == row["id"])).all())
        for key, enabled in _feature_matrix(specification["code"]).items():
            if key in configured and bool(configured[key]) != enabled:
                conflicts.append(f"{specification['code']}.features.{key}")
    if conflicts:
        raise RuntimeError("Commercial catalog conflicts require review; no rows were overwritten: "
                           + ", ".join(conflicts))


def _seed_catalog(bind):
    """Insert missing records only; safe to repeat against the same catalog."""
    _preflight_catalog(bind)
    metadata = sa.MetaData()
    features = sa.Table("features", metadata, autoload_with=bind)
    plans = sa.Table("subscription_plans", metadata, autoload_with=bind)
    mappings = sa.Table("plan_features", metadata, autoload_with=bind)
    for key, name in FEATURES.items():
        if bind.execute(sa.select(features.c.key).where(features.c.key == key)).first() is None:
            bind.execute(features.insert().values(key=key, name=name))
    for specification in CATALOG:
        plan_id = bind.execute(sa.select(plans.c.id).where(plans.c.code == specification["code"])).scalar()
        if plan_id is None:
            inserted = bind.execute(plans.insert().values(**_plan_values(specification)))
            plan_id = inserted.inserted_primary_key[0]
        for key, enabled in _feature_matrix(specification["code"]).items():
            exists = bind.execute(sa.select(mappings.c.plan_id).where(
                mappings.c.plan_id == plan_id, mappings.c.feature_key == key)).first()
            if exists is None:
                bind.execute(mappings.insert().values(plan_id=plan_id, feature_key=key, enabled=enabled))


def _add_columns(bind, table, columns):
    existing = {column["name"] for column in sa.inspect(bind).get_columns(table)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def _create_table(bind, name, *columns):
    inspector = sa.inspect(bind)
    if inspector.has_table(name):
        expected = {column.name for column in columns}
        if not expected.issubset({column["name"] for column in inspector.get_columns(name)}):
            raise RuntimeError(f"Existing {name} has an incompatible schema; review before migration.")
        return
    op.create_table(name, *columns)


def upgrade():
    if context.is_offline_mode():
        raise RuntimeError("Subscription foundation requires online catalog preflight against a reviewed database; offline SQL is unsupported.")
    bind = op.get_bind()
    _preflight_catalog(bind)
    _add_columns(bind, "subscription_plans", [
        sa.Column("active_group_limit", sa.Integer(), nullable=True),
        sa.Column("admin_account_limit", sa.Integer(), nullable=True),
        sa.Column("staff_account_limit", sa.Integer(), nullable=True),
        sa.Column("duration_months", sa.Integer(), nullable=True),
    ])
    _add_columns(bind, "companies", [
        sa.Column("subscription_started_at", sa.DateTime(), nullable=True),
        sa.Column("subscription_ends_at", sa.DateTime(), nullable=True),
        sa.Column("subscription_status", sa.String(30), nullable=True),
        sa.Column("pending_subscription_plan_id", sa.BigInteger(), nullable=True),
        sa.Column("pending_subscription_effective_at", sa.DateTime(), nullable=True),
    ])
    if not any(fk["constrained_columns"] == ["pending_subscription_plan_id"]
               for fk in sa.inspect(bind).get_foreign_keys("companies")):
        with op.batch_alter_table("companies") as batch:
            batch.create_foreign_key("fk_company_pending_subscription_plan", "subscription_plans",
                                     ["pending_subscription_plan_id"], ["id"])
    _create_table(bind, "company_subscription_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # NULL is reserved for platform plan catalog create/update events.
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("approved_reference", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    _create_table(bind, "company_addons",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("addon_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("approved_payment_reference", sa.String(255), nullable=False),
        sa.Column("approved_by_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
    for table in ("company_subscription_events", "company_addons"):
        index = f"ix_{table}_company_id"
        if index not in {row["name"] for row in sa.inspect(bind).get_indexes(table)}:
            op.create_index(index, table, ["company_id"])
    _seed_catalog(bind)


def downgrade():
    bind = op.get_bind()
    # A rollback must never silently erase approved purchases or lifecycle history.
    for table in ("company_subscription_events", "company_addons"):
        if bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() is not None:
            raise RuntimeError("Subscription history/add-ons exist; review and preserve them before downgrade.")
    op.drop_table("company_addons")
    op.drop_table("company_subscription_events")
    with op.batch_alter_table("companies") as batch:
        batch.drop_constraint("fk_company_pending_subscription_plan", type_="foreignkey")
        for name in ("pending_subscription_effective_at", "pending_subscription_plan_id", "subscription_status",
                     "subscription_ends_at", "subscription_started_at"):
            batch.drop_column(name)
    for name in ("duration_months", "staff_account_limit", "admin_account_limit", "active_group_limit"):
        op.drop_column("subscription_plans", name)
    # Catalog and feature rows deliberately remain; companies may reference them.
