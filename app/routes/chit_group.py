from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.admin.user import User

from app.schemas.chit_group import (
    ChitGroupCreate,
    ChitGroupUpdate,
    ChitGroupResponse,
)

from app.services.chit_group_service import (
    create_chit_group,
    get_all_chit_groups,
    get_chit_group,
    update_chit_group,
    delete_chit_group,
    auto_complete_expired_chits,
)
from app.services.audit_log_service import get_request_metadata


router = APIRouter(
    prefix="/chits",
    tags=["Chit Groups"],
)


# =========================================================
# CREATE CHIT
# =========================================================

@router.post(
    "",
    response_model=ChitGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chit(
    chit_data: ChitGroupCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    ip_address, user_agent = get_request_metadata(request)

    result = create_chit_group(
        db,
        current_user.company_id,
        chit_data,
        created_by=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if isinstance(result, dict):

        error = result.get("error")

        if error == "company_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found.",
            )

        if error == "start_date_required":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chit start date is required.",
            )

        if error == "months_count_mismatch":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Monthly schedule count must match the chit duration.",
            )

        if error == "invalid_month_numbers":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid monthly schedule numbers.",
            )

        if error == "invalid_month_date":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid month date for month "
                    f"{result.get('month_number', '')}."
                ),
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Unable to create chit group.",
        )

    return result


# =========================================================
# GET ALL CHITS
# =========================================================

@router.get(
    "",
    response_model=List[ChitGroupResponse],
)
def get_chits(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    # Immediate safety check so the UI never needs to wait for the
    # hourly background worker to reflect an expired chit.
    auto_complete_expired_chits(
        db=db,
        company_id=current_user.company_id,
    )

    return get_all_chit_groups(
        db,
        current_user.company_id,
    )


# =========================================================
# GET SINGLE CHIT
# =========================================================

@router.get(
    "/{chit_id}",
    response_model=ChitGroupResponse,
)
def get_chit(
    chit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    auto_complete_expired_chits(
        db=db,
        company_id=current_user.company_id,
    )

    chit = get_chit_group(
        db,
        current_user.company_id,
        chit_id,
    )

    if not chit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chit group not found.",
        )

    return chit


# =========================================================
# UPDATE CHIT
# =========================================================

@router.put(
    "/{chit_id}",
    response_model=ChitGroupResponse,
)
def update_chit(
    chit_id: int,
    chit_data: ChitGroupUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    ip_address, user_agent = get_request_metadata(request)

    result = update_chit_group(
        db,
        current_user.company_id,
        chit_id,
        chit_data,
        updated_by=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # =====================================================
    # CHIT NOT FOUND
    # =====================================================

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chit group not found.",
        )

    # =====================================================
    # BUSINESS ERRORS
    # =====================================================

    if isinstance(result, dict):

        error = result.get("error")

        error_messages = {
            "no_members": (
                "At least one member is required to activate the chit."
            ),
            "chit_start_date_missing": (
                "Chit start date is required before activating the chit."
            ),
            "chit_duration_missing": (
                "Chit duration must be greater than zero."
            ),
            "chit_month_schedule_incomplete": (
                "Chit monthly schedule is incomplete."
            ),
            "months_required": (
                "Monthly schedule is required."
            ),
            "invalid_duration": (
                "Chit duration must be greater than zero."
            ),
            "months_count_mismatch": (
                "Monthly schedule count must match the chit duration."
            ),
            "invalid_month_numbers": (
                "Invalid monthly schedule numbers."
            ),
            "start_date_required": (
                "Chit start date is required."
            ),
            "installments_already_generated": (
                "Installments have already been generated for this chit."
            ),
            "cannot_change_duration_after_payment": (
                "Duration cannot be changed after a payment has been recorded."
            ),
            "cannot_change_max_members_after_payment": (
                "Maximum members cannot be changed after a payment has been recorded."
            ),
            "cannot_change_chit_value_after_payment": (
                "Chit value cannot be changed after a payment has been recorded."
            ),
            "cannot_change_monthly_emi_after_payment": (
                "Monthly EMI cannot be changed after a payment has been recorded."
            ),
            "cannot_change_month_schedule_after_payment": (
                "Monthly EMI or planned lift amounts cannot be changed after a payment has been recorded."
            ),
            "chit_not_found": (
                "Chit group not found."
            ),
            "invalid_monthly_emi": (
                "Invalid monthly EMI."
            ),
            "invalid_monthly_lift_amount": (
                "Invalid planned lift amount."
            ),
            "invalid_month_date": (
                "Invalid monthly schedule date."
            ),
        }

        detail = error_messages.get(
            error,
            "Unable to update chit group.",
        )

        if error in {
            "cannot_change_duration_after_payment",
            "cannot_change_max_members_after_payment",
            "cannot_change_chit_value_after_payment",
            "cannot_change_monthly_emi_after_payment",
            "cannot_change_month_schedule_after_payment",
        }:
            status_code = status.HTTP_409_CONFLICT
        elif error == "chit_not_found":
            status_code = status.HTTP_404_NOT_FOUND
        else:
            status_code = status.HTTP_400_BAD_REQUEST

        raise HTTPException(
            status_code=status_code,
            detail=detail,
        )

    return result


# =========================================================
# DELETE CHIT
# =========================================================

@router.delete(
    "/{chit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_chit(
    chit_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    ip_address, user_agent = get_request_metadata(request)

    deleted = delete_chit_group(
        db,
        current_user.company_id,
        chit_id,
        deleted_by=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chit group not found.",
        )

    return None
