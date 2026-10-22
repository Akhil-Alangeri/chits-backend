"""Isolated SQLite transactions and mocked SMTP; never contacts live services."""
import os
import smtplib
import unittest
import importlib.util
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

from sqlalchemy import BigInteger, create_engine, event, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import Base
from app.models.admin.company import Company
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_months import ChitMonth
from app.models.admin.welcome_outbox import WelcomeOutbox
from app.schemas.chit_member import ChitMemberCreate, ChitMemberUpdate
from app.schemas.chit_group import ChitGroupUpdate
from app.services.chit_member_service import add_chit_member, update_chit_member
from app.services.chit_group_service import update_chit_group
from app.services import welcome_notifications as service
from app.services.welcome_template import render_welcome
from app.services.welcome_email import send_welcome_email, smtp_config, EmailConfigurationError
from app.welcome_worker import main


@compiles(BigInteger, "sqlite")
def sqlite_bigint(element, compiler, **kw):
    return "INTEGER"


class WelcomeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.factory()
        self.db.add_all([Company(id=1, company_name="Lotus Chits", status="active"),
                         Company(id=2, company_name="Cedar Chits", status="active")])
        self.db.flush()
        self.db.add_all([
            CustomerProfile(id=1, company_id=1, customer_code="C1", display_name="Ananya",
                            mobile="9876543210", email="ananya@example.com"),
            CustomerProfile(id=2, company_id=2, customer_code="C2", display_name="Ananya Cedar",
                            mobile="9876543210", email="cedar@example.com"),
        ])
        for group_id, company_id in ((1, 1), (2, 1), (3, 2)):
            self.db.add(ChitGroup(id=group_id, company_id=company_id, name=f"Group {group_id}",
                code=f"G{group_id}", chit_value=1000, monthly_emi=1000, duration_months=1,
                max_members=10, status="active", start_date=date(2026, 11, 1)))
        self.db.flush()
        for group_id, company_id in ((1, 1), (2, 1), (3, 2)):
            self.db.add(ChitMonth(chit_id=group_id, company_id=company_id, month_number=1,
                                 month_date=date(2026, 11, 1), monthly_emi=1000, monthly_lift_amount=1000))
        self.db.commit()
        self.send = Mock()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def member(self, status="confirmed", chit_id=1, profile_id=1):
        member = ChitMember(chit_id=chit_id, customer_profile_id=profile_id, member_number=1,
                            slot_number=1, member_name="Slot name", status=status)
        self.db.add(member)
        self.db.commit()
        return member

    def queue(self, member, company_id=1):
        result = service.enqueue_membership_welcome(self.db, member.id, company_id)
        self.db.commit()
        return result

    def process(self):
        self.db.rollback()  # Worker uses independent sessions, as in production.
        return service.process_welcome_batch(self.factory, send=self.send)

    def row(self):
        self.db.expire_all()
        return self.db.query(WelcomeOutbox).one()

    def test_active_and_confirmed_with_active_group(self):
        for status in ("active", "confirmed", " CONFIRMED "):
            with self.subTest(status=status):
                m = self.member(status, chit_id=1 if status == "active" else 2 if status == "confirmed" else 3,
                                profile_id=1 if status != " CONFIRMED " else 2)
                self.assertTrue(self.queue(m, 2 if status == " CONFIRMED " else 1))
        self.assertEqual(self.process(), 3)
        self.assertEqual(self.send.call_count, 3)
        self.assertEqual(self.db.query(WelcomeOutbox).filter_by(status="sent").count(), 3)

    def test_pending_and_inactive_are_ineligible(self):
        m = self.member("pending")
        self.assertFalse(self.queue(m))
        m.status = "active"
        for status in ("draft", "inactive", "upcoming", "completed"):
            self.db.get(ChitGroup, 1).status = status
            self.assertFalse(self.queue(m))
        self.assertEqual(self.process(), 0)
        self.send.assert_not_called()

    def test_real_member_creation_preserves_installments_and_queues(self):
        result = add_chit_member(self.db, 1, 1,
            ChitMemberCreate(customer_profile_id=1, member_name="Ananya"))
        self.assertIsInstance(result, ChitMember)
        self.assertEqual(len(result.installments), 1)
        self.assertEqual(self.row().membership_id, result.id)
        self.send.assert_not_called()
        self.process()
        self.send.assert_called_once()

    def test_pending_to_confirmed_update_hook(self):
        m = self.member("pending")
        self.assertFalse(self.queue(m))
        update_chit_member(self.db, 1, m.id, ChitMemberUpdate(status="confirmed", slot_number=1))
        self.assertEqual(self.process(), 1)
        update_chit_member(self.db, 1, m.id, ChitMemberUpdate(notes="Updated", slot_number=1))
        self.assertEqual(self.process(), 0)
        self.send.assert_called_once()

    def test_inactive_to_active_group_update_hook(self):
        m = self.member()
        self.db.get(ChitGroup, 1).status = "upcoming"
        self.db.commit()
        self.assertFalse(self.queue(m))
        result = update_chit_group(self.db, 1, 1, ChitGroupUpdate(status="active"))
        self.assertEqual(result.status, "active")
        self.assertEqual(self.process(), 1)
        update_chit_group(self.db, 1, 1, ChitGroupUpdate(status="active", name="Renamed"))
        self.assertEqual(self.process(), 0)
        self.send.assert_called_once()

    def test_duplicate_events_and_unrelated_historical_update(self):
        m = self.member()
        update_chit_member(self.db, 1, m.id, ChitMemberUpdate(notes="Historic", slot_number=1))
        self.assertEqual(self.db.query(WelcomeOutbox).count(), 0)
        self.assertTrue(self.queue(m))
        self.assertFalse(self.queue(m))
        self.process()
        self.assertFalse(self.queue(m))
        self.process()
        self.send.assert_called_once()

    def test_multiple_memberships_and_company_specific_content(self):
        for chit_id, profile_id, company_id in ((1, 1, 1), (2, 1, 1), (3, 2, 2)):
            self.queue(self.member(chit_id=chit_id, profile_id=profile_id), company_id)
        self.assertEqual(self.process(), 3)
        messages = [call.args for call in self.send.call_args_list]
        self.assertEqual(sum(args[0] == "ananya@example.com" for args in messages), 2)
        cedar = next(args for args in messages if args[0] == "cedar@example.com")
        self.assertEqual(cedar[1], "Welcome to Cedar Chits | NexNidhi")
        self.assertIn("Group 3", cedar[2])
        self.assertNotIn("Lotus", cedar[2])
        self.assertIn("Ananya Cedar", cedar[2])

    def test_wrong_tenant_relationship_never_queues(self):
        m = self.member(profile_id=2)
        self.assertFalse(self.queue(m, 1))
        self.assertFalse(self.queue(m, 2))
        self.assertEqual(self.process(), 0)

    def test_worker_rechecks_tenant_and_eligibility(self):
        m = self.member()
        self.queue(m)
        self.db.get(CustomerProfile, 1).company_id = 2
        self.db.commit()
        self.process()
        self.send.assert_not_called()
        self.assertEqual(self.row().last_error, "membership_ineligible")

    def test_missing_email_retries_after_correction(self):
        self.db.get(CustomerProfile, 1).email = None
        self.db.commit()
        self.queue(self.member())
        self.process()
        self.send.assert_not_called()
        row = self.row()
        self.assertEqual((row.status, row.last_error), ("failed", "missing_or_invalid_email"))
        self.db.get(CustomerProfile, 1).email = "fixed@example.com"
        row.available_at = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()
        self.process()
        self.assertEqual(self.row().status, "sent")
        self.assertEqual(self.send.call_args.args[0], "fixed@example.com")

    def test_provider_failure_then_retry_and_safe_logs(self):
        self.queue(self.member())
        self.send.side_effect = smtplib.SMTPException("private@example.com password=secret")
        with self.assertLogs(service.logger, level="WARNING") as logs:
            self.process()
        self.assertNotIn("private@example.com", str(logs.output))
        self.assertNotIn("secret", str(logs.output))
        row = self.row()
        self.assertEqual((row.status, row.attempts, row.sent_at), ("failed", 1, None))
        self.assertIsNotNone(row.available_at)
        self.assertEqual(self.process(), 0)
        row = self.row()
        row.available_at = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()
        self.send.side_effect = None
        self.process()
        self.assertEqual((self.row().status, self.row().attempts), ("sent", 2))

    def test_claim_exclusion_stale_recovery_and_fencing(self):
        self.queue(self.member())
        first = service.claim_one(self.factory)
        self.assertIsNotNone(first)
        self.assertIsNone(service.claim_one(self.factory))
        row = self.row()
        row.claimed_at = datetime.utcnow() - service.LEASE - timedelta(seconds=1)
        self.db.commit()
        second = service.claim_one(self.factory)
        self.assertNotEqual(first[1], second[1])
        self.assertFalse(service.deliver_claim(self.factory, first, self.send))
        self.assertFalse(service.finish(self.factory, *first))
        service.deliver_claim(self.factory, second, self.send)
        self.send.assert_called_once()
        self.assertEqual(self.row().status, "sent")

    def test_retry_limit(self):
        self.queue(self.member())
        self.row().attempts = service.MAX_ATTEMPTS - 1
        self.db.commit()
        self.send.side_effect = RuntimeError()
        self.process()
        self.assertEqual((self.row().status, self.row().available_at), ("failed", None))
        self.assertEqual(self.process(), 0)

    def test_finish_ownership_is_checked_at_update_time(self):
        self.queue(self.member())
        claim = service.claim_one(self.factory)
        intercepted = []
        def reclaim_before_update(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("UPDATE membership_welcome_outbox") and not intercepted:
                intercepted.append(True)
                conn.exec_driver_sql("UPDATE membership_welcome_outbox SET claim_token = 'new-owner'")
        event.listen(self.engine, "before_cursor_execute", reclaim_before_update)
        try:
            self.assertFalse(service.finish(self.factory, *claim))
        finally:
            event.remove(self.engine, "before_cursor_execute", reclaim_before_update)
        self.assertEqual((self.row().status, self.row().claim_token), ("processing", "new-owner"))

    def test_no_transaction_open_during_send(self):
        self.queue(self.member())
        active = set()
        @event.listens_for(self.engine, "begin")
        def began(conn):
            active.add(id(conn))
        @event.listens_for(self.engine, "rollback")
        @event.listens_for(self.engine, "commit")
        def ended(conn):
            active.discard(id(conn))
        def send(*args):
            self.assertFalse(active)
        service.process_welcome_batch(self.factory, send=send)

    def test_rollback_removes_notification_intent(self):
        m = self.member("pending")
        m.status = "active"
        service.enqueue_membership_welcome(self.db, m.id, 1)
        self.db.rollback()
        self.assertEqual(self.db.query(WelcomeOutbox).count(), 0)
        self.assertEqual(self.db.get(ChitMember, m.id).status, "pending")
        self.assertEqual(self.process(), 0)

    def test_cancellation_before_delivery_and_reactivation(self):
        m = self.member()
        self.queue(m)
        m.status = "cancelled"
        self.db.commit()
        self.process()
        self.send.assert_not_called()
        update_chit_member(self.db, 1, m.id, ChitMemberUpdate(status="active", slot_number=1))
        self.process()
        self.send.assert_called_once()

    def test_deleted_member_is_not_sent(self):
        m = self.member()
        self.queue(m)
        self.db.delete(m)
        self.db.commit()
        self.process()
        self.send.assert_not_called()

    def test_template_escaping_links_and_plaintext(self):
        subject, text, html = render_welcome('<img src=x onerror="alert(1)">', 'Lotus\r\nBcc: victim', '<script>x</script>', "confirmed")
        self.assertNotIn("\n", subject)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('href="https://customer.nexnidhi.in/"', html)
        self.assertIn('href="https://nexnidhi.in/"', html)
        self.assertIn("Login as Customer", html)
        self.assertIn("never share your OTP", text)
        self.assertIn("not a payment", text)
        self.assertIn("https://customer.nexnidhi.in/", text)
        self.assertIn("NexNidhi.", html)
        self.assertIn("Dear ,", render_welcome(None, None, None, None)[1])


class SmtpTests(unittest.TestCase):
    env = {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_USERNAME": "sender",
           "SMTP_PASSWORD": "secret", "SMTP_FROM": "hello@nexnidhi.in", "SMTP_USE_TLS": "true",
           "SMTP_USE_SSL": "false"}

    def test_multipart_starttls_and_ssl(self):
        for implicit in (False, True):
            values = dict(self.env, SMTP_USE_TLS=str(not implicit).lower(),
                          SMTP_USE_SSL=str(implicit).lower(), SMTP_PORT="465" if implicit else "587")
            with patch.dict(os.environ, values, clear=True), patch("app.services.welcome_email.smtplib.SMTP") as smtp, \
                 patch("app.services.welcome_email.smtplib.SMTP_SSL") as smtp_ssl, \
                 patch("app.services.welcome_email.ssl.create_default_context"):
                connection = (smtp_ssl if implicit else smtp).return_value.__enter__.return_value
                connection.send_message.return_value = {}
                send_welcome_email("test@example.com", *render_welcome("Test", "Lotus", "Lotus One", "active"), 5)
                message = connection.send_message.call_args.args[0]
                self.assertEqual(message.get_content_type(), "multipart/alternative")
                self.assertEqual([p.get_content_type() for p in message.iter_parts()], ["text/plain", "text/html"])
                self.assertTrue(message["Message-ID"].startswith("<welcome-"))
                self.assertTrue(message["Message-ID"].endswith("@nexnidhi.in>"))
                self.assertNotIn("welcome-5@", message["Message-ID"])
                connection.login.assert_called_once_with("sender", "secret")
                self.assertEqual(connection.starttls.called, not implicit)

    def test_unconfigured_or_insecure_smtp_fails_without_network(self):
        for values in ({}, dict(self.env, SMTP_USE_TLS="false"), dict(self.env, SMTP_FROM="invalid"),
                       dict(self.env, SMTP_PORT="bad"), dict(self.env, SMTP_USE_SSL="true")):
            with self.subTest(values={k: v for k, v in values.items() if k != "SMTP_PASSWORD"}):
                with patch.dict(os.environ, values, clear=True), patch("app.services.welcome_email.smtplib.SMTP") as smtp:
                    with self.assertRaises(EmailConfigurationError):
                        smtp_config()
                    smtp.assert_not_called()

    def test_worker_disabled_or_missing_config_never_claims(self):
        with patch.dict(os.environ, {}, clear=True), patch("sys.argv", ["welcome_worker"]), \
             patch("app.welcome_worker.process_welcome_batch") as process:
            self.assertEqual(main(), 0)
            process.assert_not_called()
            with patch.dict(os.environ, {"WELCOME_EMAIL_DELIVERY_ENABLED": "true"}):
                self.assertEqual(main(), 1)
                process.assert_not_called()

    def test_worker_watch_polls_again_after_database_failure(self):
        with patch.dict(os.environ, {"WELCOME_EMAIL_DELIVERY_ENABLED": "true"}), \
             patch("sys.argv", ["welcome_worker", "--watch", "--interval", "5"]), \
             patch("app.welcome_worker.smtp_config"), \
             patch("app.welcome_worker.process_welcome_batch", side_effect=[RuntimeError(), 1]) as process, \
             patch("app.welcome_worker.time.sleep", side_effect=[None, KeyboardInterrupt()]) as sleep:
            self.assertEqual(main(), 0)
            self.assertEqual(process.call_count, 2)
            self.assertEqual(sleep.call_count, 2)


class PersistenceTests(unittest.TestCase):
    def test_concurrent_workers_claim_one_record_once(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine("sqlite:///" + str(Path(directory) / "outbox.db"),
                                   connect_args={"timeout": 15})
            WelcomeOutbox.__table__.create(engine)
            factory = sessionmaker(bind=engine)
            with factory() as db:
                db.add(WelcomeOutbox(membership_id=1, company_id=1))
                db.commit()
            barrier = Barrier(8)
            def claim(_):
                barrier.wait(timeout=10)
                return service.claim_one(factory)
            try:
                with ThreadPoolExecutor(max_workers=8) as executor:
                    claims = list(executor.map(claim, range(8)))
                self.assertEqual(sum(result is not None for result in claims), 1)
                with factory() as db:
                    self.assertEqual(db.query(WelcomeOutbox).one().attempts, 1)
            finally:
                engine.dispose()

    def test_additive_migration_creates_empty_outbox(self):
        path = Path(__file__).resolve().parents[1] / "alembic/versions/e9a42b701105_membership_welcome_outbox.py"
        spec = importlib.util.spec_from_file_location("welcome_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE preserved (id INTEGER PRIMARY KEY, value TEXT)")
            connection.exec_driver_sql("INSERT INTO preserved VALUES (1, 'keep')")
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            inspector = inspect(connection)
            self.assertEqual({col["name"] for col in inspector.get_columns(WelcomeOutbox.__tablename__)},
                             set(WelcomeOutbox.__table__.columns.keys()))
            self.assertIn("uq_membership_welcome_type", {c["name"] for c in inspector.get_unique_constraints(WelcomeOutbox.__tablename__)})
            self.assertEqual(connection.exec_driver_sql("SELECT value FROM preserved").scalar(), "keep")
            self.assertEqual(connection.exec_driver_sql("SELECT count(*) FROM membership_welcome_outbox").scalar(), 0)
        engine.dispose()
