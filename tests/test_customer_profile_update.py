"""Profile edits keep customer names consistent across memberships and auctions."""
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import app.models
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.admin.audit_log import AuditLog
from app.models.admin.company import Company
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.chit_months import ChitMonth
from app.models.admin.chitlift import ChitLift
from app.models.admin.payment_transaction import PaymentTransaction
from app.schemas.customer_profile import CustomerProfileUpdate
from app.services.customer_profile_service import get_customer_details, update_customer_profile
from app.services.chit_lift_service import get_chit_lifts
from app.services.customer.auctions_list_service import get_customer_chit_auction_winners
from app.services.customer.customer_receipt_service import get_customer_receipt_data
from app.services.payment_transaction import (
    get_chit_payment_details, get_customer_chit_payment_history, get_member_payment_summary,
)


@compiles(BigInteger, 'sqlite')
def sqlite_bigint(element, compiler, **kw):
    return 'INTEGER'


class CustomerProfileUpdateTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        for identifier in (1, 2):
            self.db.add(Company(id=identifier, company_name=f'Company {identifier}', status='active'))
        for identifier, company_id in ((1, 1), (2, 1), (3, 2), (4, 1)):
            self.db.add(ChitGroup(
                id=identifier, company_id=company_id, name=f'Chit {identifier}', code=str(identifier),
                chit_value=10000, monthly_emi=1000, duration_months=10, max_members=10,
                status='completed' if identifier == 4 else 'active',
            ))
        # Even identical names and mobile numbers must not link different profiles.
        for identifier, company_id in ((1, 1), (2, 1), (3, 2)):
            self.db.add(CustomerProfile(
                id=identifier, company_id=company_id, customer_code=str(identifier),
                display_name='Old Name', mobile='9999999999', status='active',
            ))
        for identifier, profile_id, chit_id, status in (
            (1, 1, 1, 'confirmed'), (2, 1, 1, 'active'), (3, 1, 2, 'completed'),
            (4, 1, 4, 'cancelled'), (5, 2, 1, 'confirmed'), (6, 3, 3, 'confirmed'),
            (7, 1, 3, 'confirmed'),  # Legacy membership with a mismatched company.
        ):
            self.db.add(ChitMember(
                id=identifier, customer_profile_id=profile_id, chit_id=chit_id,
                member_number=identifier, slot_number=identifier, member_name='Old Name',
                status=status,
            ))
        self.db.add(ChitMonth(
            id=1, company_id=1, chit_id=1, month_number=1, month_date=date(2026, 11, 1),
            monthly_emi=1000, monthly_lift_amount=9000,
        ))
        for identifier, member_id, chit_id, company_id in (
            (1, 1, 1, 1), (2, 3, 2, 1), (3, 4, 4, 1),
            (4, 5, 1, 1), (5, 6, 3, 2), (6, 7, 3, 2),
        ):
            self.db.add(ChitLift(
                id=identifier, company_id=company_id, chit_id=chit_id, chit_member_id=member_id,
                customer_name='Old Name', member_number=str(member_id), slot_number=member_id,
                chit_month_id=1 if identifier == 1 else None, lift_date=date(2026, 11, 1),
                lifted_amount=9000, payout_status='paid', cash_amount=9000,
            ))
        self.db.add(ChitInstallment(
            id=1, chit_member_id=1, installment_number=1, due_date=date(2026, 11, 1),
            due_amount=1000, status='partial',
        ))
        self.db.add(PaymentTransaction(
            id=1, installment_id=1, amount=250, payment_date=date(2026, 11, 2),
            payment_method='cash', created_by=1,
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def update(self, name='New Name', **changes):
        payload = {'display_name': name, 'mobile': '9999999999', **changes}
        return update_customer_profile(self.db, 1, 1, CustomerProfileUpdate(**payload))

    def assert_linked_names(self, name):
        for identifier in (1, 2, 3, 4):
            self.assertEqual(self.db.get(ChitMember, identifier).member_name, name)
        for identifier in (1, 2, 3):
            self.assertEqual(self.db.get(ChitLift, identifier).customer_name, name)

    def test_rename_updates_all_slots_and_existing_lifts_without_changing_finances(self):
        # Keep objects loaded to verify the session also observes the bulk updates.
        member = self.db.get(ChitMember, 1)
        lift = self.db.get(ChitLift, 1)
        self.assertEqual(self.update('  New Name  ').display_name, 'New Name')
        self.assert_linked_names('New Name')
        self.assertEqual(member.member_name, 'New Name')
        self.assertEqual(lift.customer_name, 'New Name')
        self.assertEqual((lift.lifted_amount, lift.cash_amount, lift.payout_status),
                         (Decimal('9000'), Decimal('9000'), 'paid'))
        self.assertEqual(self.db.get(PaymentTransaction, 1).amount, Decimal('250'))
        self.assertEqual(self.db.get(ChitInstallment, 1).due_amount, Decimal('1000'))
        self.assertEqual(self.db.get(ChitMember, 4).status, 'cancelled')

    def test_payment_customer_and_auction_responses_show_updated_name(self):
        self.update()
        details = get_customer_details(self.db, 1, 1)
        self.assertTrue(details['active_chits'])
        self.assertTrue(all(row['member_name'] == 'New Name' for row in details['active_chits']))
        payments = get_chit_payment_details(self.db, 1, 1)
        self.assertEqual(payments['items'][0]['member_name'], 'New Name')
        self.assertEqual(payments['items'][0]['paid_amount'], 250)
        self.assertEqual(get_member_payment_summary(self.db, 1, 1, 1)['member_name'], 'New Name')
        lift = next(row for row in get_chit_lifts(self.db, 1, 1) if row.id == 1)
        self.assertEqual(lift.customer_name, 'New Name')
        auctions = get_customer_chit_auction_winners(self.db, '9999999999', 1)
        self.assertEqual(auctions['auction_winners'], [
            {'month_date': 'Nov-2026', 'customer_name': 'New Name'},
        ])
        history = get_customer_chit_payment_history(self.db, 1, 1, 1, 1)
        self.assertEqual(history['member_name'], 'New Name')
        receipt = get_customer_receipt_data(self.db, '9999999999', 1)
        self.assertEqual(receipt['customer']['name'], 'New Name')
        self.assertEqual(receipt['member']['member_name'], 'New Name')

    def test_case_only_name_changes_are_synced(self):
        self.update('OLD NAME')
        self.assert_linked_names('OLD NAME')

    def test_other_profiles_and_company_records_are_unchanged(self):
        self.update()
        for identifier in (2, 3):
            self.assertEqual(self.db.get(CustomerProfile, identifier).display_name, 'Old Name')
        for identifier in (5, 6, 7):
            self.assertEqual(self.db.get(ChitMember, identifier).member_name, 'Old Name')
        for identifier in (4, 5, 6):
            self.assertEqual(self.db.get(ChitLift, identifier).customer_name, 'Old Name')

    def test_saving_unchanged_profile_name_repairs_previously_stale_records(self):
        customer = self.db.get(CustomerProfile, 1)
        customer.display_name = 'New Name'
        self.db.commit()
        self.update(email='updated@example.com', address='Updated address')
        self.assert_linked_names('New Name')
        self.assertEqual(customer.email, 'updated@example.com')
        self.assertEqual(customer.address, 'Updated address')

    def test_missing_or_other_company_profile_is_not_updated(self):
        payload = CustomerProfileUpdate(display_name='New Name', mobile='9999999999')
        for company_id, customer_id in ((2, 1), (1, 999)):
            self.assertIsNone(update_customer_profile(self.db, company_id, customer_id, payload))
        self.assert_linked_names('Old Name')
        self.assertEqual(self.db.query(AuditLog).count(), 0)

    def test_customer_without_memberships_can_still_be_updated(self):
        self.db.add(CustomerProfile(
            id=4, company_id=1, customer_code='4', display_name='Old Name', mobile='8888888888',
        ))
        self.db.commit()
        updated = update_customer_profile(self.db, 1, 4, CustomerProfileUpdate(
            display_name='New Customer', mobile='8888888888',
        ))
        self.assertEqual(updated.display_name, 'New Customer')
        self.assert_linked_names('Old Name')

    def test_audit_keeps_original_name_and_updates_share_one_transaction(self):
        self.update()
        audit = self.db.query(AuditLog).one()
        self.assertEqual(audit.old_values['display_name'], 'Old Name')
        self.assertEqual(audit.new_values['display_name'], 'New Name')
        with patch('app.services.customer_profile_service.create_audit_log',
                   side_effect=RuntimeError('Audit failed')):
            with self.assertRaisesRegex(RuntimeError, 'Audit failed'):
                self.update('Another Name')
        self.db.rollback()
        self.assertEqual(self.db.get(CustomerProfile, 1).display_name, 'New Name')
        self.assert_linked_names('New Name')
        self.assertEqual(audit.old_values['display_name'], 'Old Name')
        self.assertEqual(self.db.query(AuditLog).count(), 1)


if __name__ == '__main__':
    unittest.main()
