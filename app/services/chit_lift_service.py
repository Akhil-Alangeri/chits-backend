from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from decimal import Decimal

from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_months import ChitMonth
from app.models.admin.chitlift import ChitLift


ACTIVE_MEMBER_STATUSES = ("confirmed", "active")


# =========================================================
# GET CHIT
# =========================================================

def get_chit_for_company(
    db: Session,
    company_id: int,
    chit_id: int,
):
    return (
        db.query(ChitGroup)
        .filter(
            ChitGroup.id == chit_id,
            ChitGroup.company_id == company_id,
        )
        .first()
    )


# =========================================================
# GET MEMBER FOR CHIT
# =========================================================

def get_member_for_chit(
    db: Session,
    company_id: int,
    chit_id: int,
    member_id: int,
):
    return (
        db.query(ChitMember)
        .join(
            ChitGroup,
            ChitGroup.id == ChitMember.chit_id,
        )
        .filter(
            ChitMember.id == member_id,
            ChitMember.chit_id == chit_id,
            ChitGroup.company_id == company_id,
            ChitMember.status.in_(ACTIVE_MEMBER_STATUSES),
        )
        .first()
    )


# =========================================================
# GET MONTH FOR CHIT
# =========================================================

def get_month_for_chit(
    db: Session,
    company_id: int,
    chit_id: int,
    chit_month_id: int,
):
    return (
        db.query(ChitMonth)
        .filter(
            ChitMonth.id == chit_month_id,
            ChitMonth.company_id == company_id,
            ChitMonth.chit_id == chit_id,
        )
        .first()
    )


# =========================================================
# GET ELIGIBLE MEMBERS FOR LIFT
#
# A member/slot can be lifted only once in a chit.
# Customer-level restriction DOES NOT apply.
# =========================================================

def get_eligible_members_for_lift(
    db: Session,
    company_id: int,
    chit_id: int,
):
    # -----------------------------------------------------
    # CHECK CHIT
    # -----------------------------------------------------

    chit = get_chit_for_company(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
    )

    if not chit:
        return {
            "error": "chit_not_found",
        }

    # -----------------------------------------------------
    # GET ACTIVE MEMBERS
    # -----------------------------------------------------

    members = (
        db.query(ChitMember)
        .filter(
            ChitMember.chit_id == chit_id,
            ChitMember.status.in_(ACTIVE_MEMBER_STATUSES),
        )
        .order_by(
            ChitMember.member_number.asc(),
            ChitMember.id.asc(),
        )
        .all()
    )

    if not members:
        return {
            "error": "no_eligible_members",
        }

    # -----------------------------------------------------
    # GET ALREADY LIFTED MEMBER IDS
    # -----------------------------------------------------

    lifted_member_ids = {
        member_id
        for member_id, in (
            db.query(ChitLift.chit_member_id)
            .filter(
                ChitLift.company_id == company_id,
                ChitLift.chit_id == chit_id,
            )
            .all()
        )
    }

    # -----------------------------------------------------
    # FILTER OUT ALREADY LIFTED SLOTS
    # -----------------------------------------------------

    eligible_members = [
        member
        for member in members
        if member.id not in lifted_member_ids
    ]

    if not eligible_members:
        return {
            "error": "no_eligible_members",
        }

    return eligible_members


# =========================================================
# CHECK MEMBER ALREADY LIFTED
# =========================================================

def get_existing_member_lift(
    db: Session,
    company_id: int,
    chit_id: int,
    member_id: int,
):
    return (
        db.query(ChitLift)
        .filter(
            ChitLift.company_id == company_id,
            ChitLift.chit_id == chit_id,
            ChitLift.chit_member_id == member_id,
        )
        .first()
    )


# =========================================================
# CHECK MONTH ALREADY LIFTED
# =========================================================

def get_existing_month_lift(
    db: Session,
    company_id: int,
    chit_id: int,
    chit_month_id: int,
):
    return (
        db.query(ChitLift)
        .filter(
            ChitLift.company_id == company_id,
            ChitLift.chit_id == chit_id,
            ChitLift.chit_month_id == chit_month_id,
        )
        .first()
    )


# =========================================================
# CREATE CHIT LIFT
# =========================================================

def create_chit_lift(
    db: Session,
    company_id: int,
    chit_id: int,
    member_id: int,
    lift_data,
):
    # =====================================================
    # CHECK CHIT
    # =====================================================

    chit = get_chit_for_company(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
    )

    if not chit:
        return {
            "error": "chit_not_found",
        }

    # =====================================================
    # CHECK MEMBER
    # =====================================================

    member = get_member_for_chit(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
        member_id=member_id,
    )

    if not member:
        return {
            "error": "member_not_found",
        }

    # =====================================================
    # VALIDATE MONTH
    # =====================================================

    chit_month_id = lift_data.chit_month_id

    if not chit_month_id:
        return {
            "error": "month_required",
            "message": "Chit month is required.",
        }

    month = get_month_for_chit(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
        chit_month_id=chit_month_id,
    )

    if not month:
        return {
            "error": "month_not_found",
        }

    # =====================================================
    # CHECK MEMBER / SLOT ALREADY LIFTED
    # =====================================================

    existing_member_lift = get_existing_member_lift(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
        member_id=member.id,
    )

    if existing_member_lift:
        return {
            "error": "member_already_lifted",
            "existing_lift_id": existing_member_lift.id,
        }

    # =====================================================
    # CHECK MONTH ALREADY HAS WINNER
    # =====================================================

    existing_month_lift = get_existing_month_lift(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
        chit_month_id=chit_month_id,
    )

    if existing_month_lift:
        return {
            "error": "month_already_lifted",
            "existing_lift_id": existing_month_lift.id,
        }

    # =====================================================
    # DISCOUNT AMOUNT
    # =====================================================

    discount_amount = (
        lift_data.discount_amount
        if lift_data.discount_amount is not None
        else Decimal("0")
    )

    # =====================================================
    # CALCULATE ACTUAL LIFTED AMOUNT
    # =====================================================

    lifted_amount = (
        month.monthly_lift_amount
        + discount_amount
    )

    # =====================================================
    # PAYMENT SPLIT
    # =====================================================

    upi_amount = (
        lift_data.upi_amount
        if lift_data.upi_amount is not None
        else Decimal("0")
    )

    cash_amount = (
        lift_data.cash_amount
        if lift_data.cash_amount is not None
        else Decimal("0")
    )

    # =====================================================
    # VALIDATE PAYMENT SPLIT
    # =====================================================

    # =====================================================
# VALIDATE PAYMENT AMOUNT
# =====================================================

    payment_total = upi_amount + cash_amount

    if payment_total > lifted_amount:
        return {
            "error": "payment_amount_exceeds_lift",
            "message": (
                "UPI amount and cash amount cannot exceed "
                "the lifted amount."
            ),
        }

    # =====================================================
    # CREATE LIFT
    # =====================================================

    lift = ChitLift(
        company_id=company_id,
        chit_id=chit_id,
        chit_member_id=member.id,

        # Historical snapshots
        customer_name=member.member_name,
        member_number=str(member.member_number),
        slot_number=member.slot_number,

        # Month
        chit_month_id=month.id,
        cycle_number=month.month_number,

        # Lift
        lift_date=lift_data.lift_date,
        discount_amount=discount_amount,
        lifted_amount=lifted_amount,

        # Payment split
        upi_amount=upi_amount,
        cash_amount=cash_amount,

        # Payout
        payout_status=lift_data.payout_status,
        payout_date=lift_data.payout_date,

        # Notes / audit
        notes=lift_data.notes,
        edit_reason=None,
    )

    db.add(lift)

    # =====================================================
    # COMMIT
    # =====================================================

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        return {
            "error": "lift_conflict",
            "message": (
                "Another lift already exists for this "
                "member slot or month."
            ),
        }

    # =====================================================
    # REFRESH
    # =====================================================

    db.refresh(lift)

    return lift

# =========================================================
# GET ALL LIFTS FOR CHIT
# =========================================================

def get_chit_lifts(
    db: Session,
    company_id: int,
    chit_id: int,
):
    # -----------------------------------------------------
    # CHECK CHIT
    # -----------------------------------------------------

    chit = get_chit_for_company(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
    )

    if not chit:
        return {
            "error": "chit_not_found",
        }

    # -----------------------------------------------------
    # GET LIFTS
    #
    # New records are ordered by chit_month_id.
    # Legacy records without chit_month_id are still
    # ordered using cycle_number.
    # -----------------------------------------------------

    return (
        db.query(ChitLift)
        .filter(
            ChitLift.company_id == company_id,
            ChitLift.chit_id == chit_id,
        )
        .outerjoin(
            ChitMonth,
            ChitMonth.id == ChitLift.chit_month_id,
        )
        .order_by(
            ChitMonth.month_number.asc(),
            ChitLift.cycle_number.asc(),
            ChitLift.id.asc(),
        )
        .all()
    )


# =========================================================
# GET SINGLE LIFT
# =========================================================

def get_chit_lift(
    db: Session,
    company_id: int,
    chit_id: int,
    lift_id: int,
):
    return (
        db.query(ChitLift)
        .filter(
            ChitLift.id == lift_id,
            ChitLift.company_id == company_id,
            ChitLift.chit_id == chit_id,
        )
        .first()
    )


# =========================================================
# GET LIFTS FOR PARTICULAR MEMBER / SLOT
# =========================================================

def get_member_lifts(
    db: Session,
    company_id: int,
    chit_id: int,
    member_id: int,
):
    # -----------------------------------------------------
    # VERIFY MEMBER
    # -----------------------------------------------------

    member = get_member_for_chit(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
        member_id=member_id,
    )

    if not member:
        return {
            "error": "member_not_found",
        }

    # -----------------------------------------------------
    # GET LIFT HISTORY
    # -----------------------------------------------------

    return (
        db.query(ChitLift)
        .filter(
            ChitLift.company_id == company_id,
            ChitLift.chit_id == chit_id,
            ChitLift.chit_member_id == member_id,
        )
        .outerjoin(
            ChitMonth,
            ChitMonth.id == ChitLift.chit_month_id,
        )
        .order_by(
            ChitMonth.month_number.asc(),
            ChitLift.cycle_number.asc(),
            ChitLift.id.asc(),
        )
        .all()
    )


# =========================================================
# UPDATE CHIT LIFT
#
# Every update requires edit_reason.
# =========================================================

# =========================================================
# UPDATE CHIT LIFT
# Every update requires edit_reason.
# =========================================================

# =========================================================
# UPDATE CHIT LIFT
#
# Every update requires edit_reason.
# =========================================================

def update_chit_lift(
    db: Session,
    company_id: int,
    chit_id: int,
    lift_id: int,
    lift_data,
):
    # =====================================================
    # GET EXISTING LIFT
    # =====================================================

    lift = get_chit_lift(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
        lift_id=lift_id,
    )

    if not lift:
        return {
            "error": "lift_not_found",
        }

    # =====================================================
    # EDIT REASON REQUIRED
    # =====================================================

    edit_reason = (
        lift_data.edit_reason.strip()
        if lift_data.edit_reason
        else ""
    )

    if not edit_reason:
        return {
            "error": "edit_reason_required",
        }

    # =====================================================
    # GET UPDATE DATA
    # =====================================================

    update_data = lift_data.model_dump(
        exclude_unset=True,
    )

    update_data.pop(
        "edit_reason",
        None,
    )

    # =====================================================
    # GET CHIT
    # =====================================================

    chit = get_chit_for_company(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
    )

    if not chit:
        return {
            "error": "chit_not_found",
        }

    # =====================================================
    # DETERMINE NEW VALUES
    # =====================================================

    new_month_id = update_data.get(
        "chit_month_id",
        lift.chit_month_id,
    )

    new_member_id = update_data.get(
        "chit_member_id",
        lift.chit_member_id,
    )

    # =====================================================
    # VALIDATE MONTH
    # =====================================================

    if not new_month_id:
        return {
            "error": "month_required",
            "message": "Chit month is required.",
        }

    new_month = get_month_for_chit(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
        chit_month_id=new_month_id,
    )

    if not new_month:
        return {
            "error": "month_not_found",
        }

    # =====================================================
    # VALIDATE NEW MEMBER
    # =====================================================

    new_member = get_member_for_chit(
        db=db,
        company_id=company_id,
        chit_id=chit_id,
        member_id=new_member_id,
    )

    if not new_member:
        return {
            "error": "member_not_found",
        }

    # =====================================================
    # CHECK NEW MEMBER ALREADY HAS ANOTHER LIFT
    # =====================================================

    member_lift = (
        db.query(ChitLift)
        .filter(
            ChitLift.company_id == company_id,
            ChitLift.chit_id == chit_id,
            ChitLift.chit_member_id == new_member_id,
            ChitLift.id != lift.id,
        )
        .first()
    )

    if member_lift:
        return {
            "error": "member_already_lifted",
            "existing_lift_id": member_lift.id,
        }

    # =====================================================
    # CHECK MONTH CONFLICT
    # =====================================================

    month_lift = (
        db.query(ChitLift)
        .filter(
            ChitLift.company_id == company_id,
            ChitLift.chit_id == chit_id,
            ChitLift.chit_month_id == new_month_id,
            ChitLift.id != lift.id,
        )
        .first()
    )

    if month_lift:
        return {
            "error": "month_already_lifted",
            "existing_lift_id": month_lift.id,
        }

    # =====================================================
    # APPLY MEMBER
    # =====================================================

    lift.chit_member_id = new_member.id

    lift.customer_name = new_member.member_name

    lift.member_number = str(
        new_member.member_number
    )

    lift.slot_number = new_member.slot_number

    # =====================================================
    # APPLY MONTH
    # =====================================================

    lift.chit_month_id = new_month.id

    # Legacy compatibility
    lift.cycle_number = new_month.month_number

    # =====================================================
    # APPLY LIFT DATE
    # =====================================================

    if "lift_date" in update_data:
        lift.lift_date = update_data["lift_date"]

    # =====================================================
    # DISCOUNT AMOUNT
    # =====================================================

    if "discount_amount" in update_data:
        discount_amount = (
            update_data["discount_amount"]
            if update_data["discount_amount"] is not None
            else Decimal("0")
        )
    else:
        discount_amount = (
            lift.discount_amount
            if lift.discount_amount is not None
            else Decimal("0")
        )

    # =====================================================
    # CALCULATE ACTUAL LIFTED AMOUNT
    # =====================================================

    lifted_amount = (
        new_month.monthly_lift_amount
        + discount_amount
    )

    # =====================================================
    # PAYMENT SPLIT
    # =====================================================

    if "upi_amount" in update_data:
        upi_amount = (
            update_data["upi_amount"]
            if update_data["upi_amount"] is not None
            else Decimal("0")
        )
    else:
        upi_amount = (
            lift.upi_amount
            if lift.upi_amount is not None
            else Decimal("0")
        )

    if "cash_amount" in update_data:
        cash_amount = (
            update_data["cash_amount"]
            if update_data["cash_amount"] is not None
            else Decimal("0")
        )
    else:
        cash_amount = (
            lift.cash_amount
            if lift.cash_amount is not None
            else Decimal("0")
        )

    # =====================================================
    # VALIDATE PAYMENT AMOUNT
    # =====================================================

    payment_total = upi_amount + cash_amount

    if payment_total > lifted_amount:
        return {
            "error": "payment_amount_exceeds_lift",
            "message": (
                "UPI amount and cash amount cannot exceed "
                "the lifted amount."
            ),
        }

    # =====================================================
    # SAVE AMOUNTS
    # =====================================================

    lift.discount_amount = discount_amount

    lift.lifted_amount = lifted_amount

    lift.upi_amount = upi_amount

    lift.cash_amount = cash_amount

    # =====================================================
    # PAYOUT STATUS
    # =====================================================

    if "payout_status" in update_data:
        lift.payout_status = (
            update_data["payout_status"]
        )

    # =====================================================
    # PAYOUT DATE
    # =====================================================

    if "payout_date" in update_data:
        lift.payout_date = (
            update_data["payout_date"]
        )

    # =====================================================
    # NOTES
    # =====================================================

    if "notes" in update_data:
        lift.notes = update_data["notes"]

    # =====================================================
    # EDIT REASON
    # =====================================================

    lift.edit_reason = edit_reason

    # =====================================================
    # COMMIT
    # =====================================================

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        return {
            "error": "lift_conflict",
            "message": (
                "Another lift already exists for this "
                "member slot or month."
            ),
        }

    # =====================================================
    # REFRESH
    # =====================================================

    db.refresh(lift)

    return lift