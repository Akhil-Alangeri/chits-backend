from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_group import ChitGroup
from app.models.admin.company import Company
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.payment_transaction import PaymentTransaction
from app.models.admin.chitlift import ChitLift
from app.models.admin.chit_months import ChitMonth


# ============================================================
# EXISTING FUNCTION
# ============================================================

def get_customer_membership_companies(
    db: Session,
    mobile: str,
):
    companies = (
        db.query(
            Company.id.label("company_id"),
            Company.company_name,
            Company.logo_url,
            CustomerProfile.id.label("customer_profile_id"),
            CustomerProfile.customer_code,
        )
        .join(
            CustomerProfile,
            CustomerProfile.company_id == Company.id,
        )
        .join(
            ChitMember,
            ChitMember.customer_profile_id == CustomerProfile.id,
        )
        .filter(
            CustomerProfile.mobile == mobile,
            CustomerProfile.status == "active",
            ChitMember.status == "confirmed",
        )
        .distinct()
        .all()
    )

    return companies


# ============================================================
# EXISTING FUNCTION
# ============================================================

def get_customer_company_chits(
    db: Session,
    mobile: str,
    company_id: int,
):
    customer_company = (
        db.query(
            Company.id.label("company_id"),
            Company.company_name,
            Company.logo_url,
            CustomerProfile.id.label("customer_profile_id"),
            CustomerProfile.customer_code,
        )
        .join(
            CustomerProfile,
            CustomerProfile.company_id == Company.id,
        )
        .join(
            ChitMember,
            ChitMember.customer_profile_id == CustomerProfile.id,
        )
        .filter(
            Company.id == company_id,
            CustomerProfile.mobile == mobile,
            CustomerProfile.status == "active",
            ChitMember.status == "confirmed",
        )
        .first()
    )

    if not customer_company:
        return None

    active_chits = (
        db.query(ChitGroup.id)
        .filter(
            ChitGroup.company_id == company_id,
            ChitGroup.status == "active",
        )
        .count()
    )

    active_members = (
        db.query(ChitMember.id)
        .join(
            ChitGroup,
            ChitGroup.id == ChitMember.chit_id,
        )
        .filter(
            ChitGroup.company_id == company_id,
            ChitGroup.status == "active",
            ChitMember.status.in_(["confirmed", "active"]),
        )
        .count()
    )

    customer_chits = (
        db.query(
            ChitMember,
            CustomerProfile,
            ChitGroup,
        )
        .join(
            CustomerProfile,
            CustomerProfile.id == ChitMember.customer_profile_id,
        )
        .join(
            ChitGroup,
            ChitGroup.id == ChitMember.chit_id,
        )
        .filter(
            CustomerProfile.mobile == mobile,
            CustomerProfile.company_id == company_id,
            CustomerProfile.status == "active",
            ChitMember.status == "confirmed",
            ChitGroup.company_id == company_id,
        )
        .all()
    )

    return {
        "company": customer_company,
        "active_chits": active_chits,
        "active_members": active_members,
        "chits": customer_chits,
    }


# ============================================================
# NEW:
# CUSTOMER CHIT DETAILS FOR ONE SPECIFIC SLOT
# ============================================================

def get_customer_chit_details(
    db: Session,
    mobile: str,
    chit_member_id: int,
):
    """
    Fetch complete details for ONE specific customer slot.

    IMPORTANT:
    chit_member_id is the slot identity.

    Same customer can have:
        Slot 1 -> chit_member_id = 85
        Slot 2 -> chit_member_id = 96

    These are intentionally fetched separately.
    """

    # --------------------------------------------------------
    # 1. FETCH EXACT CUSTOMER SLOT
    # --------------------------------------------------------

    member_data = (
    db.query(
        ChitMember,
        CustomerProfile,
        ChitGroup,
    )
    .join(
        CustomerProfile,
        CustomerProfile.id == ChitMember.customer_profile_id,
    )
    .join(
        ChitGroup,
        ChitGroup.id == ChitMember.chit_id,
    )
    .filter(
        ChitMember.id == chit_member_id,

        # Logged-in customer's mobile
        CustomerProfile.mobile == mobile,

        # Customer profile must be active
        CustomerProfile.status == "active",

        # Customer must have confirmed membership
        ChitMember.status == "confirmed",
    )
    .first()
)
    if not member_data:
        return None

    member, customer, chit = member_data

    # --------------------------------------------------------
    # 2. FETCH ALL INSTALLMENTS FOR THIS SLOT ONLY
    # --------------------------------------------------------

    installments = (
        db.query(ChitInstallment)
        .filter(
            ChitInstallment.chit_member_id == member.id,
        )
        .order_by(
            ChitInstallment.installment_number.asc()
        )
        .all()
    )

    # --------------------------------------------------------
    # 3. FETCH ALL PAYMENTS FOR THESE INSTALLMENTS
    # --------------------------------------------------------

    installment_ids = [
        installment.id
        for installment in installments
    ]

    payments_by_installment: dict[int, list[PaymentTransaction]] = {}

    if installment_ids:
        payments = (
            db.query(PaymentTransaction)
            .filter(
                PaymentTransaction.installment_id.in_(
                    installment_ids
                )
            )
            .order_by(
                PaymentTransaction.payment_date.asc(),
                PaymentTransaction.id.asc(),
            )
            .all()
        )

        for payment in payments:
            payments_by_installment.setdefault(
                payment.installment_id,
                [],
            ).append(payment)

    # --------------------------------------------------------
    # 4. BUILD MONTHLY PAYMENT DETAILS
    # --------------------------------------------------------

    monthly_payments = []

    total_due_amount = Decimal("0.00")
    total_paid_amount = Decimal("0.00")

    paid_installments = 0
    due_installments = 0

    for installment in installments:

        installment_due = Decimal(
            str(installment.due_amount or 0)
        )

        installment_payments = payments_by_installment.get(
            installment.id,
            [],
        )

        paid_amount = sum(
            (
                Decimal(str(payment.amount or 0))
                for payment in installment_payments
            ),
            Decimal("0.00"),
        )

        balance_amount = max(
            installment_due - paid_amount,
            Decimal("0.00"),
        )

        total_due_amount += installment_due
        total_paid_amount += paid_amount

        # ----------------------------------------------------
        # DERIVE PAYMENT STATUS FROM ACTUAL PAYMENT DATA
        # ----------------------------------------------------

        if paid_amount >= installment_due:
            payment_status = "paid"
            paid_installments += 1

        elif paid_amount > Decimal("0.00"):
            payment_status = "partial"
            due_installments += 1

        else:
            payment_status = "pending"
            due_installments += 1

        # ----------------------------------------------------
        # PAYMENT TRANSACTIONS
        #
        # IMPORTANT:
        # payment_date is the actual paid date.
        #
        # created_at is NOT used here.
        # ----------------------------------------------------

        payment_list = []

        for payment in installment_payments:

            payment_list.append(
                {
                    "payment_id": payment.id,
                    "amount": Decimal(
                        str(payment.amount or 0)
                    ),
                    "payment_date": payment.payment_date,
                    "payment_method": payment.payment_method,
                    "reference_number": (
                        payment.reference_number
                    ),
                }
            )

        monthly_payments.append(
            {
                "installment_id": installment.id,
                "installment_number": int(
                    installment.installment_number
                ),
                "due_date": installment.due_date,
                "due_amount": installment_due,
                "paid_amount": paid_amount,
                "balance_amount": balance_amount,
                "status": payment_status,
                "payments": payment_list,
            }
        )

    # --------------------------------------------------------
    # 5. PAYMENT SUMMARY
    # --------------------------------------------------------

    total_pending_amount = max(
        total_due_amount - total_paid_amount,
        Decimal("0.00"),
    )

    payment_summary = {
        "total_installments": len(installments),
        "paid_installments": paid_installments,
        "due_installments": due_installments,
        "total_due_amount": total_due_amount,
        "total_paid_amount": total_paid_amount,
        "total_pending_amount": total_pending_amount,
    }

    # --------------------------------------------------------
    # 6. FETCH LIFT FOR THIS SPECIFIC SLOT
    # --------------------------------------------------------

    lift = (
        db.query(
            ChitLift,
            ChitMonth,
        )
        .outerjoin(
            ChitMonth,
            ChitMonth.id == ChitLift.chit_month_id,
        )
        .filter(
            ChitLift.chit_member_id == member.id,
        )
        .first()
    )

    lift_details = None

    if lift:
        chit_lift, chit_month = lift

        lift_details = {
            "lift_id": chit_lift.id,

            "month_number": (
                chit_month.month_number
                if chit_month
                else 0
            ),

            "month_date": (
                chit_month.month_date
                if chit_month
                else chit_lift.lift_date
            ),

            "lift_date": chit_lift.lift_date,

            "monthly_lift_amount": (
                Decimal(
                    str(
                        chit_month.monthly_lift_amount
                        if chit_month
                        else 0
                    )
                )
            ),

            "discount_amount": Decimal(
                str(
                    chit_lift.discount_amount or 0
                )
            ),

            "lifted_amount": Decimal(
                str(
                    chit_lift.lifted_amount or 0
                )
            ),

            "payout_status": chit_lift.payout_status,

            "payout_date": chit_lift.payout_date,

            "cash_amount": Decimal(
                str(
                    chit_lift.cash_amount or 0
                )
            ),

            "upi_amount": Decimal(
                str(
                    chit_lift.upi_amount or 0
                )
            ),
        }

    # --------------------------------------------------------
    # 7. BASIC CHIT RESPONSE
    #
    # This represents ONLY this member/slot.
    # --------------------------------------------------------

    chit_response = {
        "chit_member_id": member.id,
        "chit_id": chit.id,
        "chit_name": chit.name,
        "chit_code": chit.code,

        "customer_profile_id": customer.id,
        "customer_code": customer.customer_code,

        "member_number": member.member_number,
        "slot_number": member.slot_number,
        "member_name": member.member_name,
        "member_status": member.status,

        "chit_value": Decimal(
            str(chit.chit_value)
        ),

        "monthly_emi": Decimal(
            str(chit.monthly_emi)
        ),

        "duration_months": chit.duration_months,

        "start_date": chit.start_date,
    }

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    return {
        "chit": chit_response,
        "payment_summary": payment_summary,
        "monthly_payments": monthly_payments,
        "lift_details": lift_details,
    }