import calendar

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.admin.payment_transaction import PaymentTransaction
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_installment import ChitInstallment


# =========================================================
# ADD MONTHS
# =========================================================

def add_months(
    source_date: date,
    months: int,
) -> date:

    month = source_date.month - 1 + months

    year = (
        source_date.year
        + month // 12
    )

    month = (
        month % 12
    ) + 1

    day = min(
        source_date.day,
        calendar.monthrange(
            year,
            month,
        )[1],
    )

    return date(
        year,
        month,
        day,
    )


# =========================================================
# MANUAL GENERATE INSTALLMENTS FOR CHIT
# =========================================================

def generate_installments_for_chit(
    db: Session,
    company_id: int,
    chit_id: int,
    start_date: date,
    installment_count: int,
):

    # =====================================================
    # CHECK CHIT
    # =====================================================

    chit = (
        db.query(ChitGroup)
        .filter(
            ChitGroup.id == chit_id,
            ChitGroup.company_id == company_id,
        )
        .first()
    )

    if not chit:

        return {
            "error": "chit_not_found"
        }


    # =====================================================
    # VALIDATE INSTALLMENT COUNT
    # =====================================================

    if installment_count <= 0:

        return {
            "error": "invalid_installment_count"
        }


    # =====================================================
    # CHECK EXISTING INSTALLMENTS
    #
    # This endpoint is kept mainly for manual/testing use.
    # Normal application flow should use:
    # generate_installments_for_active_chit()
    # =====================================================

    existing_installments = (
        db.query(ChitInstallment)
        .join(
            ChitMember,
            ChitMember.id
            == ChitInstallment.chit_member_id,
        )
        .filter(
            ChitMember.chit_id == chit_id,
        )
        .count()
    )

    if existing_installments > 0:

        return {
            "error":
                "installments_already_generated"
        }


    # =====================================================
    # GET CONFIRMED / ACTIVE MEMBERS
    # =====================================================

    members = (
        db.query(ChitMember)
        .filter(
            ChitMember.chit_id == chit_id,
            ChitMember.status.in_([
                "confirmed",
                "active",
            ]),
        )
        .order_by(
            ChitMember.id
        )
        .all()
    )


    if not members:

        return {
            "error": "no_confirmed_members"
        }


    # =====================================================
    # GENERATE
    # =====================================================

    created_installments = []


    for member in members:

        for i in range(
            installment_count
        ):

            due_date = add_months(
                start_date,
                i,
            )


            installment = ChitInstallment(

                chit_member_id=
                    member.id,

                installment_number=
                    i + 1,

                due_date=
                    due_date,

                due_amount=
                    chit.monthly_emi,

                status="pending",
            )


            db.add(
                installment
            )

            created_installments.append(
                installment
            )


    # =====================================================
    # COMMIT
    #
    # This manual/testing function owns its transaction.
    # =====================================================

    db.commit()


    # =====================================================
    # REFRESH
    # =====================================================

    for installment in created_installments:

        db.refresh(
            installment
        )


    # =====================================================
    # BUILD RESPONSE
    # =====================================================

    return [
        build_installment_data(
            db=db,
            installment=installment,
        )
        for installment in created_installments
    ]


# =========================================================
# GET INSTALLMENTS FOR CHIT
# =========================================================

def get_installments_for_chit(
    db: Session,
    company_id: int,
    chit_id: int,
):

    # =====================================================
    # CHECK CHIT
    # =====================================================

    chit = (
        db.query(ChitGroup)
        .filter(
            ChitGroup.id == chit_id,
            ChitGroup.company_id == company_id,
        )
        .first()
    )

    if not chit:

        return {
            "error": "chit_not_found"
        }


    # =====================================================
    # GET INSTALLMENTS + PAID AMOUNT
    # =====================================================

    rows = (
        db.query(
            ChitInstallment,

            func.coalesce(
                func.sum(
                    PaymentTransaction.amount
                ),
                0,
            ).label(
                "paid_amount"
            ),
        )
        .join(
            ChitMember,
            ChitMember.id
            == ChitInstallment.chit_member_id,
        )
        .outerjoin(
            PaymentTransaction,
            PaymentTransaction.installment_id
            == ChitInstallment.id,
        )
        .filter(
            ChitMember.chit_id == chit_id,
        )
        .group_by(
            ChitInstallment.id,
        )
        .order_by(
            ChitInstallment.installment_number,
            ChitInstallment.id,
        )
        .all()
    )


    # =====================================================
    # BUILD RESPONSE
    # =====================================================

    response = []


    for installment, paid_amount in rows:

        due_amount = int(
            installment.due_amount or 0
        )

        paid_amount = int(
            paid_amount or 0
        )

        remaining_amount = max(
            due_amount - paid_amount,
            0,
        )


        # -------------------------------------------------
        # STATUS
        # -------------------------------------------------

        if paid_amount <= 0:

            installment_status = "pending"

        elif paid_amount < due_amount:

            installment_status = "partial"

        else:

            installment_status = "paid"


        response.append({

            "id":
                installment.id,

            "chit_member_id":
                installment.chit_member_id,

            "installment_number":
                installment.installment_number,

            "due_date":
                installment.due_date,

            "due_amount":
                due_amount,

            "paid_amount":
                paid_amount,

            "remaining_amount":
                remaining_amount,

            "status":
                installment_status,

            "created_at":
                installment.created_at,

            "updated_at":
                installment.updated_at,

        })


    return response


# =========================================================
# BUILD INSTALLMENT RESPONSE
# =========================================================

def build_installment_data(
    db: Session,
    installment: ChitInstallment,
):

    paid_amount = (
        db.query(
            func.coalesce(
                func.sum(
                    PaymentTransaction.amount
                ),
                0,
            )
        )
        .filter(
            PaymentTransaction.installment_id
            == installment.id
        )
        .scalar()
    )


    due_amount = int(
        installment.due_amount or 0
    )

    paid_amount = int(
        paid_amount or 0
    )

    remaining_amount = max(
        due_amount - paid_amount,
        0,
    )


    # =====================================================
    # CALCULATE STATUS
    # =====================================================

    if paid_amount <= 0:

        installment_status = "pending"

    elif paid_amount < due_amount:

        installment_status = "partial"

    else:

        installment_status = "paid"


    return {

        "id":
            installment.id,

        "chit_member_id":
            installment.chit_member_id,

        "installment_number":
            installment.installment_number,

        "due_date":
            installment.due_date,

        "due_amount":
            due_amount,

        "paid_amount":
            paid_amount,

        "remaining_amount":
            remaining_amount,

        "status":
            installment_status,

        "created_at":
            installment.created_at,

        "updated_at":
            installment.updated_at,

    }


# =========================================================
# GENERATE INSTALLMENTS FOR MEMBER
# =========================================================

def generate_installments_for_member(
    db: Session,
    company_id: int,
    chit_id: int,
    member_id: int,
):

    # =====================================================
    # CHECK CHIT
    # =====================================================

    chit = (
        db.query(ChitGroup)
        .filter(
            ChitGroup.id == chit_id,
            ChitGroup.company_id == company_id,
        )
        .first()
    )

    if not chit:

        return {
            "error": "chit_not_found"
        }


    # =====================================================
    # CHECK MEMBER
    # =====================================================

    member = (
        db.query(ChitMember)
        .filter(
            ChitMember.id == member_id,
            ChitMember.chit_id == chit_id,
            ChitMember.status.in_([
                "confirmed",
                "active",
            ]),
        )
        .first()
    )

    if not member:

        return {
            "error": "member_not_found"
        }


    # =====================================================
    # VALIDATE CHIT SCHEDULE
    # =====================================================

    if not chit.start_date:

        return {
            "error": "chit_start_date_missing"
        }


    if (
        not chit.duration_months
        or chit.duration_months <= 0
    ):

        return {
            "error": "chit_duration_missing"
        }


    # =====================================================
    # GET EXISTING INSTALLMENT NUMBERS
    # =====================================================

    existing_numbers = {
        number
        for number, in (
            db.query(
                ChitInstallment.installment_number
            )
            .filter(
                ChitInstallment.chit_member_id
                == member.id
            )
            .all()
        )
    }


    # =====================================================
    # CREATE ONLY MISSING INSTALLMENTS
    # =====================================================

    created_installments = []


    for i in range(
        chit.duration_months
    ):

        installment_number = i + 1


        # -------------------------------------------------
        # ALREADY EXISTS
        # -------------------------------------------------

        if installment_number in existing_numbers:

            continue


        installment = ChitInstallment(

            chit_member_id=
                member.id,

            installment_number=
                installment_number,

            due_date=
                add_months(
                    chit.start_date,
                    i,
                ),

            due_amount=
                chit.monthly_emi,

            status="pending",
        )


        db.add(
            installment
        )

        created_installments.append(
            installment
        )


    # =====================================================
    # NO COMMIT HERE
    #
    # Caller controls the transaction.
    # =====================================================

    return created_installments


# =========================================================
# GENERATE INSTALLMENTS WHEN CHIT BECOMES ACTIVE
# =========================================================

def generate_installments_for_active_chit(
    db: Session,
    company_id: int,
    chit_id: int,
):

    # =====================================================
    # CHECK CHIT
    # =====================================================

    chit = (
        db.query(ChitGroup)
        .filter(
            ChitGroup.id == chit_id,
            ChitGroup.company_id == company_id,
        )
        .first()
    )

    if not chit:

        return {
            "error": "chit_not_found"
        }


    # =====================================================
    # VALIDATE START DATE
    # =====================================================

    if not chit.start_date:

        return {
            "error": "chit_start_date_missing"
        }


    # =====================================================
    # VALIDATE DURATION
    # =====================================================

    if (
        not chit.duration_months
        or chit.duration_months <= 0
    ):

        return {
            "error": "chit_duration_missing"
        }


    # =====================================================
    # GET ACTIVE / CONFIRMED MEMBERS
    # =====================================================

    members = (
        db.query(ChitMember)
        .filter(
            ChitMember.chit_id == chit_id,
            ChitMember.status.in_([
                "confirmed",
                "active",
            ]),
        )
        .order_by(
            ChitMember.member_number.asc()
        )
        .all()
    )


    if not members:

        return {
            "error": "no_confirmed_members"
        }


    # =====================================================
    # CREATE ONLY MISSING INSTALLMENTS
    #
    # For every member, independently check which
    # installment numbers already exist.
    # =====================================================

    created_installments = []


    for member in members:

        existing_numbers = {
            number
            for number, in (
                db.query(
                    ChitInstallment.installment_number
                )
                .filter(
                    ChitInstallment.chit_member_id
                    == member.id
                )
                .all()
            )
        }


        for i in range(
            chit.duration_months
        ):

            installment_number = i + 1


            # -------------------------------------------------
            # ALREADY EXISTS → SKIP
            # -------------------------------------------------

            if installment_number in existing_numbers:

                continue


            installment = ChitInstallment(

                chit_member_id=
                    member.id,

                installment_number=
                    installment_number,

                due_date=
                    add_months(
                        chit.start_date,
                        i,
                    ),

                due_amount=
                    chit.monthly_emi,

                status="pending",
            )


            db.add(
                installment
            )

            created_installments.append(
                installment
            )


    # =====================================================
    # IMPORTANT
    # =====================================================
    #
    # NO db.commit() HERE.
    #
    # update_chit_group() controls the transaction.
    #

    return created_installments