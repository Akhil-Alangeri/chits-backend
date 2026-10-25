"""Review the new revision against isolated SQLite; never open configured MySQL."""
import importlib.util
import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.engine import make_url


@compiles(sa.BigInteger, "sqlite")
def _sqlite_bigint(element, compiler, **kw):
    return "INTEGER"


REVISION_PATH = Path(__file__).resolve().parents[1] / "alembic/versions/g1d52b701107_subscription_foundation.py"
SPEC = importlib.util.spec_from_file_location("subscription_foundation_revision", REVISION_PATH)
revision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(revision)


class SubscriptionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = sa.create_engine("sqlite://")
        self.connection = self.engine.connect()
        self.metadata = sa.MetaData()
        self.plans = sa.Table("subscription_plans", self.metadata,
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("code", sa.String(80), unique=True, nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("price", sa.Numeric(12, 2), nullable=False),
            sa.Column("billing_cycle", sa.String(20), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False))
        self.features = sa.Table("features", self.metadata,
            sa.Column("key", sa.String(80), primary_key=True),
            sa.Column("name", sa.String(150), nullable=False))
        self.mappings = sa.Table("plan_features", self.metadata,
            sa.Column("plan_id", sa.BigInteger(), sa.ForeignKey("subscription_plans.id"), primary_key=True),
            sa.Column("feature_key", sa.String(80), sa.ForeignKey("features.key"), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False))
        self.companies = sa.Table("companies", self.metadata,
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("company_name", sa.String(150), nullable=False),
            sa.Column("subscription_plan_id", sa.BigInteger(), sa.ForeignKey("subscription_plans.id")))
        sa.Table("users", self.metadata, sa.Column("id", sa.BigInteger(), primary_key=True))
        self.metadata.create_all(self.connection)
        self.connection.execute(self.plans.insert().values(id=70, name="Legacy custom", code="legacy_access",
            price=0, billing_cycle="yearly", is_active=False))
        self.connection.execute(self.features.insert().values(key="loans", name="Existing Loans label"))
        self.connection.execute(self.mappings.insert().values(plan_id=70, feature_key="loans", enabled=True))
        self.connection.execute(self.companies.insert(), [
            {"id": 12, "company_name": "Legacy assigned", "subscription_plan_id": 70},
            {"id": 13, "company_name": "Unassigned", "subscription_plan_id": None}])
        self.operations = Operations(MigrationContext.configure(self.connection))

    def tearDown(self):
        self.connection.close()
        self.engine.dispose()

    def upgrade(self):
        with patch.object(revision, "op", self.operations), patch.object(
                revision, "context", SimpleNamespace(is_offline_mode=lambda: False)):
            revision.upgrade()

    def test_revision_chain(self):
        self.assertEqual(revision.down_revision, "f0c42b701106")

    def test_upgrade_is_repeatable_insert_only_and_preserves_companies(self):
        self.upgrade()
        self.upgrade()
        catalog = sa.Table("subscription_plans", sa.MetaData(), autoload_with=self.connection)
        rows = {row["code"]: row for row in self.connection.execute(sa.select(catalog)).mappings()}
        self.assertEqual(len(rows), 4)
        for code, price, groups, staff in (("starter", 9999, 3, 0), ("growth", 14999, 7, 3), ("business", 19999, 12, 5)):
            with self.subTest(code=code):
                row = rows[code]
                self.assertEqual(row["price"], price)
                self.assertEqual((row["active_group_limit"], row["admin_account_limit"],
                                  row["staff_account_limit"], row["duration_months"]), (groups, 1, staff, 12))
                features = dict(self.connection.execute(sa.select(self.mappings.c.feature_key,
                    self.mappings.c.enabled).where(self.mappings.c.plan_id == row["id"])).all())
                self.assertEqual(features, revision._feature_matrix(code))
        self.assertIsNone(rows["legacy_access"]["active_group_limit"])
        self.assertEqual(rows["legacy_access"]["name"], "Legacy custom")
        self.assertEqual(self.connection.execute(sa.select(self.features.c.name).where(
            self.features.c.key == "loans")).scalar(), "Existing Loans label")
        # Administrative deactivation is not a conflicting commercial contract.
        self.connection.execute(catalog.update().where(catalog.c.code == "growth").values(is_active=False))
        self.upgrade()
        self.assertFalse(self.connection.execute(sa.select(catalog.c.is_active).where(catalog.c.code == "growth")).scalar())
        companies = sa.Table("companies", sa.MetaData(), autoload_with=self.connection)
        data = self.connection.execute(sa.select(companies).order_by(companies.c.id)).mappings().all()
        self.assertEqual([row["subscription_plan_id"] for row in data], [70, None])
        for row in data:
            for key in ("subscription_started_at", "subscription_ends_at", "subscription_status",
                        "pending_subscription_plan_id", "pending_subscription_effective_at"):
                self.assertIsNone(row[key])
        self.assertEqual(self.connection.execute(sa.select(sa.func.count()).select_from(self.mappings)
            .where(self.mappings.c.plan_id == 70)).scalar(), 1)

    def test_conflicting_reserved_code_fails_before_any_schema_change(self):
        self.connection.execute(self.plans.insert().values(name="Custom Starter", code="starter",
            price=12, billing_cycle="monthly", is_active=True))
        with self.assertRaisesRegex(RuntimeError, "Commercial catalog conflicts require review"):
            self.upgrade()
        self.assertNotIn("active_group_limit", {column["name"] for column in sa.inspect(self.connection)
                                                .get_columns("subscription_plans")})
        self.assertFalse(sa.inspect(self.connection).has_table("company_addons"))
        self.assertEqual(self.connection.execute(sa.select(self.plans.c.price)
            .where(self.plans.c.code == "starter")).scalar(), 12)

    def test_conflicting_existing_feature_is_never_overwritten(self):
        self.upgrade()
        catalog = sa.Table("subscription_plans", sa.MetaData(), autoload_with=self.connection)
        plan_id = self.connection.execute(sa.select(catalog.c.id).where(catalog.c.code == "growth")).scalar()
        self.connection.execute(self.mappings.update().where(self.mappings.c.plan_id == plan_id,
            self.mappings.c.feature_key == "loans").values(enabled=False))
        with self.assertRaisesRegex(RuntimeError, "growth.features.loans"):
            self.upgrade()
        self.assertFalse(self.connection.execute(sa.select(self.mappings.c.enabled).where(
            self.mappings.c.plan_id == plan_id, self.mappings.c.feature_key == "loans")).scalar())

    def test_offline_upgrade_stops_before_ddl(self):
        with patch.object(revision, "context", SimpleNamespace(is_offline_mode=lambda: True)), \
                patch.object(revision, "op") as operations:
            with self.assertRaisesRegex(RuntimeError, "offline SQL is unsupported"):
                revision.upgrade()
            operations.get_bind.assert_not_called()

    def test_new_models_compile_for_mysql(self):
        # Compilation is a schema check, not evidence of a live MySQL migration.
        import app.models
        from app.core.database import Base
        for name in ("subscription_plans", "companies", "company_addons", "company_subscription_events"):
            sql = str(sa.schema.CreateTable(Base.metadata.tables[name]).compile(dialect=mysql.dialect()))
            self.assertIn(f"CREATE TABLE {name}", sql)

    def test_downgrade_refuses_to_erase_subscription_history(self):
        self.upgrade()
        events = sa.Table("company_subscription_events", sa.MetaData(), autoload_with=self.connection)
        self.connection.execute(events.insert().values(company_id=12, event_type="reviewed_assignment", after_state={}))
        with patch.object(revision, "op", self.operations):
            with self.assertRaisesRegex(RuntimeError, "history/add-ons exist"):
                revision.downgrade()
        self.assertTrue(sa.inspect(self.connection).has_table("company_subscription_events"))

    def test_platform_catalog_history_does_not_invent_a_company(self):
        self.upgrade()
        events = sa.Table("company_subscription_events", sa.MetaData(), autoload_with=self.connection)
        self.connection.execute(events.insert().values(company_id=None, event_type="plan_create",
                                                       after_state={"code": "review_fixture"}))
        row = self.connection.execute(sa.select(events).where(events.c.event_type == "plan_create")).mappings().one()
        self.assertIsNone(row["company_id"])
        self.assertEqual(row["after_state"], {"code": "review_fixture"})


class MySQLSubscriptionMigrationTests(SubscriptionMigrationTests):
    """The same migration assertions on a unique explicitly opted-in local schema.

    Set NEXNIDHI_TEST_MYSQL_URL to localhost mysql+pymysql with a nexnidhi_test_*
    database placeholder, plus NEXNIDHI_TEST_MYSQL_ALLOW_CREATE=1. Never uses
    .env/DB_* configuration and never migrates an existing schema.
    """

    @classmethod
    def setUpClass(cls):
        raw_url = os.environ.get("NEXNIDHI_TEST_MYSQL_URL")
        if not raw_url or os.environ.get("NEXNIDHI_TEST_MYSQL_ALLOW_CREATE") != "1":
            raise unittest.SkipTest("Real MySQL migration validation requires explicit local disposable-database opt-in")
        cls.test_url = make_url(raw_url)
        if (cls.test_url.drivername != "mysql+pymysql"
                or cls.test_url.host not in ("localhost", "127.0.0.1", "::1")
                or not re.fullmatch(r"nexnidhi_test_[a-zA-Z0-9_]+", cls.test_url.database or "")
                or any(key != "charset" for key in cls.test_url.query)):
            raise RuntimeError("Migration tests require localhost mysql+pymysql, nexnidhi_test_* database, and no socket/query overrides")
        cls.admin_engine = sa.create_engine(cls.test_url._replace(database=None), pool_pre_ping=True)

    @classmethod
    def tearDownClass(cls):
        cls.admin_engine.dispose()

    def setUp(self):
        # Copy only the prior-schema fixture definition and data, never current
        # application metadata: this exercises the actual ALTER migration.
        fixture = SubscriptionMigrationTests()
        fixture.setUp()
        try:
            self.schema_name = "nexnidhi_test_" + uuid.uuid4().hex
            with self.admin_engine.begin() as admin:
                admin.execute(sa.text(f"CREATE DATABASE `{self.schema_name}` CHARACTER SET utf8mb4"))
            self.addCleanup(self._drop_own_database)
            self.engine = sa.create_engine(self.test_url.set(database=self.schema_name))
            self.addCleanup(self.engine.dispose)
            self.connection = self.engine.connect()
            self.addCleanup(self.connection.close)
            self.metadata = fixture.metadata
            self.metadata.create_all(self.connection)
            for table in self.metadata.sorted_tables:
                rows = fixture.connection.execute(sa.select(table)).mappings().all()
                if rows:
                    self.connection.execute(table.insert(), [dict(row) for row in rows])
            self.connection.commit()
            for attribute in ("plans", "features", "mappings", "companies"):
                setattr(self, attribute, getattr(fixture, attribute))
            self.operations = Operations(MigrationContext.configure(self.connection))
        finally:
            fixture.tearDown()

    def tearDown(self):
        # addCleanup closes the connection and engine before dropping only the
        # randomly named database created by this individual test.
        pass

    def _drop_own_database(self):
        with self.admin_engine.begin() as admin:
            admin.execute(sa.text(f"DROP DATABASE `{self.schema_name}`"))


if __name__ == "__main__":
    unittest.main()
