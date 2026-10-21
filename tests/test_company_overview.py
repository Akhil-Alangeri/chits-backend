"""Company overview totals stay isolated across companies and chit groups."""
import unittest
from decimal import Decimal

import app.models
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.database import Base
from app.models.admin.company import Company
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_group import ChitGroup
from app.schemas.company import CompanyOverviewResponse
from app.services.company_service import get_all_companies, get_company_details


class CompanyOverviewTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            Company(id=1, company_name="First", status="active"),
            Company(id=2, company_name="Second", status="inactive"),
            Company(id=3, company_name="Empty", status="active"),
        ])
        self.db.add_all([
            CustomerProfile(id=1, company_id=1, customer_code="A", display_name="A", mobile="1", status="active"),
            CustomerProfile(id=2, company_id=1, customer_code="B", display_name="B", mobile="2", status="inactive"),
            CustomerProfile(id=3, company_id=2, customer_code="C", display_name="C", mobile="3", status="active"),
        ])
        for group_id, company_id, amount in [(1, 1, 100000), (2, 1, 100000), (3, 2, 500000)]:
            self.db.add(ChitGroup(id=group_id, company_id=company_id, name=str(group_id), code=str(group_id),
                                  chit_value=amount, monthly_emi=5000, duration_months=20, max_members=20))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_list_counts_and_each_group_amount(self):
        companies = {c.id: CompanyOverviewResponse.model_validate(c) for c in get_all_companies(self.db)}
        self.assertEqual(companies[1].total_customers_count, 2)
        self.assertEqual(companies[1].active_customers_count, 1)
        self.assertEqual(companies[1].chit_group_amounts, [Decimal("100000"), Decimal("100000")])
        self.assertEqual(companies[2].total_customers_count, 1)
        self.assertEqual(companies[2].chit_group_amounts, [Decimal("500000")])
        self.assertEqual(companies[3].total_customers_count, 0)
        self.assertEqual(companies[3].active_customers_count, 0)
        self.assertEqual(companies[3].chit_group_amounts, [])

    def test_detail_and_missing_company(self):
        company = CompanyOverviewResponse.model_validate(get_company_details(self.db, 1))
        self.assertEqual(company.total_customers_count, 2)
        self.assertEqual(company.active_customers_count, 1)
        self.assertEqual(len(company.chit_group_amounts), 2)
        self.assertIsNone(get_company_details(self.db, 999))
