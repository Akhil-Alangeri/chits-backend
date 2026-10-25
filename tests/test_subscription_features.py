"""Feature gates through real routes using only an isolated SQLite database."""
from datetime import datetime, timedelta, timezone
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
from app.models.admin.company import Company
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.subscription import CompanyFeatureOverride, Feature, PlanFeature, SubscriptionPlan
from app.models.admin.user import User
from app.models.support.ticket import SupportTicket, TicketMessage
from app.routes.admin_ticket_router import router as admin_tickets_router
from app.routes.customer.ticket_router import router as customer_tickets_router
from app.routes.collection_report import router as collections_router
from app.routes.due_reports import router as due_router
from app.routes.chit_reports import router as chits_router
from app.routes.ledger_reports import router as ledger_router
from app.routes.loan_reports import router as loans_router
from app.routes.expenses_reports_router import router as expenses_router
from app.services.support import ticket_service


@compiles(BigInteger, "sqlite")
def sqlite_bigint(element, compiler, **kw):
    return "INTEGER"


class SubscriptionFeatureTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        keys = ("reports", "loans", "expenses", "support_tickets", "staff_permissions")
        self.db.add_all([Feature(key=key, name=key) for key in keys])
        self.db.add_all([
            SubscriptionPlan(id=1, name="Starter", code="starter", price=9999, billing_cycle="yearly",
                             active_group_limit=3, admin_account_limit=1, staff_account_limit=0, duration_months=12),
            SubscriptionPlan(id=2, name="Growth", code="growth", price=14999, billing_cycle="yearly",
                             active_group_limit=7, admin_account_limit=1, staff_account_limit=3, duration_months=12),
        ])
        self.db.flush()
        self.db.add_all([PlanFeature(plan_id=plan_id, feature_key=key, enabled=plan_id == 2)
                         for plan_id in (1, 2) for key in keys])
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.add_all([Company(id=index, company_name=f"Company {index}", email=f"{index}@example.com",
            status="active", subscription_plan_id=index, subscription_status="active",
            subscription_started_at=now - timedelta(days=100), subscription_ends_at=now + timedelta(days=265))
            for index in (1, 2)])
        self.db.flush()
        self.db.add_all([User(id=index, company_id=index, login_id=f"admin{index}", password_hash="unused",
                             role="company_admin", status="active") for index in (1, 2)])
        self.db.add_all([CustomerProfile(id=index, company_id=index, customer_code=f"C{index}",
            display_name=f"Customer {index}", mobile=f"999999999{index}", status="active") for index in (1, 2)])
        self.db.flush()
        self.db.add_all([SupportTicket(id=index, ticket_number=f"TKT-{index:06d}", company_id=index,
            customer_profile_id=index, subject="Historical ticket", description="Preserve ticket history")
            for index in (1, 2)])
        self.db.commit()
        self.app = FastAPI()
        self.report_routers = (collections_router, due_router, chits_router, ledger_router, loans_router, expenses_router)
        for router in (*self.report_routers, admin_tickets_router, customer_tickets_router):
            self.app.include_router(router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)
        self.admin = {index: {"Authorization": "Bearer " + create_access_token({"sub": str(index)})}
                      for index in (1, 2)}
        self.customer = {index: {"Authorization": "Bearer " + create_access_token({
            "sub": str(index), "token_type": "customer", "customer_profile_id": index})} for index in (1, 2)}

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def assert_restricted(self, response, feature):
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "FEATURE_NOT_AVAILABLE")
        self.assertEqual(response.json()["detail"]["feature"], feature)

    def override(self, company_id, key, enabled):
        self.db.merge(CompanyFeatureOverride(company_id=company_id, feature_key=key, enabled=enabled))
        self.db.commit()

    def test_every_report_and_export_requires_reports_even_with_module_overrides(self):
        self.override(1, "loans", True)
        self.override(1, "expenses", True)
        for router in self.report_routers:
            for route in router.routes:
                for method in route.methods:
                    with self.subTest(path=route.path, method=method):
                        self.assert_restricted(self.client.request(method, route.path, headers=self.admin[1]), "reports")

    def test_growth_reports_work_and_module_permissions_still_apply(self):
        for path in ("/reports/collections", "/reports/due", "/reports/chits", "/reports/ledger",
                     "/reports/loans", "/reports/expenses"):
            response = self.client.get(path, headers=self.admin[2])
            self.assertEqual(response.status_code, 200, f"{path}: {response.text}")
        for key in ("loans", "expenses"):
            self.override(2, key, False)
            self.assert_restricted(self.client.get(f"/reports/{key}", headers=self.admin[2]), key)

    def test_starter_admin_history_and_pagination_remain_readable_but_writes_are_denied(self):
        listing = self.client.get("/admin/tickets?page=1&page_size=1", headers=self.admin[1])
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual(listing.json()["pagination"], {"page": 1, "page_size": 1, "total": 1, "total_pages": 1})
        self.assertEqual([ticket["id"] for ticket in listing.json()["tickets"]], [1])
        self.assertEqual(self.client.get("/admin/tickets/1", headers=self.admin[1]).status_code, 200)
        for method, suffix, body in (("post", "messages", {"message": "Reply"}),
            ("patch", "status", {"status": "closed"}), ("patch", "priority", {"priority": "high"}),
            ("patch", "category", {"category": "technical"}), ("patch", "assign", {"assigned_to_user_id": None})):
            with self.subTest(suffix=suffix):
                self.assert_restricted(self.client.request(method, f"/admin/tickets/1/{suffix}",
                    headers=self.admin[1], json=body), "support_tickets")
        self.assertEqual(self.db.get(SupportTicket, 1).status, "open")
        self.assertEqual(self.db.query(TicketMessage).count(), 0)

    def test_starter_customer_reads_history_but_cannot_create_or_reply(self):
        self.assertEqual(self.client.get("/customer/tickets?company_id=1", headers=self.customer[1]).status_code, 200)
        self.assertEqual(self.client.get("/customer/tickets/1", headers=self.customer[1]).status_code, 200)
        self.assert_restricted(self.client.post("/customer/tickets", headers=self.customer[1], json={
            "company_id": 1, "subject": "New ticket", "description": "Help"}), "support_tickets")
        self.assert_restricted(self.client.post("/customer/tickets/1/messages", headers=self.customer[1],
            json={"message": "New reply"}), "support_tickets")
        self.assertEqual(self.db.query(SupportTicket).count(), 2)

    def test_support_authorization_resolves_tenant_before_feature_checks(self):
        response = self.client.post("/customer/tickets", headers=self.customer[1], json={
            "company_id": 2, "subject": "Foreign ticket", "description": "Forbidden"})
        self.assertEqual(response.status_code, 403)
        self.assertIsInstance(response.json()["detail"], str)
        for path, headers in (("/customer/tickets/2/messages", self.customer[1]),
                              ("/admin/tickets/2/messages", self.admin[1])):
            self.assertEqual(self.client.post(path, headers=headers, json={"message": "Foreign reply"}).status_code, 404)
        with self.assertRaises(ValueError):
            ticket_service.create_customer_ticket(self.db, 1, 2, "Foreign ticket", "Forbidden")
        self.assertEqual(self.db.query(TicketMessage).count(), 0)

    def test_growth_support_mutations_work_including_after_subscription_expiry(self):
        company = self.db.get(Company, 2)
        company.subscription_ends_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=20)
        self.db.commit()
        created = self.client.post("/customer/tickets", headers=self.customer[2], json={
            "company_id": 2, "subject": "Growth ticket", "description": "Help with servicing"})
        self.assertEqual(created.status_code, 201, created.text)
        ticket_id = created.json()["id"]
        for headers, prefix in ((self.customer[2], "customer"), (self.admin[2], "admin")):
            response = self.client.post(f"/{prefix}/tickets/{ticket_id}/messages", headers=headers,
                                        json={"message": "Servicing continues"})
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.client.patch(f"/admin/tickets/{ticket_id}/status", headers=self.admin[2],
            json={"status": "resolved"}).status_code, 200)
        self.assertEqual(self.db.query(TicketMessage).count(), 2)

    def test_support_override_precedence_is_preserved(self):
        self.override(1, "support_tickets", True)
        response = self.client.post("/customer/tickets/1/messages", headers=self.customer[1], json={"message": "Approved override"})
        self.assertEqual(response.status_code, 201, response.text)
        self.override(2, "support_tickets", False)
        self.assert_restricted(self.client.post("/admin/tickets/2/messages", headers=self.admin[2],
            json={"message": "Disabled override"}), "support_tickets")

    def test_internal_support_mutations_also_enforce_read_only(self):
        calls = (
            lambda: ticket_service.create_admin_ticket(self.db, 1, 1, "New admin ticket", "Help"),
            lambda: ticket_service.update_ticket(self.db, 1, 1, subject="Changed"),
            lambda: ticket_service.delete_ticket(self.db, 1, 1),
        )
        for call in calls:
            with self.subTest(call=call), self.assertRaises(HTTPException) as raised:
                call()
            self.assertEqual(raised.exception.detail["feature"], "support_tickets")
        self.assertEqual(self.db.query(SupportTicket).count(), 2)


if __name__ == "__main__":
    unittest.main()
