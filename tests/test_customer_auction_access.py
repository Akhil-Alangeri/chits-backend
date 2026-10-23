"""Auction access follows the same cross-company mobile identity as chit details."""
import unittest

import app.models
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.database import Base
from app.models.admin.company import Company
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.routes.customer.auctions_list_router import get_customer_auction_winners


class CustomerAuctionAccessTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        for company_id in (1, 2):
            self.db.add(Company(id=company_id, company_name=str(company_id), status='active'))
            self.db.add(ChitGroup(id=company_id, company_id=company_id, name='Savings', code=str(company_id),
                                  chit_value=100000, monthly_emi=5000, duration_months=20, max_members=20))
        for profile_id, company_id, mobile, status in [
            (1, 1, '9999999999', 'active'),
            (2, 2, '9999999999', 'active'),
            (3, 2, '8888888888', 'active'),
            (4, 2, '9999999999', 'inactive'),
        ]:
            self.db.add(CustomerProfile(id=profile_id, company_id=company_id, customer_code=str(profile_id),
                                        display_name='Customer', mobile=mobile, status=status))
        for member_id, profile_id, chit_id, status in [
            (96, 1, 1, 'confirmed'), (97, 2, 2, 'confirmed'),
            (98, 3, 2, 'confirmed'), (99, 4, 2, 'confirmed'),
            (100, 2, 1, 'confirmed'), (101, 2, 2, 'cancelled'),
        ]:
            self.db.add(ChitMember(id=member_id, customer_profile_id=profile_id, chit_id=chit_id,
                                   member_number=member_id, slot_number=member_id, member_name='Customer', status=status))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def fetch(self, member_id):
        return get_customer_auction_winners(member_id, self.db,
            {'customer_profile_id': 1, 'mobile': '9999999999'})

    def test_own_memberships_in_both_companies_are_accessible(self):
        for member_id in (96, 97):
            with self.subTest(member_id=member_id):
                result = self.fetch(member_id)
                self.assertTrue(result['success'])
                self.assertEqual(result['auction_winners'], [])

    def test_unrelated_inactive_mismatched_cancelled_and_missing_memberships_are_rejected(self):
        for member_id in (98, 99, 100, 101, 999):
            with self.subTest(member_id=member_id):
                with self.assertRaises(HTTPException) as context:
                    self.fetch(member_id)
                self.assertEqual(context.exception.status_code, 404)
