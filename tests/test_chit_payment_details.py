"""Payments table returns one month's installments, never the full chit term."""
import unittest
from datetime import date
from types import SimpleNamespace

import app.models
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.dependencies import get_current_user
from app.models.admin.company import Company
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.payment_transaction import PaymentTransaction
from app.routes.chit_installment import router


@compiles(BigInteger, 'sqlite')
def sqlite_bigint(element, compiler, **kw):
    return 'INTEGER'


class ChitPaymentDetailsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            'sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = SimpleNamespace(id=1, company_id=1)
        for identifier in (1, 2):
            self.db.add(Company(id=identifier, company_name=str(identifier), status='active'))
        for identifier, company_id in ((23, 1), (24, 1), (25, 2)):
            self.db.add(ChitGroup(
                id=identifier, company_id=company_id, name=f'Chit {identifier}', code=str(identifier),
                chit_value=500000, monthly_emi=13500, duration_months=30, max_members=30,
                start_date=date(2026, 11, 1), status='active',
            ))
        for identifier, company_id in ((1, 1), (2, 1), (3, 1), (4, 2)):
            self.db.add(CustomerProfile(
                id=identifier, company_id=company_id, customer_code=str(identifier),
                display_name=f'Customer {identifier}', mobile=str(identifier),
            ))
        for identifier, profile_id, chit_id, status in (
            (121, 1, 23, 'confirmed'), (130, 2, 23, 'active'),
            (131, 1, 23, 'cancelled'), (132, 3, 24, 'confirmed'), (133, 4, 25, 'confirmed'),
        ):
            self.db.add(ChitMember(
                id=identifier, customer_profile_id=profile_id, chit_id=chit_id,
                member_number=identifier, slot_number=1, member_name=f'Member {identifier}',
                status=status,
            ))
        # Reproduce two members with 30 installments each (Rs 810,000 for the full term).
        for member_index, member_id in enumerate((121, 130)):
            for offset in range(30):
                year, month_index = divmod(2026 * 12 + 10 + offset, 12)
                self.db.add(ChitInstallment(
                    id=1000 + member_index * 30 + offset, chit_member_id=member_id,
                    installment_number=offset + 1, due_date=date(year, month_index + 1, 1),
                    due_amount=13500,
                ))
        for identifier, member_id in ((2000, 131), (2001, 132), (2002, 133)):
            self.db.add(ChitInstallment(
                id=identifier, chit_member_id=member_id, installment_number=1,
                due_date=date(2026, 11, 1), due_amount=999999,
            ))
        for identifier, installment_id, amount in ((1, 1000, 13500), (2, 1001, 13000)):
            self.db.add(PaymentTransaction(
                id=identifier, installment_id=installment_id, amount=amount,
                payment_date=date(2026, 11, 5), payment_method='cash', created_by=1,
            ))
        self.db.commit()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def fetch(self, month=11, year=2026, **params):
        response = self.client.get('/chits/23/payments', params={
            'month': month, 'year': year, **params,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_two_members_return_two_monthly_records_instead_of_sixty(self):
        result = self.fetch()
        self.assertEqual(len(result['items']), 2)
        self.assertEqual({item['due_date'] for item in result['items']}, {'2026-11-01'})
        self.assertEqual({item['member_id'] for item in result['items']}, {121, 130})
        self.assertEqual(result['summary'], {
            'total_months': 1, 'total_members': 2, 'total_records': 2,
            'total_due': 27000, 'total_paid': 13500, 'total_remaining': 13500,
            'paid_members': 1, 'partial_members': 0, 'due_members': 1,
        })

    def test_december_and_same_month_in_another_year_are_scoped_correctly(self):
        december = self.fetch(month=12)
        self.assertEqual({item['due_date'] for item in december['items']}, {'2026-12-01'})
        self.assertEqual(december['summary']['total_paid'], 13000)
        self.assertEqual(december['summary']['total_remaining'], 14000)
        self.assertEqual(december['summary']['partial_members'], 1)
        following_year = self.fetch(year=2027)
        self.assertEqual({item['due_date'] for item in following_year['items']}, {'2027-11-01'})
        self.assertEqual(following_year['summary']['total_paid'], 0)

    def test_status_filter_applies_only_to_the_selected_month(self):
        for status, expected_ids in (('paid', [121]), ('due', [130]), ('partial', [])):
            with self.subTest(status=status):
                result = self.fetch(status=status)
                self.assertEqual([item['member_id'] for item in result['items']], expected_ids)
                self.assertEqual(result['summary']['total_records'], len(expected_ids))

    def test_unfiltered_requests_and_invalid_filters_are_rejected(self):
        for params in ({}, {'month': 11}, {'year': 2026},
                       {'month': 0, 'year': 2026}, {'month': 13, 'year': 2026},
                       {'month': 11, 'year': 1999}, {'month': 11, 'year': 2101}):
            with self.subTest(params=params):
                response = self.client.get('/chits/23/payments', params=params)
                self.assertEqual(response.status_code, 422, response.text)
        response = self.client.get('/chits/23/payments', params={
            'month': 11, 'year': 2026, 'status': 'invalid',
        })
        self.assertEqual(response.status_code, 400)

    def test_empty_month_has_consistent_zero_counts(self):
        result = self.fetch(month=10)
        self.assertEqual(result['items'], [])
        self.assertTrue(all(value == 0 for value in result['summary'].values()))
        self.assertIn('total_records', result['summary'])

    def test_record_count_and_member_count_have_distinct_meanings(self):
        self.db.add(ChitInstallment(
            id=2010, chit_member_id=121, installment_number=31,
            due_date=date(2026, 11, 20), due_amount=500,
        ))
        self.db.commit()
        summary = self.fetch()['summary']
        self.assertEqual(summary['total_records'], 3)
        self.assertEqual(summary['total_members'], 2)
        self.assertEqual(summary['total_months'], 1)

    def test_chit_ownership_is_enforced(self):
        self.user.company_id = 2
        response = self.client.get('/chits/23/payments', params={'month': 11, 'year': 2026})
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
