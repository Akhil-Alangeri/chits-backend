from datetime import datetime

from sqlalchemy.orm import Session

from app.models.admin.chit_group import ChitGroup
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_member import ChitMember
from app.services.chit_installment_service import (
    generate_installments_for_member,
)   


# =========================================================
# GENERATE NEXT MEMBER NUMBER
# =========================================================

def generate_member_number(
    db: Session,
    chit_id: int,
) -> int:

    latest_member = (
        db.query(ChitMember)
        .filter(
            ChitMember.chit_id == chit_id
        )
        .order_by(
            ChitMember.member_number.desc()
        )
        .first()
    )

    if not latest_member:
        return 1

    return latest_member.member_number + 1


# =========================================================
# COUNT OCCUPIED SLOTS
# =========================================================

def get_occupied_slot_count(
    db: Session,
    chit_id: int,
) -> int:

    return (
        db.query(ChitMember)
        .filter(
            ChitMember.chit_id == chit_id,
            ChitMember.status.in_([
                "confirmed",
                "active",
            ]),
        )
        .count()
    )


# =========================================================
# ADD MEMBER
# =========================================================

def add_chit_member(
    db: Session,
    company_id: int,
    chit_id: int,
    member_data,
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
    # CHECK CUSTOMER
    # =====================================================

    customer = (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.id
            == member_data.customer_profile_id,

            CustomerProfile.company_id
            == company_id,
        )
        .first()
    )

    if not customer:
        return {
            "error": "customer_not_found"
        }


    # =====================================================
    # CHECK CAPACITY
    # =====================================================

    occupied_count = get_occupied_slot_count(
        db,
        chit_id,
    )

    if occupied_count >= chit.max_members:
        return {
            "error": "chit_full"
        }


    # =====================================================
    # AUTOMATIC MEMBER NUMBER
    # =====================================================

    member_number = generate_member_number(
        db,
        chit_id,
    )


    # =====================================================
    # AUTOMATIC SLOT NUMBER
    # =====================================================

    slot_number = generate_slot_number(
        db,
        chit_id,
        member_data.customer_profile_id,
    )


    # =====================================================
    # CREATE MEMBER
    # =====================================================

    member = ChitMember(

        chit_id=chit_id,

        customer_profile_id=
            member_data.customer_profile_id,

        member_number=member_number,

        slot_number=slot_number,

        member_name=
            member_data.member_name.strip(),

        status="confirmed",

        confirmed_at=datetime.utcnow(),

        notes=member_data.notes,
    )


    db.add(member)

    # Flush is enough to get member.id.
    # Do NOT commit yet.
    db.flush()


    # =====================================================
    # GENERATE INSTALLMENTS ONLY FOR ACTIVE CHIT
    # =====================================================

    if chit.status == "active":

        installment_result = (
            generate_installments_for_member(
                db=db,
                company_id=company_id,
                chit_id=chit_id,
                member_id=member.id,
            )
        )


        # -------------------------------------------------
        # HANDLE INSTALLMENT ERRORS
        # -------------------------------------------------

        if isinstance(
            installment_result,
            dict,
        ):

            error = installment_result.get(
                "error"
            )

            db.rollback()

            return {
                "error": error
            }


    # =====================================================
    # COMMIT EVERYTHING
    # =====================================================

    db.commit()

    db.refresh(member)

    return member

# =========================================================
# GET MEMBERS
# =========================================================

def get_chit_members(
    db: Session,
    company_id: int,
    chit_id: int,
):

    return (
        db.query(ChitMember)
        .join(CustomerProfile)
        .filter(
            ChitMember.chit_id == chit_id,
            CustomerProfile.company_id
            == company_id,
            ChitMember.status.in_([
                'confirmed',
                'active'
            ])
        )
        .order_by(
            ChitMember.member_number.asc()
        )
        .all()
    )


# =========================================================
# GET MEMBER
# =========================================================

def get_chit_member(
    db: Session,
    company_id: int,
    member_id: int,
):

    return (
        db.query(ChitMember)
        .join(CustomerProfile)
        .filter(
            ChitMember.id == member_id,
            CustomerProfile.company_id
            == company_id,
        )
        .first()
    )


# =========================================================
# UPDATE MEMBER
# =========================================================

def update_chit_member(
    db: Session,
    company_id: int,
    member_id: int,
    member_data,
):

    member = get_chit_member(
        db,
        company_id,
        member_id,
    )

    if not member:
        return None

    # -----------------------------------------------------
    # NAME
    # -----------------------------------------------------

    if member_data.member_name is not None:

        member.member_name = (
            member_data.member_name.strip()
        )

    # -----------------------------------------------------
    # NOTES
    # -----------------------------------------------------

    if member_data.notes is not None:

        member.notes = member_data.notes

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    if member_data.status is not None:

        new_status = member_data.status

        member.status = new_status

        if new_status == "cancelled":

            member.cancelled_at = (
                datetime.utcnow()
            )

            member.cancel_reason = (
                member_data.cancel_reason
            )

        elif new_status in [
            "confirmed",
            "active",
        ]:

            member.cancelled_at = None

            member.cancel_reason = None

    db.commit()

    db.refresh(member)

    return member


# =============================
# GENERETE SLOT NUMBER
#=============================

def generate_slot_number(
    db: Session,
    chit_id: int,
    customer_profile_id: int,
) -> int:

    latest_slot = (
        db.query(ChitMember)
        .filter(
            ChitMember.chit_id == chit_id,
            ChitMember.customer_profile_id
            == customer_profile_id,
        )
        .order_by(
            ChitMember.slot_number.desc()
        )
        .first()
    )

    if not latest_slot:

        return 1

    return latest_slot.slot_number + 1




# =========================================================
# REMOVE MEMBER FROM CHIT
# =========================================================

def remove_chit_member(
    db: Session,
    company_id: int,
    chit_id: int,
    member_id: int,
):

    # =====================================================
    # GET MEMBER + VERIFY CHIT + COMPANY
    # =====================================================

    member = (
        db.query(ChitMember)
        .join(
            CustomerProfile,
            CustomerProfile.id
            == ChitMember.customer_profile_id,
        )
        .join(
            ChitGroup,
            ChitGroup.id
            == ChitMember.chit_id,
        )
        .filter(
            ChitMember.id == member_id,
            ChitMember.chit_id == chit_id,
            ChitGroup.company_id == company_id,
            CustomerProfile.company_id == company_id,
        )
        .first()
    )

    if not member:

        return {
            "error": "member_not_found"
        }


    # =====================================================
    # ALREADY REMOVED
    # =====================================================

    if member.status == "cancelled":

        return {
            "error": "member_already_removed"
        }


    # =====================================================
    # REMOVE MEMBERSHIP
    # =====================================================

    member.status = "cancelled"

    member.cancelled_at = datetime.utcnow()

    member.cancel_reason = "Removed by admin"


    # =====================================================
    # COMMIT
    # =====================================================

    db.commit()

    db.refresh(member)

    return member