from datetime import date

from sqlalchemy.orm import Session
from dateutil.relativedelta import relativedelta
from app.services.chit_installment_service import add_months
from app.models.admin.payment_transaction import PaymentTransaction
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_months import ChitMonth
from app.models.admin.company import Company
from app.services.audit_log_service import create_audit_log, snapshot_model


from app.schemas.chit_group import (
    ChitGroupCreate,
    ChitGroupUpdate,
)

from app.services.chit_installment_service import (
    generate_installments_for_active_chit,
)


CHIT_GROUP_AUDIT_FIELDS = [
    "id",
    "name",
    "code",
    "chit_value",
    "monthly_emi",
    "duration_months",
    "max_members",
    "start_date",
    "status",
]

CHIT_MONTH_AUDIT_FIELDS = [
    "id",
    "month_number",
    "month_date",
    "monthly_emi",
    "monthly_lift_amount",
]


def _chit_group_audit_snapshot(
    db: Session,
    chit: ChitGroup,
) -> dict:
    values = snapshot_model(
        chit,
        CHIT_GROUP_AUDIT_FIELDS,
    )

    months = (
        db.query(ChitMonth)
        .filter(
            ChitMonth.chit_id == chit.id,
            ChitMonth.company_id == chit.company_id,
        )
        .order_by(ChitMonth.month_number.asc())
        .all()
    )

    values["months"] = [
        snapshot_model(month, CHIT_MONTH_AUDIT_FIELDS)
        for month in months
    ]

    return values


# =========================================================
# GENERATE CHIT CODE
# =========================================================

def generate_chit_code(
    db: Session,
    company_id: int,
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
    chit_data: ChitGroupCreate,
    created_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
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
        db.add(chit)

        db.flush()

        create_audit_log(
            db=db,
            company_id=company_id,
            user_id=created_by,
            action="CREATE",
            module="Chit Groups",
            entity_type="ChitGroup",
            entity_id=chit.id,
            description=f"Created chit group '{chit.name}'",
            new_values=_chit_group_audit_snapshot(
                db,
                chit,
            ),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.commit()
        db.refresh(chit)

        return chit


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
# AUTO-COMPLETE EXPIRED CHITS
# =========================================================

def auto_complete_expired_chits(
    db: Session,
    company_id: int | None = None,
) -> int:
    """
    Automatically mark active chits as completed after their
    configured duration has fully elapsed.

    Completion date = start_date + duration_months.

    Example:
        start_date = 2026-08-01
        duration  = 25 months
        completion date = 2028-09-01

    Existing payment/installment records are never modified here.
    Only the ChitGroup.status is changed.
    """

    query = db.query(ChitGroup).filter(
        ChitGroup.status == "active",
        ChitGroup.start_date.isnot(None),
        ChitGroup.duration_months.isnot(None),
        ChitGroup.duration_months > 0,
    )

    if company_id is not None:
        query = query.filter(
            ChitGroup.company_id == company_id
        )

    chits = query.all()

    today = date.today()
    completed_count = 0

    for chit in chits:
        completion_date = add_months(
            chit.start_date,
            int(chit.duration_months),
        )

        if today >= completion_date:
            chit.status = "completed"
            completed_count += 1

    if completed_count:
        db.commit()

    return completed_count



# =========================================================
# UPDATE CHIT
# =========================================================

def update_chit_group(
    db: Session,
    company_id: int,
    chit_id: int,
    chit_data: ChitGroupUpdate,
    updated_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
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

    old_values = _chit_group_audit_snapshot(
        db,
        chit,
    )

    # =====================================================
    # GET BASIC UPDATE DATA
    # =====================================================

    update_data = chit_data.model_dump(
        exclude_unset=True,
        exclude={"months"},
    )

    # =====================================================
    # MONTH SCHEDULE PAYLOAD
    # =====================================================

    months_requested = (
        chit_data.months is not None
    )

    months_data = (
        chit_data.months
        if months_requested
        else None
    )

    # =====================================================
    # STATUS
    # =====================================================

    old_status = chit.status

    new_status = update_data.get(
        "status",
        old_status,
    )

    # =====================================================
    # IMPORTANT FIELD CHANGES
    # =====================================================

    start_date_changed = (
        "start_date" in update_data
        and update_data["start_date"] != chit.start_date
    )

    duration_changed = (
        "duration_months" in update_data
        and update_data["duration_months"] != chit.duration_months
    )

    max_members_changed = (
        "max_members" in update_data
        and update_data["max_members"] != chit.max_members
    )

    chit_value_changed = (
        "chit_value" in update_data
        and update_data["chit_value"] != chit.chit_value
    )

    monthly_emi_changed = (
        "monthly_emi" in update_data
        and update_data["monthly_emi"] != chit.monthly_emi
    )

    # =====================================================
    # CHECK EXISTING PAYMENTS
    # =====================================================
    # Do not depend on chit.status. Payment history itself
    # determines whether financial/schedule changes are locked.

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
    # CHECK ACTUAL MONTH SCHEDULE CHANGES
    # =====================================================

    schedule_changed = False
    schedule_amounts_changed = False

    if months_requested:

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

        if len(existing_months) != len(months_data):
            schedule_changed = True
            schedule_amounts_changed = True
        else:
            existing_by_number = {
                month.month_number: month
                for month in existing_months
            }

            for month_data in months_data:

                existing = existing_by_number.get(
                    month_data.month_number
                )

                if existing is None:
                    schedule_changed = True
                    schedule_amounts_changed = True
                    break

                # Start-date-driven month date shift is allowed.
                if existing.month_date != month_data.month_date:
                    schedule_changed = True

                # EMI / lift amount changes are financial changes.
                if existing.monthly_emi != month_data.monthly_emi:
                    schedule_changed = True
                    schedule_amounts_changed = True

                if (
                    existing.monthly_lift_amount
                    != month_data.monthly_lift_amount
                ):
                    schedule_changed = True
                    schedule_amounts_changed = True

    # =====================================================
    # PROTECT FINANCIAL / STRUCTURAL CHANGES AFTER PAYMENT
    # =====================================================
    # Start date is intentionally NOT protected.
    # It may shift the entire calendar forward/backward while
    # preserving the same installment + payment relationship.

    protected_change_after_payment = (
        duration_changed
        or max_members_changed
        or chit_value_changed
        or monthly_emi_changed
        or schedule_amounts_changed
    )

    if has_payments and protected_change_after_payment:

        db.rollback()

        if duration_changed:
            return {
                "error":
                    "cannot_change_duration_after_payment"
            }

        if max_members_changed:
            return {
                "error":
                    "cannot_change_max_members_after_payment"
            }

        if chit_value_changed:
            return {
                "error":
                    "cannot_change_chit_value_after_payment"
            }

        if monthly_emi_changed:
            return {
                "error":
                    "cannot_change_monthly_emi_after_payment"
            }

        if schedule_amounts_changed:
            return {
                "error":
                    "cannot_change_month_schedule_after_payment"
            }

    # =====================================================
    # VALIDATE MONTH SCHEDULE
    # =====================================================

    if months_requested:

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

        if not start_date:
            return {
                "error": "start_date_required"
            }

        if not duration or duration <= 0:
            return {
                "error": "invalid_duration"
            }

        if len(months_data) != duration:
            return {
                "error": "months_count_mismatch"
            }

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

        for index, month_data in enumerate(months_data):

            expected_date = (
                start_date
                + relativedelta(months=index)
            )

            if month_data.month_date != expected_date:
                return {
                    "error": "invalid_month_date",
                    "month_number": month_data.month_number,
                }

            if (
                month_data.monthly_emi is None
                or month_data.monthly_emi <= 0
            ):
                return {
                    "error": "invalid_monthly_emi",
                    "month_number": month_data.month_number,
                }

            if (
                month_data.monthly_lift_amount is None
                or month_data.monthly_lift_amount <= 0
            ):
                return {
                    "error": "invalid_monthly_lift_amount",
                    "month_number": month_data.month_number,
                }

        # Keep group-level EMI synced to month 1.
        update_data["monthly_emi"] = (
            months_data[0].monthly_emi
        )

    # =====================================================
    # STATUS ACTIVATION VALIDATION
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

        final_duration = update_data.get(
            "duration_months",
            chit.duration_months,
        )

        existing_month_count = (
            db.query(ChitMonth)
            .filter(
                ChitMonth.chit_id == chit_id,
                ChitMonth.company_id == company_id,
            )
            .count()
        )

        if months_requested:
            final_month_count = len(months_data)
        else:
            final_month_count = existing_month_count

        if final_month_count != final_duration:
            return {
                "error":
                    "chit_month_schedule_incomplete"
            }

        final_start_date = update_data.get(
            "start_date",
            chit.start_date,
        )

        if not final_start_date:
            return {
                "error": "chit_start_date_missing"
            }

        if not final_duration or final_duration <= 0:
            return {
                "error": "chit_duration_missing"
            }

    # =====================================================
    # APPLY BASIC CHIT UPDATE
    # =====================================================

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

    if months_requested:

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

                db.add(
                    ChitMonth(
                        company_id=company_id,
                        chit_id=chit.id,
                        month_number=month_data.month_number,
                        month_date=month_data.month_date,
                        monthly_emi=month_data.monthly_emi,
                        monthly_lift_amount=(
                            month_data.monthly_lift_amount
                        ),
                    )
                )

        for existing_month in existing_months:
            if (
                existing_month.month_number
                not in incoming_numbers
            ):
                db.delete(existing_month)

        chit.monthly_emi = (
            months_data[0].monthly_emi
        )

        db.flush()

    # =====================================================
    # START DATE CHANGE + EXISTING PAYMENTS
    # =====================================================
    # Keep the same ChitInstallment rows so all PaymentTransaction
    # records remain attached to the exact same installment IDs.

    if start_date_changed and has_payments:

        new_start_date = chit.start_date

        installments = (
            db.query(ChitInstallment)
            .join(
                ChitMember,
                ChitMember.id
                == ChitInstallment.chit_member_id,
            )
            .filter(
                ChitMember.chit_id == chit_id,
            )
            .order_by(
                ChitInstallment.chit_member_id.asc(),
                ChitInstallment.installment_number.asc(),
            )
            .all()
        )

        for installment in installments:

            installment.due_date = add_months(
                new_start_date,
                int(installment.installment_number) - 1,
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

        if isinstance(installment_result, dict):

            error = installment_result.get(
                "error"
            )

            db.rollback()

            if error == "no_confirmed_members":
                return {"error": "no_members"}

            if error == "chit_start_date_missing":
                return {
                    "error":
                        "chit_start_date_missing"
                }

            if error == "chit_duration_missing":
                return {
                    "error":
                        "chit_duration_missing"
                }

            if error == "chit_month_schedule_incomplete":
                return {
                    "error":
                        "chit_month_schedule_incomplete"
                }

            return {
                "error": error
            }

    # =====================================================
    # ACTIVE CHIT + CHANGES + NO PAYMENTS
    # =====================================================
    # It is safe to regenerate installment rows because no
    # PaymentTransaction references exist yet.

    elif (
        old_status == "active"
        and (
            start_date_changed
            or duration_changed
            or schedule_changed
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

        if isinstance(installment_result, dict):

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
        db.flush()

        new_values = _chit_group_audit_snapshot(
            db,
            chit,
        )

        if old_values != new_values:
            status_changed = (
                old_values["status"]
                != new_values["status"]
            )

            create_audit_log(
                db=db,
                company_id=company_id,
                user_id=updated_by,
                action=(
                    "STATUS_CHANGE"
                    if status_changed
                    else "UPDATE"
                ),
                module="Chit Groups",
                entity_type="ChitGroup",
                entity_id=chit.id,
                description=(
                    f"Changed chit group '{chit.name}' status "
                    f"from '{old_values['status']}' "
                    f"to '{new_values['status']}'"
                    if status_changed
                    else f"Updated chit group '{chit.name}'"
                ),
                old_values=old_values,
                new_values=new_values,
                ip_address=ip_address,
                user_agent=user_agent,
            )

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
    chit_id: int,
    deleted_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
):

    chit = get_chit_group(
        db,
        company_id,
        chit_id
    )

    if not chit:
        return None

    old_values = _chit_group_audit_snapshot(
        db,
        chit,
    )

    db.delete(chit)

    db.flush()

    create_audit_log(
        db=db,
        company_id=company_id,
        user_id=deleted_by,
        action="DELETE",
        module="Chit Groups",
        entity_type="ChitGroup",
        entity_id=chit_id,
        description=f"Deleted chit group '{old_values['name']}'",
        old_values=old_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()

    return True
