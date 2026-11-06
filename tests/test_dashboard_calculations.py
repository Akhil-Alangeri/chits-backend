"""Financial regressions run against an isolated database, never company data."""
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import Base
from app.models.admin.loan import Loan
from app.models.admin.loan_transaction import LoanTransaction
from app.models.admin.expenses import Expense
from app.models.admin.chitlift import ChitLift
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.payment_transaction import PaymentTransaction
from app.models.admin.audit_log import AuditLog
from app.services.dashboard_service import get_dashboard, get_expense_summary
from app.services.loan_services import cancel_loan


@compiles(BigInteger, 'sqlite')
def sqlite_bigint(element, compiler, **kw):
    return 'INTEGER'


class DashboardCalculationsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.features = patch(
            'app.services.dashboard_service.get_company_effective_features',
            return_value={'loans': True, 'expenses': True},
        )
        self.features.start()

    def tearDown(self):
        self.features.stop()
        self.db.close()
        self.engine.dispose()

    def loan(self, identifier, direction, company=1):
        self.db.add(Loan(id=identifier, company_id=company, person_name='Test',
                         direction=direction, principal_amount=1000,
                         start_date=date.today()))
        self.db.flush()

    def transaction(self, identifier, loan, kind, cash, interest=0, discount=0, company=1):
        self.db.add(LoanTransaction(id=identifier, company_id=company, loan_id=loan,
                                   transaction_date=date.today(), transaction_type=kind,
                                   cash_amount=cash, upi_amount=0,
                                   interest_amount=interest, discount=discount))
        self.db.flush()

    def test_balance_includes_taken_loans_and_actual_discounted_receipts(self):
        self.loan(1, 'given')
        self.loan(2, 'taken')
        self.loan(3, 'given', company=2)
        self.transaction(1, 1, 'disbursement', 1000)
        self.transaction(2, 2, 'disbursement', 1000)
        self.transaction(3, 1, 'interest_payment', Decimal('80.25'), interest=100, discount=Decimal('19.75'))
        self.transaction(4, 2, 'interest_payment', 50, interest=50)
        self.transaction(5, 3, 'interest_payment', 999, interest=999, company=2)
        result = get_dashboard(self.db, 1)
        self.assertEqual(result['balance']['loan_repayments'], Decimal('80.25'))
        self.assertEqual(result['balance']['available_balance'], Decimal('30.25'))
        self.assertEqual(result['balance']['available_balance'], result['cash_bank']['total'])
        self.assertEqual(result['loans']['repayment_cash'], Decimal('80.25'))

    def test_expense_categories_match_selected_month_and_company(self):
        for identifier, company, month, amount in [(1, 1, 1, 100), (2, 1, 2, 250), (3, 2, 1, 999)]:
            self.db.add(Expense(id=identifier, company_id=company, created_by=1,
                                category='Rent', amount=amount,
                                expense_date=date(date.today().year, month, 1), payment_method='cash'))
        self.db.flush()
        result = get_expense_summary(self.db, 1, date.today().year, 1)
        self.assertEqual(result['total'], 350)
        self.assertEqual(result['this_month'], 100)
        self.assertEqual(result['categories'], [{'category': 'Rent', 'amount': Decimal('100')}])

    def test_only_paid_chit_payouts_reduce_available_balance(self):
        for identifier, company, status, cash, upi in [
            (1, 1, 'paid', 200, 300),
            (2, 1, 'pending', 400, 500),
            (3, 2, 'paid', 600, 700),
        ]:
            self.db.add(ChitLift(
                id=identifier, company_id=company, chit_id=identifier,
                chit_member_id=identifier, customer_name='Test', member_number='1',
                lift_date=date.today(), lifted_amount=cash + upi,
                payout_status=status, cash_amount=cash, upi_amount=upi,
            ))
        self.db.flush()
        result = get_dashboard(self.db, 1)
        self.assertEqual(result['cash_bank'], {'cash': Decimal('-200'), 'bank': Decimal('-300'), 'total': Decimal('-500')})
        self.assertEqual(result['balance']['available_balance'], Decimal('-500'))

    def seed_collections(self):
        self.db.add(ChitGroup(id=1, company_id=1, name='Test', code='T1',
                              chit_value=10000, monthly_emi=1000,
                              duration_months=10, max_members=10, status='active'))
        self.db.flush()
        self.db.add(ChitMember(id=1, chit_id=1, customer_profile_id=1,
                               member_number=1, slot_number=1, member_name='Test', status='active'))
        self.db.flush()
        self.db.add(ChitInstallment(id=1, chit_member_id=1, installment_number=1,
                                    due_date=date.today(), due_amount=1000))
        self.db.flush()
        for identifier, method, amount in [
            (1, ' Cheque ', Decimal('100.25')),
            (2, 'bank_transfer', Decimal('200.50')),
            (3, 'upi', Decimal('300.75')),
            (4, 'cash', Decimal('50.25')),
        ]:
            self.db.add(PaymentTransaction(id=identifier, installment_id=1, created_by=1,
                                           payment_date=date.today(),
                                           payment_method=method, amount=amount))
        self.db.flush()

    def test_cheque_and_bank_transfer_are_bank_collections(self):
        self.seed_collections()
        result = get_dashboard(self.db, 1)
        self.assertEqual(result['cash_bank']['bank'], Decimal('601.50'))
        self.assertEqual(result['cash_bank']['cash'], Decimal('50.25'))
        self.assertEqual(result['balance']['available_balance'], Decimal('651.75'))
        self.assertEqual(result['cash']['upi_collected_total'], Decimal('601.50'))
        self.assertEqual(result['cash']['bank_upi_closing_balance'], Decimal('601.50'))

    def test_cancel_route_deletes_2000_cash_loan_and_restores_balance_once(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from types import SimpleNamespace
        from app.core.database import get_db
        from app.core.dependencies import get_current_user
        from app.routes.loan import router

        self.loan(1, 'given')
        self.db.get(Loan, 1).principal_amount = 2000
        self.transaction(1, 1, 'disbursement', 2000)
        self.db.commit()
        before = get_dashboard(self.db, 1)
        self.assertEqual(before['cash_bank']['cash'], Decimal('-2000'))
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(company_id=1, id=None)
        for dependency in router.dependencies:
            app.dependency_overrides[dependency.dependency] = lambda: None
        with TestClient(app) as client:
            response = client.patch('/loans/1/cancel')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['loan_id'], 1)
            self.assertEqual(client.patch('/loans/1/cancel').status_code, 404)
        self.assertIsNone(self.db.get(Loan, 1))
        self.assertEqual(self.db.query(LoanTransaction).count(), 0)
        after = get_dashboard(self.db, 1)
        self.assertEqual(after['cash_bank'], {'cash': 0, 'bank': 0, 'total': 0})
        self.assertEqual(after['balance']['available_balance'], 0)
        self.assertEqual(after['loans']['total_count'], 0)
        self.assertEqual(after['balance']['loan_given'], 0)
        audit = self.db.query(AuditLog).one()
        self.assertEqual(audit.action, 'DELETE')
        self.assertEqual(audit.entity_type, 'Loan')
        self.assertEqual(audit.old_values['transactions'][0]['cash_amount'], 2000)

    def test_cancellation_reverses_split_disbursements_and_all_repayments(self):
        for direction in ('given', 'taken'):
            with self.subTest(direction=direction):
                self.loan(1, direction)
                self.transaction(1, 1, 'disbursement', Decimal('600.25'))
                self.db.get(LoanTransaction, 1).upi_amount = Decimal('399.75')
                self.transaction(2, 1, 'principal_repayment', Decimal('100.50'))
                self.db.get(LoanTransaction, 2).principal_amount = Decimal('200.75')
                self.db.get(LoanTransaction, 2).upi_amount = Decimal('100.25')
                self.transaction(3, 1, 'interest_payment', Decimal('40.25'), interest=50, discount=Decimal('9.75'))
                self.db.commit()
                before = get_dashboard(self.db, 1)
                sign = -1 if direction == 'given' else 1
                self.assertEqual(before['cash_bank']['cash'], sign * Decimal('459.50'))
                self.assertEqual(before['cash_bank']['bank'], sign * Decimal('299.50'))
                cancel_loan(self.db, 1, 1)
                after = get_dashboard(self.db, 1)
                self.assertEqual(after['cash_bank']['total'], 0)
                self.assertEqual(after['balance']['loan_repayments'], 0)
                self.assertEqual(after['loans']['given_outstanding'], 0)
                self.assertEqual(after['loans']['taken_outstanding'], 0)

    def test_cancellation_is_company_scoped_and_allows_closed_loans(self):
        self.loan(1, 'given', company=2)
        self.transaction(1, 1, 'disbursement', 1000, company=2)
        self.db.commit()
        self.assertEqual(cancel_loan(self.db, 1, 1)['error'], 'loan_not_found')
        self.assertIsNotNone(self.db.get(Loan, 1))
        self.assertEqual(self.db.query(LoanTransaction).count(), 1)
        self.db.get(Loan, 1).status = 'closed'
        self.db.commit()
        self.assertIn('message', cancel_loan(self.db, 2, 1))
        self.assertIsNone(self.db.get(Loan, 1))

    def test_cancellation_audit_failure_rolls_back_loan_and_transactions(self):
        self.loan(1, 'given')
        self.transaction(1, 1, 'disbursement', 1000)
        self.db.commit()
        def fail_after_flush(**kwargs):
            self.db.flush()
            raise RuntimeError('Audit failed')

        with patch('app.services.loan_services.create_audit_log', side_effect=fail_after_flush):
            with self.assertRaises(RuntimeError):
                cancel_loan(self.db, 1, 1)
        self.assertIsNotNone(self.db.get(Loan, 1))
        self.assertEqual(self.db.query(LoanTransaction).count(), 1)
        self.assertEqual(get_dashboard(self.db, 1)['cash_bank']['cash'], -1000)

    def test_undisbursed_and_legacy_cancelled_loans_do_not_change_cash_flow(self):
        self.loan(1, 'given')
        self.loan(2, 'given')
        self.db.get(Loan, 2).status = 'cancelled'
        self.transaction(1, 2, 'disbursement', 1000)
        self.transaction(2, 2, 'principal_repayment', 100)
        result = get_dashboard(self.db, 1)
        self.assertEqual(result['loans']['total_count'], 1)
        self.assertEqual(result['loans']['given_amount'], 1000)
        self.assertEqual(result['balance']['loan_given'], 0)
        self.assertEqual(result['balance']['loan_repayments'], 0)
        self.assertEqual(result['cash_bank']['total'], 0)

    def test_expense_splits_include_all_bank_methods_and_normalize_spaces(self):
        for identifier, method, amount in [
            (1, ' Cash ', 10),
            (2, ' UPI ', 20),
            (3, ' Bank_Transfer ', 30),
            (4, ' Cheque ', 40),
        ]:
            self.db.add(Expense(id=identifier, company_id=1, created_by=1,
                                category='Rent', amount=amount,
                                expense_date=date.today(), payment_method=method))
        self.db.flush()
        result = get_dashboard(self.db, 1)
        expenses = result['expenses']
        self.assertEqual(expenses['cash'], 10)
        self.assertEqual(expenses['upi'], 90)
        self.assertEqual(expenses['cash'] + expenses['upi'], expenses['total'])
        self.assertEqual(expenses['this_month_cash'] + expenses['this_month_upi'], expenses['this_month'])
        self.assertEqual(result['cash_bank']['total'], -expenses['total'])

    def test_overpayments_are_capped_in_dues_but_fully_counted_as_receipts(self):
        self.seed_collections()
        self.db.get(ChitInstallment, 1).due_amount = 100
        self.db.flush()
        result = get_dashboard(self.db, 1)
        self.assertEqual(result['overview']['total_paid'], 100)
        self.assertEqual(result['overview']['total_outstanding'], 0)
        self.assertEqual(result['balance']['collections'], Decimal('651.75'))
        self.assertEqual(result['overview']['collection_rate'], 100)
        self.db.get(ChitGroup, 1).status = 'closed'
        self.db.flush()
        result = get_dashboard(self.db, 1)
        self.assertEqual(result['cash']['cash_collected_total'], Decimal('50.25'))
        self.assertEqual(result['cash']['upi_collected_total'], Decimal('601.50'))
        self.assertEqual(result['balance']['collections'], result['cash_bank']['total'])

    def test_cancellation_preserves_other_collections_expenses_and_company_balances(self):
        self.seed_collections()
        self.db.add(Expense(id=1, company_id=1, created_by=1, category='Rent',
                            amount=20, expense_date=date.today(), payment_method='cash'))
        self.loan(2, 'taken', company=2)
        self.transaction(2, 2, 'disbursement', 9000, company=2)
        baseline = get_dashboard(self.db, 1)['cash_bank']
        other_company = get_dashboard(self.db, 2)['cash_bank']
        self.loan(1, 'given')
        self.transaction(1, 1, 'disbursement', 1000)
        self.db.commit()
        cancel_loan(self.db, 1, 1)
        self.assertEqual(get_dashboard(self.db, 1)['cash_bank'], baseline)
        self.assertEqual(get_dashboard(self.db, 2)['cash_bank'], other_company)
        # An undisbursed loan can be cancelled without adding fictitious money.
        self.loan(3, 'given')
        self.db.commit()
        cancel_loan(self.db, 1, 3)
        self.assertEqual(get_dashboard(self.db, 1)['cash_bank'], baseline)

    def test_dues_payment_status_and_monthly_chart_reconcile_per_installment(self):
        from datetime import timedelta

        self.seed_collections()
        yesterday = date.today() - timedelta(days=1)
        self.db.get(ChitInstallment, 1).due_date = yesterday
        self.db.add(ChitInstallment(id=2, chit_member_id=1, installment_number=2,
                                    due_date=yesterday, due_amount=200))
        self.db.flush()
        self.db.add(PaymentTransaction(id=5, installment_id=2, created_by=1,
                                       payment_date=date.today(), payment_method='cash', amount=300))
        self.db.flush()
        result = get_dashboard(self.db, 1)
        self.assertEqual(result['overview']['total_due'], 1200)
        self.assertEqual(result['overview']['total_paid'], Decimal('851.75'))
        self.assertEqual(result['overview']['total_outstanding'], Decimal('348.25'))
        self.assertEqual(result['dues']['overdue_amount'], Decimal('348.25'))
        self.assertEqual(result['dues']['overdue_count'], 1)
        self.assertEqual(result['payment_status'], {'total': 2, 'paid': 1, 'partial': 1, 'pending': 0})
        self.assertEqual(result['today_collection']['total'], Decimal('951.75'))
        self.assertEqual(result['this_month_collection']['total'], Decimal('951.75'))
        self.assertEqual(sum(result['today_collection'][key] for key in
                             ('cash', 'upi', 'bank_transfer', 'cheque', 'other')),
                         result['today_collection']['total'])
        chart = get_dashboard(self.db, 1, year=yesterday.year)['monthly_chart'][yesterday.month - 1]
        self.assertEqual(chart['collection'], Decimal('851.75'))
        self.assertEqual(chart['due'], Decimal('348.25'))
        self.assertEqual(chart['collection'] + chart['due'], 1200)
        self.assertEqual(result['chit_wise'][0]['outstanding'], Decimal('348.25'))

    def assert_closing_balances(self, response, cash, bank):
        self.assertEqual(response['cash_bank']['cash'], cash)
        self.assertEqual(response['cash_bank']['bank'], bank)
        self.assertEqual(response['cash_bank']['total'], cash + bank)
        self.assertEqual(response['cash']['cash_closing_balance'], cash)
        self.assertEqual(response['cash']['bank_upi_closing_balance'], bank)
        self.assertEqual(response['cash']['total_cash_bank_balance'], cash + bank)
        self.assertEqual(response['balance']['available_balance'], cash + bank)

    def test_dashboard_api_closing_balances_before_and_after_cancel(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from types import SimpleNamespace
        from app.core.database import get_db
        from app.core.dependencies import get_current_user
        from app.routes.loan import router as loan_router
        from app.routes.dashboard_router import router as dashboard_router

        self.seed_collections()
        self.db.add_all([
            PaymentTransaction(id=10, installment_id=1, created_by=1,
                               payment_date=date.today(), payment_method='cash', amount=10000),
            PaymentTransaction(id=11, installment_id=1, created_by=1,
                               payment_date=date.today(), payment_method='upi', amount=20000),
        ])
        self.db.commit()
        app = FastAPI()
        app.include_router(loan_router)
        app.include_router(dashboard_router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(company_id=1, id=None)
        for dependency in loan_router.dependencies:
            app.dependency_overrides[dependency.dependency] = lambda: None
        cash_start, bank_start = Decimal('10050.25'), Decimal('20601.50')
        with TestClient(app) as client:
            for direction, cash, bank in [
                ('given', Decimal('2000'), Decimal('0')),
                ('given', Decimal('0'), Decimal('2000')),
                ('given', Decimal('800.25'), Decimal('1199.75')),
                ('taken', Decimal('800.25'), Decimal('1199.75')),
            ]:
                with self.subTest(direction=direction, cash=cash, bank=bank):
                    self.loan(1, direction)
                    self.db.get(Loan, 1).principal_amount = cash + bank
                    self.transaction(1, 1, 'disbursement', cash)
                    self.db.get(LoanTransaction, 1).upi_amount = bank
                    self.db.commit()
                    sign = -1 if direction == 'given' else 1
                    before = client.get('/dashboard')
                    self.assertEqual(before.status_code, 200, before.text)
                    self.assert_closing_balances(before.json(), cash_start + sign * cash, bank_start + sign * bank)
                    cancelled = client.patch('/loans/1/cancel')
                    self.assertEqual(cancelled.status_code, 200, cancelled.text)
                    after = client.get('/dashboard')
                    self.assertEqual(after.status_code, 200, after.text)
                    self.assert_closing_balances(after.json(), cash_start, bank_start)
                    filtered = client.get(f'/dashboard?year={date.today().year}&expense_month=1')
                    self.assert_closing_balances(filtered.json(), cash_start, bank_start)

    def test_closing_balances_retain_historical_movements_when_features_disabled(self):
        self.seed_collections()
        self.loan(1, 'given')
        self.transaction(1, 1, 'disbursement', 20)
        self.db.get(LoanTransaction, 1).upi_amount = 30
        self.loan(2, 'taken')
        self.transaction(2, 2, 'disbursement', 100)
        self.db.add(Expense(id=1, company_id=1, created_by=1, category='Rent', amount=10,
                            expense_date=date.today(), payment_method='cash'))
        self.db.flush()
        expected_cash, expected_bank = Decimal('120.25'), Decimal('571.50')
        self.assert_closing_balances(get_dashboard(self.db, 1), expected_cash, expected_bank)
        with patch('app.services.dashboard_service.get_company_effective_features',
                   return_value={'loans': False, 'expenses': False}):
            result = get_dashboard(self.db, 1)
            self.assert_closing_balances(result, expected_cash, expected_bank)
            self.assertEqual(result['loans']['total_count'], 0)
            self.assertEqual(result['expenses']['total'], 0)


if __name__ == '__main__':
    unittest.main()
