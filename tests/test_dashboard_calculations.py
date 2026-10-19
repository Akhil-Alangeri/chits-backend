"""Financial regressions run against an isolated database, never company data."""
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

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
from app.services.dashboard_service import get_dashboard, get_expense_summary


class DashboardCalculationsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
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

    def test_cheque_and_bank_transfer_are_bank_collections(self):
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
        result = get_dashboard(self.db, 1)
        self.assertEqual(result['cash_bank']['bank'], Decimal('601.50'))
        self.assertEqual(result['cash_bank']['cash'], Decimal('50.25'))
        self.assertEqual(result['balance']['available_balance'], Decimal('651.75'))
        self.assertEqual(result['cash']['upi_collected_total'], Decimal('601.50'))
        self.assertEqual(result['cash']['bank_upi_closing_balance'], Decimal('601.50'))


if __name__ == '__main__':
    unittest.main()
