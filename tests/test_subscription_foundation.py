"""Subscription behavior through isolated API routes; never connects to configured MySQL."""
from datetime import date, datetime, timedelta, timezone
import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import BigInteger

import app.models
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.admin.audit_log import AuditLog
from app.models.admin.chit_group import ChitGroup
from app.models.admin.company import Company
from app.models.admin.subscription import (
    CompanyFeatureOverride, Feature, PlanFeature, SubscriptionPlan,
)
from app.models.admin.user import User
from app.routes.chit_group import router as groups_router
from app.routes.company_users import router as users_router
from app.routes.subscription import company_router
from app.services.entitlement_service import (
    ensure_admin_capacity, get_company_entitlements, has_company_feature,
    subscription_state,
)


@compiles(BigInteger, "sqlite")
def sqlite_bigint(element, compiler, **kw):
    return "INTEGER"


PLAN_LIMITS = {"starter": (3, 0), "growth": (7, 3), "business": (12, 5)}
FEATURES = ("loans", "expenses", "reports", "staff_permissions", "support_tickets",
            "audit_export", "audit_history", "whatsapp_automation")


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def seed_foundation(db):
    """Small explicit fixture, independent of production data and migration seeding."""
    db.add_all([Feature(key=key, name=key) for key in FEATURES])
    for index, (code, (groups, staff)) in enumerate(PLAN_LIMITS.items(), 1):
        db.add(SubscriptionPlan(id=index, name=code.title(), code=code,
            price=(9999, 14999, 19999)[index - 1], billing_cycle="yearly",
            active_group_limit=groups, admin_account_limit=1,
            staff_account_limit=staff, duration_months=12))
    db.flush()
    for index, code in enumerate(PLAN_LIMITS, 1):
        for key in FEATURES:
            enabled = (key == "audit_history" or
                       key == "audit_export" and code == "business" or
                       key in ("loans", "expenses", "reports", "staff_permissions", "support_tickets")
                       and code != "starter")
            db.add(PlanFeature(plan_id=index, feature_key=key, enabled=enabled))
    db.add_all([Company(id=12, company_name="Tenant A", status="active"),
                Company(id=13, company_name="Tenant B", status="active")])
    db.flush()
    db.add_all([User(id=1, company_id=12, login_id="admin_a", role="company_admin",
                    password_hash="fixture: no password login", status="active"),
                User(id=2, company_id=13, login_id="admin_b", role="company_admin",
                    password_hash="fixture: no password login", status="active")])
    db.commit()


def make_app(database_dependency):
    app = FastAPI()
    for router in (groups_router, users_router, company_router):
        app.include_router(router)
    app.dependency_overrides[get_db] = database_dependency
    return app


def group_row(index, *, company_id=12, status="draft"):
    return ChitGroup(id=index, company_id=company_id, code=f"FIXTURE-{index}",
                     name=f"Group {index}", chit_value=10000, monthly_emi=1000,
                     duration_months=10, max_members=10, status=status)


class SubscriptionFoundationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        seed_foundation(self.db)
        self.client = TestClient(make_app(lambda: self.db))
        self.headers = {"Authorization": "Bearer " + create_access_token({"sub": "1"})}
        self.other_headers = {"Authorization": "Bearer " + create_access_token({"sub": "2"})}

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def assign(self, code="growth", *, company_id=12, days_remaining=100):
        company = self.db.get(Company, company_id)
        company.subscription_plan_id = self.db.query(SubscriptionPlan).filter_by(code=code).one().id
        company.subscription_started_at = utcnow() - timedelta(days=265)
        company.subscription_ends_at = utcnow() + timedelta(days=days_remaining)
        company.subscription_status = "active"
        self.db.commit()
        return company

    def add_groups(self, statuses, *, company_id=12, start=1):
        self.db.add_all([group_row(index, company_id=company_id, status=status)
                         for index, status in enumerate(statuses, start)])
        self.db.commit()

    def create_staff(self, login="staff_a"):
        return self.client.post("/company/users", headers=self.headers,
            json={"full_name": "Staff Member", "login_id": login, "password": "Password123"})

    def assert_restriction(self, response, code, resource=None):
        self.assertEqual(response.status_code, 403, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], code)
        self.assertTrue(detail["message"])
        if resource:
            self.assertEqual(detail["resource"], resource)
        return detail

    def test_exact_group_limits_and_company_scoped_usage(self):
        for code, (limit, _) in PLAN_LIMITS.items():
            with self.subTest(plan=code):
                self.db.query(ChitGroup).delete()
                self.assign(code)
                self.add_groups(["upcoming"] * (limit - 1) + ["draft", "draft"])
                # Another tenant's usage must never enter Tenant A's limit.
                self.add_groups(["active"] * 14, company_id=13, start=100)
                response = self.client.put(f"/chits/{limit}", headers=self.headers,
                                           json={"status": "upcoming"})
                self.assertEqual(response.status_code, 200, response.text)
                denied = self.client.put(f"/chits/{limit + 1}", headers=self.headers,
                                         json={"status": "paused"})
                detail = self.assert_restriction(denied, "PLAN_LIMIT_REACHED", "active_groups")
                self.assertEqual((detail["used"], detail["limit"], detail["plan_code"]),
                                 (limit, limit, code))
                self.db.rollback()
                self.assertEqual(self.db.get(ChitGroup, limit + 1).status, "draft")

    def test_status_accounting_and_release_then_reopen(self):
        self.assign("starter")
        self.add_groups(["active", "upcoming", "paused", "completed", "cancelled", "draft"])
        state = get_company_entitlements(self.db, 12)
        self.assertEqual(state["usage"]["active_groups"], 3)
        for group_id in (4, 5, 6):
            denied = self.client.put(f"/chits/{group_id}", headers=self.headers,
                                     json={"status": "upcoming"})
            self.assert_restriction(denied, "PLAN_LIMIT_REACHED")
            self.db.rollback()
        response = self.client.put("/chits/2", headers=self.headers, json={"status": "completed"})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.put("/chits/4", headers=self.headers, json={"status": "upcoming"})
        self.assertEqual(response.status_code, 200, response.text)

    def test_active_activation_preserves_installment_workflow_and_checks_capacity(self):
        from app.models.admin.chit_installment import ChitInstallment
        from app.models.admin.chit_member import ChitMember
        from app.models.admin.chit_months import ChitMonth
        from app.models.admin.customer_profile import CustomerProfile
        self.assign("starter")
        self.add_groups(["upcoming", "paused", "draft", "draft"])
        self.db.add(CustomerProfile(id=1, company_id=12, customer_code="MEMBER-1",
            display_name="Member", mobile="9000000000", status="active"))
        self.db.flush()
        for group_id in (3, 4):
            group = self.db.get(ChitGroup, group_id)
            group.start_date = date(2030, 1, 1)
            group.duration_months = 1
            self.db.add(ChitMonth(company_id=12, chit_id=group_id, month_number=1,
                month_date=date(2030, 1, 1), monthly_emi=1000, monthly_lift_amount=10000))
            self.db.add(ChitMember(chit_id=group_id, customer_profile_id=1, member_number=1,
                member_name="Member", slot_number=1, status="confirmed"))
        self.db.commit()
        response = self.client.put("/chits/3", headers=self.headers, json={"status": "active"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.db.query(ChitInstallment).count(), 1)
        response = self.client.put("/chits/4", headers=self.headers, json={"status": "active"})
        self.assert_restriction(response, "PLAN_LIMIT_REACHED", "active_groups")
        self.db.rollback()
        self.assertEqual(self.db.get(ChitGroup, 4).status, "draft")
        self.assertEqual(self.db.query(ChitInstallment).count(), 1)

    def test_exact_term_and_fifteen_day_grace_boundaries(self):
        company = self.assign("growth")
        plan = self.db.get(SubscriptionPlan, company.subscription_plan_id)
        end = company.subscription_ends_at
        for moment, expected in ((end - timedelta(microseconds=1), "active"),
                                 (end, "grace"),
                                 (end + timedelta(days=15) - timedelta(microseconds=1), "grace"),
                                 (end + timedelta(days=15), "expired")):
            with self.subTest(moment=moment):
                state = subscription_state(company, plan, now=moment)
                self.assertEqual(state["status"], expected)
                self.assertEqual(state["grace_ends_at"], end + timedelta(days=15))
                self.assertEqual(state["capacity_increases_allowed"], expected != "expired")

    def test_drafts_allowed_at_capacity_and_after_expiry_with_audit(self):
        self.assign("starter", days_remaining=-16)
        self.add_groups(["upcoming"] * 3)
        response = self.client.post("/chits", headers=self.headers, json={
            "name": "New Draft", "chit_value": 1000, "monthly_emi": 1000,
            "duration_months": 1, "max_members": 1, "start_date": "2030-01-01",
            "months": [{"month_number": 1, "month_date": "2030-01-01",
                        "monthly_emi": 1000, "monthly_lift_amount": 1000}]})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["status"], "draft")
        self.assertEqual(get_company_entitlements(self.db, 12)["usage"]["active_groups"], 3)
        self.assertTrue(self.db.query(AuditLog).filter_by(module="Chit Groups", action="CREATE").first())

    def test_over_limit_and_expired_groups_can_be_serviced_and_reduced(self):
        self.assign("starter", days_remaining=-16)
        self.add_groups(["upcoming"] * 4 + ["draft"])
        response = self.client.put("/chits/1", headers=self.headers, json={"name": "Existing Group"})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.put("/chits/1", headers=self.headers, json={"status": "paused"})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.put("/chits/2", headers=self.headers, json={"status": "cancelled"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get("/chits", headers=self.headers).status_code, 200)
        response = self.client.put("/chits/5", headers=self.headers, json={"status": "upcoming"})
        self.assert_restriction(response, "SUBSCRIPTION_EXPIRED")
        self.db.rollback()
        self.assertEqual(self.db.query(ChitGroup).count(), 5)
        self.assertGreater(self.db.query(AuditLog).count(), 0)

    def test_grace_allows_capacity_but_post_grace_blocks_groups_and_staff(self):
        company = self.assign("growth", days_remaining=-14)
        self.add_groups(["draft", "draft"])
        self.assertEqual(get_company_entitlements(self.db, 12)["subscription"]["status"], "grace")
        response = self.client.put("/chits/1", headers=self.headers, json={"status": "upcoming"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.create_staff().status_code, 201)
        company.subscription_ends_at = utcnow() - timedelta(days=16)
        self.db.commit()
        state = get_company_entitlements(self.db, 12)
        self.assertEqual(state["subscription"]["status"], "expired")
        self.assertFalse(state["subscription"]["capacity_increases_allowed"])
        self.assertTrue(state["features"]["loans"])
        response = self.client.put("/chits/2", headers=self.headers, json={"status": "upcoming"})
        self.assert_restriction(response, "SUBSCRIPTION_EXPIRED")
        self.db.rollback()
        self.assert_restriction(self.create_staff("staff_b"), "SUBSCRIPTION_EXPIRED")

    def test_bounded_plan_without_verified_term_cannot_increase_capacity(self):
        company = self.assign("growth")
        company.subscription_started_at = None
        company.subscription_ends_at = None
        self.db.commit()
        self.add_groups(["draft"])
        response = self.client.put("/chits/1", headers=self.headers, json={"status": "upcoming"})
        self.assert_restriction(response, "SUBSCRIPTION_REVIEW_REQUIRED")
        self.db.rollback()
        self.assert_restriction(self.create_staff(), "SUBSCRIPTION_REVIEW_REQUIRED")

    def test_staff_exact_limits_zero_three_five_and_reactivation(self):
        for code, (_, limit) in PLAN_LIMITS.items():
            with self.subTest(plan=code):
                self.db.query(User).filter(User.role == "company_user").delete()
                self.assign(code)
                # A positive override demonstrates that Starter's hard zero seat
                # limit still applies independently of optional feature access.
                override = self.db.get(CompanyFeatureOverride, (12, "staff_permissions"))
                if override is None:
                    self.db.add(CompanyFeatureOverride(company_id=12, feature_key="staff_permissions", enabled=True))
                self.db.commit()
                for index in range(limit):
                    response = self.create_staff(f"{code}_staff_{index}")
                    self.assertEqual(response.status_code, 201, response.text)
                detail = self.assert_restriction(self.create_staff(f"{code}_extra"), "PLAN_LIMIT_REACHED", "staff_accounts")
                self.assertEqual((detail["used"], detail["limit"]), (limit, limit))
                self.db.rollback()
                if not limit:
                    continue
                user = self.db.query(User).filter_by(company_id=12, role="company_user").first()
                response = self.client.patch(f"/company/users/{user.id}/status", headers=self.headers,
                                             json={"status": "inactive"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(self.create_staff(f"{code}_replacement").status_code, 201)
                response = self.client.patch(f"/company/users/{user.id}/status", headers=self.headers,
                                             json={"status": "active"})
                self.assert_restriction(response, "PLAN_LIMIT_REACHED", "staff_accounts")
                self.db.rollback()
                self.assertEqual(self.db.get(User, user.id).status, "inactive")

    def test_existing_staff_can_be_edited_deactivated_deleted_after_expiry(self):
        self.assign("growth")
        response = self.create_staff()
        self.assertEqual(response.status_code, 201, response.text)
        user_id = response.json()["id"]
        self.assign("growth", days_remaining=-16)
        response = self.client.put(f"/company/users/{user_id}", headers=self.headers,
                                  json={"full_name": "Updated Name", "login_id": "updated_staff"})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.patch(f"/company/users/{user_id}/status", headers=self.headers,
                                     json={"status": "active"})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.patch(f"/company/users/{user_id}/status", headers=self.headers,
                                     json={"status": "inactive"})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.delete(f"/company/users/{user_id}", headers=self.headers)
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.db.get(User, user_id).status, "deleted")

    def test_legacy_unassigned_and_custom_unbounded_preserve_capacity(self):
        self.add_groups(["upcoming"] * 15 + ["draft"])
        state = get_company_entitlements(self.db, 12)
        self.assertEqual(state["subscription"]["status"], "legacy")
        self.assertIsNone(state["limits"]["active_groups"])
        self.assertFalse(state["features"]["loans"])
        for feature in ("reports", "staff_permissions", "support_tickets"):
            self.assertTrue(state["features"][feature])
        self.assertEqual(self.client.put("/chits/16", headers=self.headers, json={"status": "upcoming"}).status_code, 200)
        self.assertEqual(self.create_staff().status_code, 201)
        custom = SubscriptionPlan(name="Existing custom", code="existing_custom", price=0, billing_cycle="yearly")
        self.db.add(custom)
        self.db.flush()
        self.db.get(Company, 12).subscription_plan_id = custom.id
        self.db.commit()
        self.assertIsNone(get_company_entitlements(self.db, 12)["limits"]["staff_accounts"])
        self.assertEqual(self.create_staff("legacy_second").status_code, 201)

    def test_entitlement_api_is_authenticated_and_company_scoped(self):
        self.assign("starter")
        self.assign("business", company_id=13)
        self.add_groups(["upcoming", "paused"])
        response = self.client.get("/company/entitlements?company_id=13", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["plan"]["code"], "starter")
        self.assertEqual(body["limits"], {"active_groups": 3, "staff_accounts": 0, "admin_accounts": 1})
        self.assertEqual(body["usage"], {"active_groups": 2, "staff_accounts": 0, "admin_accounts": 1})
        for key in ("plan", "plan_features", "overrides", "features"):
            self.assertIn(key, body)
        self.assertIn(self.client.get("/company/entitlements").status_code, (401, 403))
        self.assertEqual(self.client.put("/chits/1", headers=self.other_headers,
                                        json={"status": "upcoming"}).status_code, 404)
        self.assertEqual(self.client.patch("/company/users/1/status", headers=self.other_headers,
                                          json={"status": "inactive"}).status_code, 404)

    def test_feature_matrix_ordinary_overrides_and_guaranteed_audit(self):
        for code in PLAN_LIMITS:
            self.assign(code)
            state = get_company_entitlements(self.db, 12)
            for key in ("loans", "expenses", "reports", "staff_permissions", "support_tickets"):
                self.assertEqual(state["features"][key], code != "starter", (code, key))
            self.assertEqual(state["features"]["audit_export"], code == "business")
            self.assertTrue(state["features"]["audit_history"])
            self.assertFalse(state["features"]["whatsapp_automation"])
        self.db.add_all([CompanyFeatureOverride(company_id=12, feature_key="loans", enabled=False),
                         CompanyFeatureOverride(company_id=12, feature_key="audit_history", enabled=False)])
        self.db.commit()
        self.assertFalse(has_company_feature(self.db, 12, "loans"))
        self.assertTrue(has_company_feature(self.db, 12, "audit_history"))

    def test_whatsapp_requires_valid_paid_approved_addon_even_with_override(self):
        from app.models.admin.subscription import CompanyAddon
        self.assign("business")
        self.db.add(CompanyFeatureOverride(company_id=12, feature_key="whatsapp_automation", enabled=True))
        self.db.commit()
        self.assertFalse(has_company_feature(self.db, 12, "whatsapp_automation"))
        addon = CompanyAddon(company_id=12, addon_key="whatsapp_automation", status="active",
            starts_at=utcnow() - timedelta(days=1), ends_at=utcnow() + timedelta(days=10),
            approved_payment_reference="TEST-APPROVED-123", approved_by_user_id=1)
        self.db.add(addon)
        self.db.commit()
        self.assertTrue(has_company_feature(self.db, 12, "whatsapp_automation"))
        addon.ends_at = utcnow() - timedelta(seconds=1)
        self.db.commit()
        self.assertFalse(has_company_feature(self.db, 12, "whatsapp_automation"))
        addon.ends_at = utcnow() + timedelta(days=10)
        addon.approved_by_user_id = None
        self.db.commit()
        self.assertFalse(has_company_feature(self.db, 12, "whatsapp_automation"))

    def test_admin_limit_and_protection(self):
        self.assign("starter")
        with self.assertRaises(HTTPException) as raised:
            ensure_admin_capacity(self.db, 12)
        self.assertEqual(raised.exception.detail["code"], "PLAN_LIMIT_REACHED")
        self.assertEqual(raised.exception.detail["resource"], "admin_accounts")
        self.db.rollback()
        response = self.client.patch("/company/users/1/status", headers=self.headers,
                                     json={"status": "inactive"})
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.db.get(User, 1).status, "active")

    def test_staff_feature_does_not_bypass_admin_role(self):
        self.assign("business")
        response = self.create_staff()
        self.assertEqual(response.status_code, 201, response.text)
        staff_headers = {"Authorization": "Bearer " + create_access_token({"sub": str(response.json()["id"])})}
        response = self.client.post("/company/users", headers=staff_headers,
            json={"full_name": "Unauthorized", "login_id": "unauthorized", "password": "Password123"})
        self.assertEqual(response.status_code, 403, response.text)

    def test_unknown_status_rejected_without_changing_group(self):
        self.assign("starter")
        self.add_groups(["draft"])
        for status in ("ACTIVE", "unknown", "", None):
            response = self.client.put("/chits/1", headers=self.headers, json={"status": status})
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.db.get(ChitGroup, 1).status, "draft")
