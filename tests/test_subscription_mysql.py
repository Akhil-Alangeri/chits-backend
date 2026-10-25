"""Opt-in real MySQL request races in a uniquely created local database.

Set NEXNIDHI_TEST_MYSQL_URL to a localhost mysql+pymysql URL whose database
starts nexnidhi_test_, and NEXNIDHI_TEST_MYSQL_ALLOW_CREATE=1. This never uses
DB_* variables, .env database settings, or existing database tables. Only the
unique database created by this suite is removed. Without opt-in these tests skip.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import re
import threading
import unittest
import uuid
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker

import app.models
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.admin.chit_group import ChitGroup
from app.models.admin.company import Company
from app.models.admin.subscription import Feature, PlanFeature, SubscriptionPlan, CompanyFeatureOverride, CompanySubscriptionEvent
from app.models.admin.user import User
from app.routes.chit_group import router as groups_router
from app.routes.company_users import router as users_router
from app.routes.subscription import router as subscription_router
from app.routes.super_admin_auth import require_super_admin
from app.services.subscription_lifecycle import apply_transition


class MySQLSubscriptionConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw_url = os.environ.get("NEXNIDHI_TEST_MYSQL_URL")
        if not raw_url or os.environ.get("NEXNIDHI_TEST_MYSQL_ALLOW_CREATE") != "1":
            raise unittest.SkipTest("Real MySQL concurrency requires explicit local disposable-database opt-in")
        test_url = make_url(raw_url)
        if (test_url.drivername != "mysql+pymysql" or test_url.host not in ("localhost", "127.0.0.1", "::1")
                or not re.fullmatch(r"nexnidhi_test_[a-zA-Z0-9_]+", test_url.database or "")
                or any(key != "charset" for key in test_url.query)):
            raise RuntimeError("MySQL tests require localhost mysql+pymysql, nexnidhi_test_* database, and no socket/query overrides")
        cls.schema_name = "nexnidhi_test_" + uuid.uuid4().hex
        server_url = URL.create(test_url.drivername, username=test_url.username,
            password=test_url.password, host=test_url.host, port=test_url.port,
            query=dict(test_url.query))
        cls.admin_engine = create_engine(server_url, pool_pre_ping=True)
        cls.created = False
        try:
            with cls.admin_engine.begin() as connection:
                connection.execute(text(f"CREATE DATABASE `{cls.schema_name}` CHARACTER SET utf8mb4"))
            cls.created = True
            cls.engine = create_engine(test_url.set(database=cls.schema_name),
                isolation_level="REPEATABLE READ", pool_size=5, max_overflow=2,
                connect_args={"init_command": "SET SESSION innodb_lock_wait_timeout=10"})
            Base.metadata.create_all(cls.engine)
            cls.Session = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        except Exception:
            cls._cleanup_database()
            raise

    @classmethod
    def _cleanup_database(cls):
        if hasattr(cls, "engine"):
            cls.engine.dispose()
        if cls.created:
            # The name is generated here and is never sourced from DB_* or a user schema.
            with cls.admin_engine.begin() as connection:
                connection.execute(text(f"DROP DATABASE `{cls.schema_name}`"))
            cls.created = False
        cls.admin_engine.dispose()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_database()

    def setUp(self):
        # Separate tenants avoid deleting any rows between tests.
        self.company_id = int(uuid.uuid4().int % 1_000_000_000) + 100
        self.admin_id = self.company_id
        self.headers = {"Authorization": "Bearer " + create_access_token({"sub": str(self.admin_id)})}
        with self.Session() as db:
            plan = SubscriptionPlan(name="Concurrency fixture", code=f"race_{self.company_id}",
                price=14999, billing_cycle="yearly", active_group_limit=3,
                staff_account_limit=3, admin_account_limit=1, duration_months=12)
            db.add(plan)
            if db.get(Feature, "staff_permissions") is None:
                db.add(Feature(key="staff_permissions", name="Staff permissions"))
            db.flush()
            db.add(PlanFeature(plan_id=plan.id, feature_key="staff_permissions", enabled=True))
            db.add(Company(id=self.company_id, company_name="Local concurrency fixture", status="active",
                subscription_plan_id=plan.id, subscription_status="active",
                subscription_started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
                subscription_ends_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=364)))
            db.flush()
            db.add(User(id=self.admin_id, company_id=self.company_id, role="company_admin", status="active",
                login_id=f"admin_{self.company_id}", password_hash="fixture: no password login"))
            db.commit()

    def concurrent_requests(self, requests, *, warm_snapshot=True):
        barrier = threading.Barrier(len(requests))
        observed_connections = set()
        guard = threading.Lock()
        def isolated_request_db():
            with self.Session() as db:
                if warm_snapshot:
                    # Establish an old consistent-read snapshot before either
                    # request can take the company lock (MySQL REPEATABLE READ).
                    db.execute(select(func.count()).select_from(ChitGroup)
                               .where(ChitGroup.company_id == self.company_id)).scalar_one()
                    db.execute(select(func.count()).select_from(User)
                               .where(User.company_id == self.company_id)).scalar_one()
                connection_id = db.execute(text("SELECT CONNECTION_ID()")).scalar_one()
                with guard:
                    observed_connections.add(connection_id)
                barrier.wait(timeout=15)
                try:
                    yield db
                finally:
                    db.rollback()
        app = FastAPI()
        app.include_router(groups_router)
        app.include_router(users_router)
        app.include_router(subscription_router)
        app.dependency_overrides[require_super_admin] = lambda: None
        app.dependency_overrides[get_db] = isolated_request_db
        def request(args):
            method, path, body = args
            with TestClient(app) as client:
                return client.request(method, path, headers=self.headers, json=body)
        with ThreadPoolExecutor(max_workers=len(requests)) as workers:
            futures = [workers.submit(request, item) for item in requests]
            responses = [future.result(timeout=35) for future in futures]
        self.assertEqual(len(observed_connections), len(requests), "Race must use separate real MySQL connections")
        return responses

    def test_simultaneous_group_entries_cannot_bypass_limit_with_stale_snapshot(self):
        with self.Session() as db:
            groups = [ChitGroup(company_id=self.company_id, name=f"Race group {index}", code=f"RACE-{index}",
                chit_value=10000, monthly_emi=1000, duration_months=10, max_members=10,
                status="upcoming" if index < 2 else "draft") for index in range(4)]
            db.add_all(groups)
            db.commit()
            group_ids = [group.id for group in groups[2:]]
        responses = self.concurrent_requests([
            ("PUT", f"/chits/{group_id}", {"status": "upcoming"}) for group_id in group_ids])
        self.assertEqual(sorted(response.status_code for response in responses), [200, 403],
                         [response.text for response in responses])
        denied = next(response for response in responses if response.status_code == 403)
        self.assertEqual(denied.json()["detail"]["code"], "PLAN_LIMIT_REACHED")
        with self.Session() as db:
            self.assertEqual(db.query(ChitGroup).filter(ChitGroup.company_id == self.company_id,
                ChitGroup.status.in_(["active", "upcoming", "paused"])).count(), 3)

    def test_simultaneous_staff_creation_cannot_bypass_limit_with_stale_snapshot(self):
        with self.Session() as db:
            db.add_all([User(company_id=self.company_id, role="company_user", status="active",
                login_id=f"initial_{self.company_id}_{index}", password_hash="fixture") for index in range(2)])
            db.commit()
        responses = self.concurrent_requests([("POST", "/company/users", {
            "full_name": "Race Staff", "login_id": f"race_staff_{self.company_id}_{index}",
            "password": "Password123"}) for index in range(2)])
        self.assertEqual(sorted(response.status_code for response in responses), [201, 403],
                         [response.text for response in responses])
        denied = next(response for response in responses if response.status_code == 403)
        self.assertEqual(denied.json()["detail"]["code"], "PLAN_LIMIT_REACHED")
        with self.Session() as db:
            self.assertEqual(db.query(User).filter_by(company_id=self.company_id,
                role="company_user", status="active").count(), 3)

    def test_simultaneous_staff_reactivation_cannot_bypass_limit(self):
        with self.Session() as db:
            users = [User(company_id=self.company_id, role="company_user",
                status="active" if index < 2 else "inactive",
                login_id=f"reactivate_{self.company_id}_{index}", password_hash="fixture") for index in range(4)]
            db.add_all(users)
            db.commit()
            user_ids = [user.id for user in users[2:]]
        responses = self.concurrent_requests([("PATCH", f"/company/users/{user_id}/status",
                                               {"status": "active"}) for user_id in user_ids])
        self.assertEqual(sorted(response.status_code for response in responses), [200, 403],
                         [response.text for response in responses])
        with self.Session() as db:
            self.assertEqual(db.query(User).filter_by(company_id=self.company_id,
                role="company_user", status="active").count(), 3)

    def test_different_tenant_first_overrides_retry_real_gap_lock_deadlock(self):
        other_company_id = self.company_id + 1
        with self.Session() as db:
            original = db.get(Company, self.company_id)
            plan_id = original.subscription_plan_id
            db.add(Company(id=other_company_id, company_name="Second isolated tenant", status="active",
                subscription_plan_id=plan_id, subscription_status="active",
                subscription_started_at=original.subscription_started_at,
                subscription_ends_at=original.subscription_ends_at))
            db.commit()
        reached = threading.Barrier(2)
        attempts = {}
        guard = threading.Lock()
        def synchronize_first_attempt(db, company, *args):
            result = apply_transition(db, company, *args)
            with guard:
                attempts[company.id] = attempts.get(company.id, 0) + 1
                first = attempts[company.id] == 1
            if first:
                reached.wait(timeout=15)
            return result
        with patch("app.routes.subscription.apply_transition", side_effect=synchronize_first_attempt):
            responses = self.concurrent_requests([("PUT", f"/super-admin/companies/{company_id}/subscription",
                {"plan_id": plan_id, "overrides": {"staff_permissions": False}})
                for company_id in (self.company_id, other_company_id)])
        self.assertEqual([response.status_code for response in responses], [200, 200],
                         [response.text for response in responses])
        self.assertGreater(sum(attempts.values()), 2, "Test must produce a real retry after a cross-tenant gap-lock deadlock")
        with self.Session() as db:
            for company_id in (self.company_id, other_company_id):
                self.assertEqual(db.query(CompanyFeatureOverride).filter_by(company_id=company_id,
                    feature_key="staff_permissions", enabled=False).count(), 1)
                self.assertEqual(db.query(CompanySubscriptionEvent).filter_by(company_id=company_id).count(), 1)
