"""Chit totals, payments allocated to installment months, and expense ownership."""
import unittest
from datetime import date, datetime as real_datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import app.models
from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.chitlift import ChitLift
from app.models.admin.expenses import Expense
from app.models.admin.payment_transaction import PaymentTransaction
from app.schemas.expenses import ExpenseCreate, ExpenseUpdate
from app.schemas.payment_summary import ChitPaymentSummaryResponse
from app.services.expenses_service import create_expense, update_expense, delete_expense
from app.services.payment_transaction import get_chit_payment_summary


@compiles(BigInteger, 'sqlite')
def sqlite_bigint(element, compiler, **kw):
    return 'INTEGER'


class ChitPaymentSummaryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.clock = patch('app.services.payment_transaction.datetime')
        self.now = self.clock.start()
        self.now.now.return_value = real_datetime(2026, 11, 10, tzinfo=ZoneInfo('Asia/Kolkata'))
        for identifier, company in [(1, 1), (2, 1), (3, 2), (4, 1)]:
            self.db.add(ChitGroup(id=identifier, company_id=company, name=f'Chit {identifier}',
                                  code=f'C{identifier}', chit_value=10000, monthly_emi=1000,
                                  duration_months=10, max_members=10, status='active'))
        self.db.flush()
        for identifier, chit in [(1, 1), (2, 1), (3, 2), (4, 3)]:
            self.db.add(ChitMember(id=identifier, chit_id=chit, customer_profile_id=identifier,
                                   member_number=identifier, slot_number=1, member_name='Member',
                                   status='active'))
        self.db.flush()

    def tearDown(self):
        self.clock.stop()
        self.db.close()
        self.engine.dispose()

    def installment(self, identifier, member, month, amount=1000):
        self.db.add(ChitInstallment(id=identifier, chit_member_id=member,
                                    installment_number=identifier,
                                    due_date=date(2026, month, 1), due_amount=amount))
        self.db.flush()

    def payment(self, identifier, installment, month, amount):
        self.db.add(PaymentTransaction(id=identifier, installment_id=installment,
                                       payment_date=date(2026, month, 5),
                                       payment_method='cash', amount=amount, created_by=1))
        self.db.flush()

    def expense(self, identifier, chit, amount, company=1):
        self.db.add(Expense(id=identifier, company_id=company, chit_id=chit, amount=amount,
                            created_by=1, category='other', expense_date=date(2026, 11, 1),
                            payment_method='cash'))
        self.db.flush()

    def test_default_dues_stop_at_current_month_and_collections_follow_installment_month(self):
        for identifier, member, month in [(1, 1, 10), (2, 1, 11), (3, 1, 12), (4, 2, 11),
                                          (5, 3, 11), (6, 4, 11)]:
            self.installment(identifier, member, month)
        # Arrears and advances count toward their allocated installment month.
        for identifier, installment, month, amount in [(1, 1, 10, 100), (2, 1, 11, 200),
                                                       (3, 2, 10, 300), (4, 2, 11, 400),
                                                       (5, 3, 11, 100), (6, 5, 11, 999),
                                                       (7, 6, 11, 999)]:
            self.payment(identifier, installment, month, amount)
        for identifier, chit, company, amount in [(1, 1, 1, Decimal('500.50')),
                                                 (2, 2, 1, 999), (3, 3, 2, 999)]:
            self.db.add(ChitLift(id=identifier, company_id=company, chit_id=chit,
                                 chit_member_id=identifier, customer_name='Member',
                                 member_number=str(identifier), lift_date=date(2026, 11, 1),
                                 lifted_amount=amount, payout_status='paid'))
        for identifier, chit, company, amount in [(1, 1, 1, 150), (2, 1, 1, 50),
                                                 (3, None, 1, 999), (4, 2, 1, 999),
                                                 (5, 3, 2, 999), (6, 1, 2, 999)]:
            self.expense(identifier, chit, amount, company)
        result = ChitPaymentSummaryResponse.model_validate(get_chit_payment_summary(self.db, 1, 1))
        self.assertEqual(result.total_due, 3000)
        self.assertEqual(result.total_paid, 1100)
        self.assertEqual(result.total_remaining, 2000)
        self.assertEqual(result.this_month_collections, 700)
        self.assertEqual(result.this_month_due, 1300)
        self.assertEqual(result.total_lift_amount, 500.50)
        self.assertEqual(result.others_amount, 200)
        self.assertEqual((result.current_year, result.current_month), (2026, 11))
        self.assertEqual((result.reference_year, result.reference_month), (2026, 11))
        self.now.now.assert_called_with(ZoneInfo('Asia/Kolkata'))

    def test_selected_month_controls_monthly_due_and_cumulative_cutoff(self):
        for identifier, month in [(1, 10), (2, 11), (3, 12)]:
            self.installment(identifier, 1, month)
        self.payment(1, 1, 10, 200)
        self.payment(2, 2, 11, 300)
        october = get_chit_payment_summary(self.db, 1, 1, month=10, year=2026)
        self.assertEqual(october['this_month_due'], 800)
        self.assertEqual(october['this_month_collections'], 200)
        self.assertEqual(october['total_remaining'], 800)
        self.assertEqual(october['total_due'], 1000)
        self.assertEqual(october['total_paid'], 500)
        self.assertEqual((october['reference_year'], october['reference_month']), (2026, 10))
        november = get_chit_payment_summary(self.db, 1, 1)
        self.assertEqual(november['this_month_due'], 700)
        self.assertEqual(november['total_remaining'], 1500)
        december = get_chit_payment_summary(self.db, 1, 1, month=12, year=2026)
        self.assertEqual(december['this_month_due'], 1000)
        self.assertEqual(december['total_remaining'], 2500)

    def test_selected_year_and_empty_reference_month(self):
        self.installment(1, 1, 11)
        previous_year = get_chit_payment_summary(self.db, 1, 1, month=11, year=2025)
        self.assertEqual(previous_year['this_month_due'], 0)
        self.assertEqual(previous_year['total_remaining'], 0)
        next_year = get_chit_payment_summary(self.db, 1, 1, month=1, year=2027)
        self.assertEqual(next_year['this_month_due'], 0)
        self.assertEqual(next_year['total_remaining'], 1000)

    def test_monthly_amount_ignores_creation_and_update_timestamps(self):
        self.installment(1, 1, 11)
        self.payment(1, 1, 11, 250)
        installment = self.db.get(ChitInstallment, 1)
        payment = self.db.get(PaymentTransaction, 1)
        installment.created_at = real_datetime(2026, 10, 25)
        installment.updated_at = real_datetime(2026, 12, 5)
        payment.created_at = real_datetime(2026, 10, 31, 23, 59)
        payment.updated_at = real_datetime(2026, 12, 1)
        self.db.flush()

        november = get_chit_payment_summary(self.db, 1, 1, month=11, year=2026)
        self.assertEqual(november['this_month_collections'], 250)
        self.assertEqual(november['this_month_due'], 750)
        for month in (10, 12):
            result = get_chit_payment_summary(self.db, 1, 1, month=month, year=2026)
            self.assertEqual(result['this_month_collections'], 0)

        payment.created_at = real_datetime(2027, 1, 1)
        payment.updated_at = real_datetime(2027, 2, 1)
        self.db.flush()
        self.assertEqual(get_chit_payment_summary(
            self.db, 1, 1, month=11, year=2026,
        )['this_month_collections'], 250)

    def test_monthly_amount_follows_edited_and_deleted_transactions(self):
        self.installment(1, 1, 11)
        self.payment(1, 1, 11, 250)
        payment = self.db.get(PaymentTransaction, 1)
        payment.amount = 400
        self.db.flush()
        summary = get_chit_payment_summary(self.db, 1, 1, month=11, year=2026)
        self.assertEqual(summary['this_month_collections'], 400)
        self.assertEqual(summary['this_month_due'], 600)
        self.db.delete(payment)
        self.db.flush()
        summary = get_chit_payment_summary(self.db, 1, 1, month=11, year=2026)
        self.assertEqual(summary['this_month_collections'], 0)
        self.assertEqual(summary['this_month_due'], 1000)

    def test_payment_month_controls_collections_instead_of_receipt_or_audit_month(self):
        self.installment(1, 1, 11)
        self.installment(2, 1, 12)
        # December selected in the payment form; money received in November.
        self.payment(1, 2, 11, 600)
        # November arrears paid in December, in two transactions.
        self.payment(2, 1, 12, 200)
        self.payment(3, 1, 12, 300)
        for payment in self.db.query(PaymentTransaction).all():
            payment.created_at = real_datetime(2027, 1, 15)
            payment.updated_at = real_datetime(2027, 2, 15)
        self.db.flush()

        november = get_chit_payment_summary(self.db, 1, 1, month=11, year=2026)
        december = get_chit_payment_summary(self.db, 1, 1, month=12, year=2026)
        self.assertEqual(november['this_month_collections'], 500)
        self.assertEqual(november['this_month_due'], 500)
        self.assertEqual(december['this_month_collections'], 600)
        self.assertEqual(december['this_month_due'], 400)
        self.assertEqual(december['total_paid'], 1100)
        self.assertEqual(get_chit_payment_summary(
            self.db, 1, 1, month=1, year=2027,
        )['this_month_collections'], 0)

        payment = self.db.get(PaymentTransaction, 1)
        payment.payment_date = date(2027, 1, 1)
        self.db.flush()
        self.assertEqual(get_chit_payment_summary(
            self.db, 1, 1, month=12, year=2026,
        )['this_month_collections'], 600)

    def test_api_forwards_selected_month_and_validates_reference(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.core.database import get_db
        from app.core.dependencies import get_current_user
        from app.routes.payment_summary import router

        self.installment(1, 1, 10)
        self.installment(2, 1, 11)
        self.payment(1, 1, 11, 250)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, company_id=1)
        with TestClient(app) as client:
            selected = client.get('/chits/1/payment-summary', params={'month': 10, 'year': 2026})
            self.assertEqual(selected.status_code, 200, selected.text)
            self.assertEqual(selected.json()['this_month_collections'], 250)
            self.assertEqual(selected.json()['this_month_due'], 750)
            self.assertEqual(selected.json()['total_remaining'], 750)
            default = client.get('/chits/1/payment-summary')
            self.assertEqual(default.status_code, 200, default.text)
            self.assertEqual(default.json()['this_month_collections'], 0)
            self.assertEqual(default.json()['total_remaining'], 1750)
            self.assertEqual(default.json()['reference_month'], 11)
            self.assertEqual(client.get('/chits/1/payment-summary?month=13&year=2026').status_code, 422)
            self.assertEqual(client.get('/chits/1/payment-summary?month=10').status_code, 400)
            self.assertEqual(client.get('/chits/1/payment-summary?year=2026').status_code, 400)

    def test_empty_chit_and_ownership(self):
        result = get_chit_payment_summary(self.db, 1, 4)
        for key in ('total_due', 'total_paid', 'total_remaining', 'this_month_collections',
                    'this_month_due', 'total_lift_amount', 'others_amount'):
            self.assertEqual(result[key], 0)
        self.expense(1, 4, 75)
        self.assertEqual(get_chit_payment_summary(self.db, 1, 4)['others_amount'], 75)
        self.assertEqual(get_chit_payment_summary(self.db, 2, 1), {'error': 'chit_not_found'})

    def test_december_payment_month_includes_transactions_received_next_year(self):
        self.now.now.return_value = real_datetime(2026, 12, 31, tzinfo=ZoneInfo('Asia/Kolkata'))
        self.installment(1, 1, 12)
        self.payment(1, 1, 12, 200)
        self.db.add(PaymentTransaction(id=2, installment_id=1, amount=100,
                                       payment_date=date(2027, 1, 1), payment_method='cash', created_by=1))
        self.db.flush()
        result = get_chit_payment_summary(self.db, 1, 1)
        self.assertEqual(result['this_month_collections'], 300)
        self.assertEqual(result['this_month_due'], 700)

    @patch('app.services.expenses_service.create_audit_log')
    def test_expenses_can_be_assigned_reassigned_and_cleared(self, audit):
        user = SimpleNamespace(id=1, company_id=1)
        payload = ExpenseCreate(chit_id=1, category='other', amount=250,
                                expense_date=date(2026, 11, 1), payment_method='cash')
        expense = create_expense(self.db, payload, user)
        self.assertEqual(get_chit_payment_summary(self.db, 1, 1)['others_amount'], 250)
        update_expense(self.db, expense.id, ExpenseUpdate(amount=300, reason='Correct amount'), user)
        self.assertEqual(expense.chit_id, 1)
        self.assertEqual(get_chit_payment_summary(self.db, 1, 1)['others_amount'], 300)
        update_expense(self.db, expense.id, ExpenseUpdate(chit_id=2, reason='Correct chit'), user)
        self.assertEqual(get_chit_payment_summary(self.db, 1, 1)['others_amount'], 0)
        self.assertEqual(get_chit_payment_summary(self.db, 1, 2)['others_amount'], 300)
        update_expense(self.db, expense.id, ExpenseUpdate(chit_id=None, reason='General expense'), user)
        self.assertIsNone(expense.chit_id)
        self.assertEqual(get_chit_payment_summary(self.db, 1, 2)['others_amount'], 0)
        update_expense(self.db, expense.id, ExpenseUpdate(chit_id=1, reason='Assign again'), user)
        delete_expense(self.db, expense.id, user)
        self.assertEqual(get_chit_payment_summary(self.db, 1, 1)['others_amount'], 0)

    def test_expense_cannot_be_linked_to_another_company_chit(self):
        user = SimpleNamespace(id=1, company_id=1)
        payload = ExpenseCreate(chit_id=3, category='other', amount=250,
                                expense_date=date(2026, 11, 1), payment_method='cash')
        with self.assertRaises(HTTPException) as error:
            create_expense(self.db, payload, user)
        self.assertEqual(error.exception.status_code, 404)
        self.expense(1, 1, 100)
        with self.assertRaises(HTTPException):
            update_expense(self.db, 1, ExpenseUpdate(chit_id=3, reason='Invalid assignment'), user)
        self.assertEqual(self.db.get(Expense, 1).chit_id, 1)


if __name__ == '__main__':
    unittest.main()
