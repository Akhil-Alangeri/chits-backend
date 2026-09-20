from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.admin.company import Company
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.payment_transaction import PaymentTransaction


def generate_customer_code(
    db: Session,
    company_id: int,
) -> str:

    existing = (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.company_id == company_id
        )
        .all()
    )

    numbers = []

    for customer in existing:

        if not customer.customer_code:
            continue

        try:
            number = int(
                customer.customer_code
                .split("-")[-1]
            )

            numbers.append(number)

        except ValueError:
            continue

    next_number = (
        max(numbers) + 1
        if numbers
        else 1
    )

    return f"CUST-{next_number:03d}"

def create_customer_profile(
    db: Session,
    company_id: int,
    customer_data,
):
    # =====================================================
    # CHECK EXISTING CUSTOMER IN SAME COMPANY
    # =====================================================

    mobile = customer_data.mobile.strip()

    existing = (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.company_id == company_id,
            CustomerProfile.mobile == mobile,
            CustomerProfile.status == "active",
        )
        .first()
    )

    if existing:
        return {
            "error": "customer_mobile_exists",
            "customer": existing,
        }

    # =====================================================
    # VERIFY COMPANY
    # =====================================================


    company = (
        db.query(Company)
        .filter(
            Company.id == company_id
        )
        .first()
    )

    if not company:
        return {
            "error": "company_not_found"
        }

    # =====================================================
    # GENERATE CUSTOMER CODE
    # =====================================================

    customer_code = generate_customer_code(
        db,
        company_id,
    )

    # =====================================================
    # CREATE PROFILE
    # =====================================================

    customer = CustomerProfile(

        company_id=company_id,

        customer_code=customer_code,

        display_name=
            customer_data.display_name.strip(),

        legal_name=
            customer_data.legal_name,

        mobile=
            customer_data.mobile.strip(),

        email=
            customer_data.email,

        address=
            customer_data.address,

        status="active",

    )

    db.add(customer)

    db.commit()

    db.refresh(customer)

    return customer


# GET Cusomers

def get_customer_profiles(
    db: Session,
    company_id: int,
):

    return (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.company_id == company_id
        )
        .order_by(
            CustomerProfile.id.desc()
        )
        .all()
    )
    
    
# GET One Customer
def get_customer_profile(
    db: Session,
    company_id: int,
    customer_id: int,
):

    return (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.id == customer_id,
            CustomerProfile.company_id == company_id,
        )
        .first()
    )
    
    
# Update Customer


def update_customer_profile(
    db: Session,
    company_id: int,
    customer_id: int,
    customer_data,
):

    customer = get_customer_profile(
        db,
        company_id,
        customer_id,
    )

    if not customer:
        return None

    customer.display_name = (
        customer_data.display_name.strip()
    )

    customer.legal_name = (
        customer_data.legal_name
    )

    customer.mobile = (
        customer_data.mobile.strip()
    )

    customer.email = (
        customer_data.email
    )

    customer.address = (
        customer_data.address
    )

    customer.status = (
        customer_data.status
    )

    db.commit()

    db.refresh(customer)

    return customer





# =========================================================
# GET CUSTOMER DETAILS
# =========================================================

# =========================================================
# GET CUSTOMER DETAILS
# =========================================================

def get_customer_details(
    db: Session,
    company_id: int,
    customer_id: int,
):

    # =====================================================
    # GET CUSTOMER
    # =====================================================

    customer = (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.id == customer_id,
            CustomerProfile.company_id == company_id,
        )
        .first()
    )

    if not customer:
        return None


    # =====================================================
    # GET ACTIVE MEMBERSHIPS
    # =====================================================

    memberships = (
        db.query(
            ChitMember,
            ChitGroup,
        )
        .join(
            ChitGroup,
            ChitGroup.id == ChitMember.chit_id,
        )
        .filter(
            ChitMember.customer_profile_id == customer_id,

            ChitGroup.company_id == company_id,

            ChitGroup.status == "active",

            ChitMember.status.in_([
                "confirmed",
                "active",
            ]),
        )
        .order_by(
            ChitGroup.start_date.desc(),
            ChitMember.member_number.asc(),
        )
        .all()
    )


    # =====================================================
    # BUILD ACTIVE CHITS
    # =====================================================

    active_chits = []


    for member, chit in memberships:

        # -------------------------------------------------
        # GET INSTALLMENTS FOR THIS MEMBER
        # -------------------------------------------------

        installments = (
            db.query(ChitInstallment)
            .filter(
                ChitInstallment.chit_member_id
                == member.id,
            )
            .order_by(
                ChitInstallment.installment_number.asc()
            )
            .all()
        )


        # -------------------------------------------------
        # NO INSTALLMENTS
        # -------------------------------------------------

        if not installments:

            active_chits.append({

                "chit_id":
                    chit.id,

                "chit_name":
                    chit.name,

                "chit_code":
                    chit.code,

                "member_id":
                    member.id,

                "member_number":
                    member.member_number,

                "member_name":
                    member.member_name,

                "status":
                    member.status,

                "total_due":
                    0,

                "total_paid":
                    0,

                "remaining_amount":
                    0,

                "total_months":
                    0,

                "paid_months":
                    0,

                "remaining_months":
                    0,
            })

            continue


        # -------------------------------------------------
        # PAYMENT TOTALS
        # -------------------------------------------------

        payment_rows = (
            db.query(
                PaymentTransaction.installment_id,
                func.coalesce(
                    func.sum(
                        PaymentTransaction.amount
                    ),
                    0,
                ).label("paid_amount"),
            )
            .join(
                ChitInstallment,
                ChitInstallment.id
                == PaymentTransaction.installment_id,
            )
            .filter(
                ChitInstallment.chit_member_id
                == member.id,
            )
            .group_by(
                PaymentTransaction.installment_id,
            )
            .all()
        )


        paid_by_installment = {
            installment_id:
                int(paid_amount or 0)
            for installment_id, paid_amount
            in payment_rows
        }


        # -------------------------------------------------
        # CALCULATE SUMMARY
        # -------------------------------------------------

        total_due = 0

        total_paid = 0

        paid_months = 0


        for installment in installments:

            due_amount = int(
                installment.due_amount or 0
            )

            paid_amount = int(
                paid_by_installment.get(
                    installment.id,
                    0,
                )
            )


            total_due += due_amount

            total_paid += min(
                paid_amount,
                due_amount,
            )


            if (
                paid_amount >=
                due_amount
                and due_amount > 0
            ):

                paid_months += 1


        remaining_amount = max(
            total_due - total_paid,
            0,
        )


        total_months = len(
            installments
        )


        remaining_months = max(
            total_months - paid_months,
            0,
        )


        # -------------------------------------------------
        # APPEND
        # -------------------------------------------------

        active_chits.append({

            "chit_id":
                chit.id,

            "chit_name":
                chit.name,

            "chit_code":
                chit.code,

            "member_id":
                member.id,

            "member_number":
                member.member_number,

            "member_name":
                member.member_name,

            "status":
                member.status,

            "total_due":
                total_due,

            "total_paid":
                total_paid,

            "remaining_amount":
                remaining_amount,

            "total_months":
                total_months,

            "paid_months":
                paid_months,

            "remaining_months":
                remaining_months,
        })


    # =====================================================
    # RETURN
    # =====================================================

    return {

        "customer":
            customer,

        "active_chits":
            active_chits,
    }