"""Administrative subscription transitions in an isolated SQLite API fixture."""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import unittest

from dateutil.relativedelta import relativedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.admin.audit_log import AuditLog
from app.models.admin.chit_group import ChitGroup
from app.models.admin.company import Company
from app.models.admin.subscription import CompanySubscriptionEvent, SubscriptionPlan
from app.models.admin.user import User
from app.routes.subscription import router
from app.routes.super_admin_auth import require_super_admin
from tests.test_subscription_foundation import group_row, seed_foundation, utcnow


class SubscriptionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        seed_foundation(self.db)
        self.actor = User(id=900, company_id=None, role="super_admin", status="active",
                          login_id="platform_admin", password_hash="fixture", session_version=3)
        self.db.add(self.actor)
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        # Business-rule tests use a real stored actor; authentication is tested
        # independently with this override removed below.
        self.app.dependency_overrides[require_super_admin] = lambda: self.actor
        self.client = TestClient(self.app)
        self.path = "/super-admin/companies/12/subscription"

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def plan_id(self, code):
        return self.db.query(SubscriptionPlan).filter_by(code=code).one().id

    def direct_assignment(self, code="growth", *, remaining=100):
        company = self.db.get(Company, 12)
        company.subscription_plan_id = self.plan_id(code)
        company.subscription_ends_at = utcnow() + timedelta(days=remaining)
        company.subscription_started_at = company.subscription_ends_at - relativedelta(months=12)
        company.subscription_status = "active"
        self.db.commit()
        return company

    def transition(self, code, action, **extra):
        return self.client.put(self.path, json={"plan_id": self.plan_id(code), "action": action,
            "workflow": "administrative", "reason": "Approved by platform administrator", **extra})

    def events(self):
        return self.db.query(CompanySubscriptionEvent).filter_by(company_id=12).order_by(CompanySubscriptionEvent.id).all()

    def assert_no_transition(self, response, before_plan, before_events=0, code=None):
        self.assertGreaterEqual(response.status_code, 400, response.text)
        self.assertLess(response.status_code, 500, response.text)
        if code:
            self.assertEqual(response.json()["detail"]["code"], code)
        self.db.rollback()
        self.assertEqual(self.db.get(Company, 12).subscription_plan_id, before_plan)
        self.assertEqual(len(self.events()), before_events)

    def test_commercial_assignment_requires_explicit_administrative_approval(self):
        response = self.client.put(self.path, json={"plan_id": self.plan_id("starter")})
        self.assert_no_transition(response, None, code="SUBSCRIPTION_APPROVAL_REQUIRED")
        for extra in ({}, {"approved_reference": "UNVERIFIED-PAYMENT-CLAIM"}):
            payload = {"plan_id": self.plan_id("starter"), "action": "assign", **extra}
            response = self.client.put(self.path, json=payload)
            self.assert_no_transition(response, None, code="SUBSCRIPTION_APPROVAL_REQUIRED")
        response = self.client.put(self.path, json={"plan_id": self.plan_id("starter"), "action": "assign",
            "workflow": "administrative", "reason": "   "})
        self.assert_no_transition(response, None)
        response = self.client.put(self.path, json={"plan_id": self.plan_id("starter"), "action": "assign",
            "workflow": "payment", "reason": "Client claims payment succeeded"})
        self.assert_no_transition(response, None)

    def test_approved_assignment_records_actor_term_event_and_financial_audit(self):
        response = self.transition("starter", "assign", starts_at="2030-01-15T00:00:00Z",
                                   approved_reference="ADMIN-REVIEW-123")
        self.assertEqual(response.status_code, 200, response.text)
        company = self.db.get(Company, 12)
        self.assertEqual(company.subscription_started_at, datetime(2030, 1, 15))
        self.assertEqual(company.subscription_ends_at, datetime(2031, 1, 15))
        self.assertEqual(company.subscription_status, "active")
        saved = self.events()[0]
        self.assertEqual((saved.actor_user_id, saved.event_type, saved.approved_reference),
                         (900, "assign", "ADMIN-REVIEW-123"))
        self.assertTrue(saved.reason)
        self.assertIsNone(saved.before_state["plan"])
        self.assertEqual(saved.after_state["plan"]["code"], "starter")
        audit = self.db.query(AuditLog).filter_by(company_id=12, module="subscription").one()
        self.assertEqual(audit.user_id, 900)
        # Other tenants are never assigned by this workflow.
        self.assertIsNone(self.db.get(Company, 13).subscription_plan_id)

    def test_initial_assignment_cannot_reset_existing_paid_term(self):
        company = self.direct_assignment("starter")
        original_end = company.subscription_ends_at
        response = self.transition("business", "assign", starts_at="2030-01-01T00:00:00Z")
        self.assert_no_transition(response, self.plan_id("starter"))
        self.assertEqual(self.db.get(Company, 12).subscription_ends_at, original_end)

    def test_existing_bounded_plan_without_term_requires_reviewed_assignment(self):
        company = self.db.get(Company, 12)
        company.subscription_plan_id = self.plan_id("starter")
        self.db.commit()
        response = self.client.put(self.path, json={"plan_id": self.plan_id("starter"), "action": "assign"})
        self.assert_no_transition(response, self.plan_id("starter"), code="SUBSCRIPTION_APPROVAL_REQUIRED")
        response = self.transition("starter", "assign", starts_at="2030-02-01T00:00:00Z")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(company.subscription_started_at, datetime(2030, 2, 1))
        self.assertEqual(company.subscription_ends_at, datetime(2031, 2, 1))
        self.assertEqual(self.events()[0].event_type, "assign")

    def test_partial_existing_term_cannot_be_reset_through_assignment(self):
        company = self.direct_assignment("starter")
        original_start, original_end = company.subscription_started_at, company.subscription_ends_at
        for start, end in ((original_start, None), (None, original_end)):
            company.subscription_started_at, company.subscription_ends_at = start, end
            self.db.commit()
            response = self.transition("starter", "assign")
            self.assert_no_transition(response, self.plan_id("starter"))
            self.assertEqual((company.subscription_started_at, company.subscription_ends_at), (start, end))

    def test_quote_is_prorated_read_only_and_upgrade_preserves_renewal(self):
        company = self.direct_assignment("starter", remaining=180)
        start, end = company.subscription_started_at, company.subscription_ends_at
        response = self.client.get(self.path + "/upgrade-quote", params={"plan_id": self.plan_id("growth")})
        self.assertEqual(response.status_code, 200, response.text)
        quote = response.json()
        quoted_at = datetime.fromisoformat(quote["quoted_at"])
        expected = (Decimal(5000) * Decimal(str((end - quoted_at).total_seconds())) /
                    Decimal(str((end - start).total_seconds()))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.assertEqual(Decimal(str(quote["amount"])), expected)
        self.assertEqual(quote["currency"], "INR")
        self.assertTrue(quote["requires_administrative_approval"])
        self.assertFalse(quote["charged"])
        self.assertEqual(len(self.events()), 0)
        self.assertEqual(company.subscription_plan_id, self.plan_id("starter"))
        # Merely selecting the target cannot activate a paid upgrade.
        response = self.client.put(self.path, json={"plan_id": self.plan_id("growth")})
        self.assert_no_transition(response, self.plan_id("starter"), code="SUBSCRIPTION_APPROVAL_REQUIRED")
        response = self.transition("growth", "upgrade", approved_reference="ADMIN-UPGRADE-1")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((company.subscription_started_at, company.subscription_ends_at), (start, end))
        saved = self.events()[0]
        self.assertEqual(saved.event_type, "upgrade")
        self.assertEqual(saved.after_state["upgrade_quote"]["charged"], False)
        self.assertEqual(saved.actor_user_id, 900)
        response = self.transition("business", "upgrade")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((company.subscription_started_at, company.subscription_ends_at), (start, end))

    def test_lower_plan_cannot_be_applied_as_upgrade_or_plan_only_change(self):
        company = self.direct_assignment("business")
        response = self.transition("starter", "upgrade")
        self.assert_no_transition(response, company.subscription_plan_id)
        response = self.client.put(self.path, json={"plan_id": self.plan_id("starter")})
        self.assert_no_transition(response, self.plan_id("business"), code="SUBSCRIPTION_APPROVAL_REQUIRED")

    def test_quote_rejects_inactive_same_unbounded_and_lower_capacity_targets(self):
        company = self.direct_assignment("growth")
        custom = SubscriptionPlan(name="Existing custom", code="unbounded_quote_target", price=25000,
                                  billing_cycle="yearly")
        smaller = SubscriptionPlan(name="Smaller capacity", code="smaller_quote_target", price=25000,
            billing_cycle="yearly", duration_months=12, active_group_limit=2,
            admin_account_limit=1, staff_account_limit=5)
        self.db.add_all([custom, smaller])
        self.db.commit()
        targets = [self.plan_id("growth"), self.plan_id("starter"), custom.id, smaller.id]
        business = self.db.get(SubscriptionPlan, self.plan_id("business"))
        business.is_active = False
        self.db.commit()
        targets.append(business.id)
        for target in targets:
            with self.subTest(target=target):
                response = self.client.get(self.path + "/upgrade-quote", params={"plan_id": target})
                self.assertGreaterEqual(response.status_code, 400, response.text)
                self.assertLess(response.status_code, 500, response.text)
                self.assertEqual(company.subscription_plan_id, self.plan_id("growth"))
                self.assertEqual(len(self.events()), 0)



    def test_correct_plan_immediately_preserves_term_and_audit(self):
        company = self.direct_assignment("business")
        original_start = company.subscription_started_at
        original_end = company.subscription_ends_at

        response = self.transition(
            "starter",
            "correct_plan",
            reason="Business selected by mistake",
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.db.refresh(company)

        self.assertEqual(company.subscription_plan_id, self.plan_id("starter"))
        self.assertEqual(company.subscription_started_at, original_start)
        self.assertEqual(company.subscription_ends_at, original_end)
        self.assertEqual(company.subscription_status, "active")
        self.assertIsNone(company.pending_subscription_plan_id)

        saved = self.events()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].event_type, "correct_plan")
        self.assertEqual(saved[0].actor_user_id, 900)
        self.assertEqual(saved[0].reason, "Business selected by mistake")
        self.assertEqual(saved[0].before_state["plan"]["code"], "business")
        self.assertEqual(saved[0].after_state["plan"]["code"], "starter")

        audit = self.db.query(AuditLog).filter_by(
            company_id=12, module="subscription"
        ).one()
        self.assertEqual(audit.user_id, 900)

    def test_correct_plan_rejects_over_capacity(self):
        company = self.direct_assignment("business")

        self.db.add_all([
            group_row(index, status="upcoming")
            for index in range(1, 5)
        ])
        self.db.commit()

        response = self.transition("starter", "correct_plan")

        self.assert_no_transition(
            response,
            self.plan_id("business"),
            code="PLAN_LIMIT_REACHED",
        )
        self.assertEqual(self.db.query(ChitGroup).count(), 4)

    def test_correct_plan_rejects_pending_downgrade(self):
        company = self.direct_assignment("business")

        response = self.transition("growth", "schedule_downgrade")
        self.assertEqual(response.status_code, 200, response.text)

        response = self.transition("starter", "correct_plan")

        self.assert_no_transition(
            response,
            self.plan_id("business"),
            before_events=1,
        )
        self.assertEqual(
            company.pending_subscription_plan_id,
            self.plan_id("growth"),
        )

    def test_correct_plan_rejects_invalid_terms(self):
        cases = (
            ("expired", -1, -366),
            ("future", 400, 35),
        )

        for label, end_offset, start_offset in cases:
            with self.subTest(case=label):
                company = self.direct_assignment("business")
                company.subscription_started_at = (
                    utcnow() + timedelta(days=start_offset)
                )
                company.subscription_ends_at = (
                    utcnow() + timedelta(days=end_offset)
                )
                self.db.commit()

                response = self.transition("starter", "correct_plan")

                self.assert_no_transition(
                    response,
                    self.plan_id("business"),
                )

    def test_correct_plan_requires_approval_and_distinct_plan(self):
        company = self.direct_assignment("business")

        response = self.client.put(
            self.path,
            json={
                "plan_id": self.plan_id("starter"),
                "action": "correct_plan",
                "reason": "Correction without workflow",
            },
        )
        self.assert_no_transition(
            response,
            self.plan_id("business"),
            code="SUBSCRIPTION_APPROVAL_REQUIRED",
        )

        response = self.transition("business", "correct_plan")
        self.assert_no_transition(
            response,
            self.plan_id("business"),
        )

    def test_correct_plan_preserves_feature_overrides(self):
        from app.models.admin.subscription import CompanyFeatureOverride

        company = self.direct_assignment("business")
        self.db.add(
            CompanyFeatureOverride(
                company_id=12,
                feature_key="reports",
                enabled=False,
            )
        )
        self.db.commit()

        response = self.transition("starter", "correct_plan")
        self.assertEqual(response.status_code, 200, response.text)

        override = self.db.query(CompanyFeatureOverride).filter_by(
            company_id=12,
            feature_key="reports",
        ).one()

        self.assertFalse(override.enabled)
        self.assertEqual(company.subscription_plan_id, self.plan_id("starter"))


    def test_downgrade_schedule_preserves_current_plan_and_can_be_cancelled(self):
        company = self.direct_assignment("business")
        end = company.subscription_ends_at
        response = self.transition("starter", "schedule_downgrade")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(company.subscription_plan_id, self.plan_id("business"))
        self.assertEqual(company.pending_subscription_plan_id, self.plan_id("starter"))
        self.assertEqual(company.pending_subscription_effective_at, end)
        response = self.transition("starter", "apply_downgrade")
        self.assert_no_transition(response, self.plan_id("business"), before_events=1)
        response = self.transition("business", "cancel_downgrade")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(company.pending_subscription_plan_id)
        self.assertIsNone(company.pending_subscription_effective_at)
        self.assertEqual([saved.event_type for saved in self.events()], ["schedule_downgrade", "cancel_downgrade"])

    def test_downgrade_checks_capacity_when_scheduled_and_again_when_due(self):
        company = self.direct_assignment("business")
        self.db.add_all([group_row(index, status="upcoming") for index in range(1, 5)])
        self.db.commit()
        response = self.transition("starter", "schedule_downgrade")
        self.assert_no_transition(response, self.plan_id("business"), code="PLAN_LIMIT_REACHED")
        self.db.get(ChitGroup, 4).status = "cancelled"
        self.db.commit()
        response = self.transition("starter", "schedule_downgrade")
        self.assertEqual(response.status_code, 200, response.text)
        # Usage can grow under the still-current Business plan before renewal.
        self.db.get(ChitGroup, 4).status = "upcoming"
        company.subscription_ends_at = utcnow() - timedelta(days=1)
        company.pending_subscription_effective_at = company.subscription_ends_at
        due = company.subscription_ends_at
        self.db.commit()
        response = self.transition("starter", "apply_downgrade")
        self.assert_no_transition(response, self.plan_id("business"), before_events=1, code="PLAN_LIMIT_REACHED")
        self.assertEqual(self.db.query(ChitGroup).count(), 4)
        self.db.get(ChitGroup, 4).status = "completed"
        self.db.commit()
        response = self.transition("starter", "apply_downgrade")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(company.subscription_plan_id, self.plan_id("starter"))
        self.assertEqual(company.subscription_started_at, due)
        self.assertEqual(company.subscription_ends_at, due + relativedelta(months=12))
        self.assertIsNone(company.pending_subscription_plan_id)
        self.assertEqual(self.db.query(ChitGroup).count(), 4)

    def test_pending_downgrade_cannot_be_bypassed_by_renewal(self):
        company = self.direct_assignment("business")
        response = self.transition("growth", "schedule_downgrade")
        self.assertEqual(response.status_code, 200, response.text)
        company.subscription_ends_at = utcnow() - timedelta(days=1)
        company.pending_subscription_effective_at = company.subscription_ends_at
        self.db.commit()
        response = self.transition("business", "renew")
        self.assert_no_transition(response, self.plan_id("business"), before_events=1)
        self.assertEqual(company.pending_subscription_plan_id, self.plan_id("growth"))

    def test_renewal_due_only_and_preserves_due_date_during_grace(self):
        company = self.direct_assignment("growth")
        response = self.transition("growth", "renew")
        self.assert_no_transition(response, self.plan_id("growth"))
        company.subscription_ends_at = utcnow() - timedelta(days=1)
        due = company.subscription_ends_at
        self.db.commit()
        response = self.transition("growth", "renew")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(company.subscription_started_at, due)
        self.assertEqual(company.subscription_ends_at, due + relativedelta(months=12))
        self.assertEqual(self.events()[0].event_type, "renew")

    def test_renewal_after_grace_starts_new_term_without_deleting_history(self):
        company = self.direct_assignment("growth", remaining=-16)
        self.db.add(group_row(1, status="paused"))
        self.db.commit()
        before = utcnow()
        response = self.transition("growth", "renew")
        after = utcnow()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLessEqual(before, company.subscription_started_at)
        self.assertLessEqual(company.subscription_started_at, after)
        self.assertEqual(company.subscription_ends_at, company.subscription_started_at + relativedelta(months=12))
        self.assertEqual(self.db.get(ChitGroup, 1).status, "paused")

    def test_custom_plan_and_override_compatibility_preserves_actor_history(self):
        custom = SubscriptionPlan(name="Existing custom", code="legacy_custom", price=1, billing_cycle="yearly")
        self.db.add(custom)
        self.db.commit()
        response = self.client.put(self.path, json={"plan_id": custom.id})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["subscription"]["status"], "legacy")
        response = self.client.put(self.path, json={"plan_id": custom.id, "overrides": {"loans": True}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["features"]["loans"])
        self.assertIsNone(self.db.get(Company, 12).subscription_ends_at)
        self.assertEqual([saved.event_type for saved in self.events()], ["assignment", "overrides"])
        self.assertTrue(all(saved.actor_user_id == 900 for saved in self.events()))
        response = self.client.get(self.path + "/events")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([row["event_type"] for row in response.json()], ["overrides", "assignment"])

    def test_commercial_catalog_rejects_price_limits_duration_and_feature_mutation(self):
        all_plans = self.client.get("/super-admin/plans").json()
        for plan in all_plans:
            payload = {key: value for key, value in plan.items() if key not in ("id", "created_at", "updated_at")}
            for change in ({"price": 1}, {"active_group_limit": 99}, {"staff_account_limit": 99},
                           {"admin_account_limit": 2}, {"duration_months": 1}, {"billing_cycle": "monthly"},
                           {"features": {**payload["features"], "loans": not payload["features"]["loans"]}},
                           {"code": "changed_code"}):
                with self.subTest(plan=plan["code"], change=change):
                    response = self.client.put(f"/super-admin/plans/{plan['id']}", json={**payload, **change})
                    self.assertEqual(response.status_code, 422, response.text)
                    self.db.rollback()
                    saved = self.db.get(SubscriptionPlan, plan["id"])
                    self.assertEqual(Decimal(saved.price), Decimal(plan["price"]))
                    self.assertEqual(saved.active_group_limit, plan["active_group_limit"])
            response = self.client.put(f"/super-admin/plans/{plan['id']}",
                                       json={**payload, "description": "Reviewed catalog description"})
            self.assertEqual(response.status_code, 200, response.text)

    def test_super_admin_authentication_rejects_missing_company_customer_and_stale_sessions(self):
        del self.app.dependency_overrides[require_super_admin]
        denied_headers = ({},
            {"Authorization": "Bearer " + create_access_token({"sub": "1"})},
            {"Authorization": "Bearer " + create_access_token({"sub": "1", "token_type": "customer"})},
            {"Authorization": "Bearer " + create_access_token({"sub": "1", "token_type": "super_admin", "session_version": 0})},
            {"Authorization": "Bearer " + create_access_token({"sub": "900", "token_type": "super_admin", "session_version": 2})})
        for headers in denied_headers:
            for path in ("/super-admin/plans", self.path, self.path + "/events",
                         self.path + f"/upgrade-quote?plan_id={self.plan_id('growth')}"):
                self.assertEqual(self.client.get(path, headers=headers).status_code, 401)
            response = self.client.put(self.path, headers=headers, json={"plan_id": self.plan_id("starter"),
                "action": "assign", "workflow": "administrative", "reason": "Unauthorized request"})
            self.assertEqual(response.status_code, 401, response.text)
        self.assertIsNone(self.db.get(Company, 12).subscription_plan_id)
        self.assertEqual(len(self.events()), 0)
        headers = {"Authorization": "Bearer " + create_access_token({"sub": "900", "token_type": "super_admin", "session_version": 3})}
        self.assertEqual(self.client.get("/super-admin/plans", headers=headers).status_code, 200)
