from sqlalchemy.orm import Session
from dateutil.relativedelta import relativedelta
from app.services.chit_installment_service import add_months
from app.models.admin.payment_transaction import PaymentTransaction
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_months import ChitMonth
from app.models.admin.company import Company


from app.schemas.chit_group import (
    ChitGroupCreate,
    ChitGroupUpdate,
)

from app.services.chit_installment_service import (
    generate_installments_for_active_chit,
)


# =========================================================
# GENERATE CHIT CODE
# =========================================================

def generate_chit_code(
    db: Session,
    company_id: int
) -> str:

    # Get all existing codes for this company
    existing_chits = (
        db.query(ChitGroup)
        .filter(
            ChitGroup.company_id == company_id
        )
        .all()
    )

    numbers = []

    for chit in existing_chits:

        if not chit.code:
            continue

        try:

            number = int(
                chit.code.split("-")[-1]
            )

            numbers.append(number)

        except ValueError:
            continue

    next_number = (
        max(numbers) + 1
        if numbers
        else 1
    )

    return f"CHIT-{next_number:03d}"


# =========================================================
# CREATE CHIT GROUP
# =========================================================

def create_chit_group(
    db: Session,
    company_id: int,
    chit_data: ChitGroupCreate
):

    # -----------------------------------------
    # Check company
    # -----------------------------------------

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

    # -----------------------------------------
    # Validate start date
    # -----------------------------------------

    if not chit_data.start_date:
        return {
            "error": "start_date_required"
        }

    # -----------------------------------------
    # Validate month count
    # -----------------------------------------

    if len(chit_data.months) != chit_data.duration_months:
        return {
            "error": "months_count_mismatch"
        }

    # -----------------------------------------
    # Validate month numbers
    # -----------------------------------------

    expected_month_numbers = list(
        range(
            1,
            chit_data.duration_months + 1
        )
    )

    actual_month_numbers = [
        month.month_number
        for month in chit_data.months
    ]

    if actual_month_numbers != expected_month_numbers:
        return {
            "error": "invalid_month_numbers"
        }

    # -----------------------------------------
    # Validate month dates
    # -----------------------------------------

    for index, month_data in enumerate(
        chit_data.months
    ):

        expected_date = (
            chit_data.start_date
            + relativedelta(months=index)
        )

        if month_data.month_date != expected_date:
            return {
                "error": "invalid_month_date",
                "month_number": month_data.month_number,
            }

    # -----------------------------------------
    # Generate code
    # -----------------------------------------

    code = generate_chit_code(
        db,
        company_id
    )

    # -----------------------------------------
    # Create chit
    # -----------------------------------------

    chit = ChitGroup(

        company_id=company_id,

        name=chit_data.name,

        code=code,

        chit_value=chit_data.chit_value,

        # Keep first month's EMI as the
        # group-level summary value.
        monthly_emi=chit_data.months[0].monthly_emi,

        duration_months=chit_data.duration_months,

        max_members=chit_data.max_members,

        start_date=chit_data.start_date,

        status="draft"

    )

    db.add(chit)

    # Get chit.id without committing yet
    db.flush()

    # -----------------------------------------
    # Create monthly schedule
    # -----------------------------------------

    for month_data in chit_data.months:

        chit_month = ChitMonth(

            company_id=company_id,

            chit_id=chit.id,

            month_number=month_data.month_number,

            month_date=month_data.month_date,

            monthly_emi=month_data.monthly_emi,

            monthly_lift_amount=(
                month_data.monthly_lift_amount
            ),

        )

        db.add(chit_month)

    # -----------------------------------------
    # Commit everything together
    # -----------------------------------------

    try:

        db.commit()

    except Exception:

        db.rollback()

        raise

    # -----------------------------------------
    # Refresh
    # -----------------------------------------

    db.refresh(chit)

    return chit

# =========================================================
# GET ALL CHITS
# =========================================================

def get_all_chit_groups(
    db: Session,
    company_id: int
):

    return (
        db.query(ChitGroup)
        .filter(
            ChitGroup.company_id == company_id
        )
        .order_by(
            ChitGroup.id.desc()
        )
        .all()
    )


# =========================================================
# GET SINGLE CHIT
# =========================================================

def get_chit_group(
    db: Session,
    company_id: int,
    chit_id: int
):

    return (
        db.query(ChitGroup)
        .filter(
            ChitGroup.id == chit_id,
            ChitGroup.company_id == company_id
        )
        .first()
    )
    
    
    
def regenerate_installments_for_active_chit(
    db: Session,
    company_id: int,
    chit_id: int,
):

    # =====================================================
    # GET CHIT
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
    # VALIDATE CHIT
    # =====================================================

    if not chit.start_date:
        return {
            "error": "chit_start_date_missing"
        }

    if not chit.duration_months or chit.duration_months <= 0:
        return {
            "error": "chit_duration_missing"
        }

    # =====================================================
    # GET MONTH SCHEDULE
    # =====================================================

    months = (
        db.query(ChitMonth)
        .filter(
            ChitMonth.chit_id == chit_id,
            ChitMonth.company_id == company_id,
        )
        .order_by(
            ChitMonth.month_number.asc()
        )
        .all()
    )

    if len(months) != chit.duration_months:
        return {
            "error": "chit_month_schedule_incomplete"
        }

    # =====================================================
    # GET MEMBERS
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
        .all()
    )

    if not members:
        return {
            "error": "no_confirmed_members"
        }

    # =====================================================
    # DELETE EXISTING INSTALLMENTS
    # ONLY WHEN NO PAYMENTS EXIST
    # =====================================================

    db.query(ChitInstallment).filter(
        ChitInstallment.chit_member_id.in_(
            [
                member.id
                for member in members
            ]
        )
    ).delete(
        synchronize_session=False
    )

    db.flush()

    # =====================================================
    # GENERATE INSTALLMENTS
    # =====================================================

    for member in members:

        for month in months:

            installment = ChitInstallment(

                chit_member_id=member.id,

                installment_number=(
                    month.month_number
                ),

                due_date=(
                    month.month_date
                ),

                # IMPORTANT:
                # EMI comes from ChitMonth
                due_amount=(
                    month.monthly_emi
                ),

                status="pending",

            )

            db.add(installment)

    db.flush()

    return {
        "success": True
    }





# =========================================================
# UPDATE CHIT
# =========================================================

def update_chit_group(
    db: Session,
    company_id: int,
    chit_id: int,
    chit_data: ChitGroupUpdate,
):
    # =====================================================
    # GET CHIT
    # =====================================================

    chit = get_chit_group(
        db,
        company_id,
        chit_id,
    )

    if not chit:
        return None

    # =====================================================
    # GET BASIC UPDATE DATA
    # =====================================================
    # IMPORTANT:
    # months are nested Pydantic objects.
    # Do NOT convert them into dicts here.
    #
    # We separately keep months_data from chit_data.months.

    update_data = chit_data.model_dump(
        exclude_unset=True,
        exclude={"months"},
    )

    # =====================================================
    # MONTH SCHEDULE
    # =====================================================

    months_changed = chit_data.months is not None

    months_data = (
        chit_data.months
        if months_changed
        else None
    )

    # =====================================================
    # CHECK STATUS TRANSITION
    # =====================================================

    old_status = chit.status

    new_status = update_data.get(
        "status",
        old_status,
    )

    # =====================================================
    # CHECK IMPORTANT CHANGES
    # =====================================================

    start_date_changed = (
        "start_date" in update_data
        and update_data["start_date"] != chit.start_date
    )

    duration_changed = (
        "duration_months" in update_data
        and update_data["duration_months"] != chit.duration_months
    )

    # =====================================================
    # CHECK EXISTING PAYMENTS
    # =====================================================

    has_payments = False

    if old_status == "active":
        has_payments = (
            db.query(PaymentTransaction)
            .join(
                ChitInstallment,
                ChitInstallment.id
                == PaymentTransaction.installment_id,
            )
            .join(
                ChitMember,
                ChitMember.id
                == ChitInstallment.chit_member_id,
            )
            .filter(
                ChitMember.chit_id == chit_id,
            )
            .first()
            is not None
        )

    # =====================================================
    # ACTIVE CHIT + SCHEDULE CHANGE + PAYMENTS
    # =====================================================
    # Once payments exist, do not allow changing:
    # - start date
    # - duration
    # - monthly schedule
    #
    # IMPORTANT:
    # Return BEFORE changing any DB object.

    if (
        old_status == "active"
        and has_payments
        and (
            start_date_changed
            or duration_changed
            or months_changed
        )
    ):
        db.rollback()

        if start_date_changed:
            return {
                "error": "cannot_change_start_date_after_payment"
            }

        return {
            "error": "cannot_change_month_schedule_after_payment"
        }

    # =====================================================
    # VALIDATE MONTH SCHEDULE
    # =====================================================

    if months_changed:

        if not months_data:
            return {
                "error": "months_required"
            }

        duration = update_data.get(
            "duration_months",
            chit.duration_months,
        )

        start_date = update_data.get(
            "start_date",
            chit.start_date,
        )

        # ---------------------------------------------
        # Start date required
        # ---------------------------------------------

        if not start_date:
            return {
                "error": "start_date_required"
            }

        # ---------------------------------------------
        # Duration validation
        # ---------------------------------------------

        if not duration or duration <= 0:
            return {
                "error": "invalid_duration"
            }

        # ---------------------------------------------
        # Month count
        # ---------------------------------------------

        if len(months_data) != duration:
            return {
                "error": "months_count_mismatch"
            }

        # ---------------------------------------------
        # Expected month numbers
        # ---------------------------------------------

        expected_month_numbers = list(
            range(
                1,
                duration + 1,
            )
        )

        actual_month_numbers = [
            month.month_number
            for month in months_data
        ]

        if actual_month_numbers != expected_month_numbers:
            return {
                "error": "invalid_month_numbers"
            }

        # ---------------------------------------------
        # Validate month details
        # ---------------------------------------------

        for index, month_data in enumerate(months_data):

            # -----------------------------------------
            # Validate month date
            # -----------------------------------------

            expected_date = (
                start_date
                + relativedelta(months=index)
            )

            if month_data.month_date != expected_date:
                return {
                    "error": "invalid_month_date",
                    "month_number": month_data.month_number,
                }

            # -----------------------------------------
            # Validate monthly EMI
            # -----------------------------------------

            if (
                month_data.monthly_emi is None
                or month_data.monthly_emi <= 0
            ):
                return {
                    "error": "invalid_monthly_emi",
                    "month_number": month_data.month_number,
                }

            # -----------------------------------------
            # Validate planned lift amount
            # -----------------------------------------

            if (
                month_data.monthly_lift_amount is None
                or month_data.monthly_lift_amount <= 0
            ):
                return {
                    "error": "invalid_monthly_lift_amount",
                    "month_number": month_data.month_number,
                }

        # ---------------------------------------------
        # Optional consistency:
        # first month EMI becomes group-level EMI
        # ---------------------------------------------

        update_data["monthly_emi"] = (
            months_data[0].monthly_emi
        )

    # =====================================================
    # ACTIVATING CHIT
    # =====================================================

    if (
        old_status != "active"
        and new_status == "active"
    ):

        member_count = (
            db.query(ChitMember)
            .filter(
                ChitMember.chit_id == chit_id,
                ChitMember.status.in_(
                    [
                        "confirmed",
                        "active",
                    ]
                ),
            )
            .count()
        )

        if member_count == 0:
            return {
                "error": "no_members"
            }

        # ---------------------------------------------
        # Active chit must have complete schedule
        # ---------------------------------------------

        if not months_changed:
            existing_month_count = (
                db.query(ChitMonth)
                .filter(
                    ChitMonth.chit_id == chit_id,
                    ChitMonth.company_id == company_id,
                )
                .count()
            )

            final_duration = update_data.get(
                "duration_months",
                chit.duration_months,
            )

            if existing_month_count != final_duration:
                return {
                    "error": "chit_month_schedule_incomplete"
                }

    # =====================================================
    # APPLY BASIC CHIT UPDATE
    # =====================================================
    # Do NOT write months into ChitGroup.

    for field, value in update_data.items():

        if field == "months":
            continue

        setattr(
            chit,
            field,
            value,
        )

    # =====================================================
    # UPDATE MONTH SCHEDULE
    # =====================================================

    if months_changed:

        # NOTE:
        # Use months_data directly.
        # Do NOT use update_data["months"].

        existing_months = (
            db.query(ChitMonth)
            .filter(
                ChitMonth.chit_id == chit_id,
                ChitMonth.company_id == company_id,
            )
            .order_by(
                ChitMonth.month_number.asc()
            )
            .all()
        )

        existing_by_number = {
            month.month_number: month
            for month in existing_months
        }

        incoming_numbers = {
            month.month_number
            for month in months_data
        }

        # ---------------------------------------------
        # Update existing / create new
        # ---------------------------------------------

        for month_data in months_data:

            existing_month = existing_by_number.get(
                month_data.month_number
            )

            if existing_month:

                existing_month.month_date = (
                    month_data.month_date
                )

                existing_month.monthly_emi = (
                    month_data.monthly_emi
                )

                existing_month.monthly_lift_amount = (
                    month_data.monthly_lift_amount
                )

            else:

                new_month = ChitMonth(
                    company_id=company_id,
                    chit_id=chit.id,
                    month_number=(
                        month_data.month_number
                    ),
                    month_date=(
                        month_data.month_date
                    ),
                    monthly_emi=(
                        month_data.monthly_emi
                    ),
                    monthly_lift_amount=(
                        month_data.monthly_lift_amount
                    ),
                )

                db.add(new_month)

        # ---------------------------------------------
        # Delete old months that are no longer present
        # ---------------------------------------------

        for existing_month in existing_months:

            if (
                existing_month.month_number
                not in incoming_numbers
            ):
                db.delete(existing_month)

        # ---------------------------------------------
        # Keep group-level EMI synced
        # ---------------------------------------------

        chit.monthly_emi = (
            months_data[0].monthly_emi
        )

        db.flush()

    # =====================================================
    # FIRST TIME ACTIVATION
    # =====================================================

    if (
        old_status != "active"
        and new_status == "active"
    ):

        installment_result = (
            generate_installments_for_active_chit(
                db=db,
                company_id=company_id,
                chit_id=chit.id,
            )
        )

        if isinstance(
            installment_result,
            dict,
        ):

            error = installment_result.get(
                "error"
            )

            db.rollback()

            if error == "no_confirmed_members":
                return {
                    "error": "no_members"
                }

            if error == "chit_start_date_missing":
                return {
                    "error": "chit_start_date_missing"
                }

            if error == "chit_duration_missing":
                return {
                    "error": "chit_duration_missing"
                }

            if error == "chit_month_schedule_incomplete":
                return {
                    "error": "chit_month_schedule_incomplete"
                }

            if error == "installments_already_generated":
                return {
                    "error": "installments_already_generated"
                }

            return {
                "error": error
            }

    # =====================================================
    # ACTIVE CHIT + SCHEDULE UPDATE
    # =====================================================
    # No payment exists, so installments can be regenerated.

    elif (
        old_status == "active"
        and (
            start_date_changed
            or duration_changed
            or months_changed
        )
        and not has_payments
    ):

        installment_result = (
            regenerate_installments_for_active_chit(
                db=db,
                company_id=company_id,
                chit_id=chit.id,
            )
        )

        if isinstance(
            installment_result,
            dict,
        ):

            error = installment_result.get(
                "error"
            )

            if error:
                db.rollback()

                return {
                    "error": error
                }

    # =====================================================
    # COMMIT
    # =====================================================

    try:
        db.commit()

    except Exception:
        db.rollback()
        raise

    # =====================================================
    # REFRESH
    # =====================================================

    db.refresh(chit)

    return chit

# =========================================================
# DELETE CHIT
# =========================================================

def delete_chit_group(
    db: Session,
    company_id: int,
    chit_id: int
):

    chit = get_chit_group(
        db,
        company_id,
        chit_id
    )

    if not chit:
        return None

    db.delete(chit)

    db.commit()

    return True