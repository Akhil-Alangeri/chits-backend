from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
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
)


router = APIRouter(
    prefix="/chits",
    tags=["Chit Groups"]
)


# =========================================================
# CREATE CHIT
# =========================================================

@router.post(
    "",
    response_model=ChitGroupResponse,
    status_code=status.HTTP_201_CREATED
)
def create_chit(
    chit_data: ChitGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    result = create_chit_group(
        db,
        current_user.company_id,
        chit_data
    )

    if isinstance(result, dict):

        if result.get("error") == "company_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found."
            )

    return result


# =========================================================
# GET ALL CHITS
# =========================================================

@router.get(
    "",
    response_model=List[ChitGroupResponse]
)
def get_chits(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return get_all_chit_groups(
        db,
        current_user.company_id
    )


# =========================================================
# GET SINGLE CHIT
# =========================================================

@router.get(
    "/{chit_id}",
    response_model=ChitGroupResponse
)
def get_chit(
    chit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    chit = get_chit_group(
        db,
        current_user.company_id,
        chit_id
    )

    if not chit:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chit group not found."
        )

    return chit


# =========================================================
# UPDATE CHIT
# =========================================================


@router.put(
    "/{chit_id}",
    response_model=ChitGroupResponse
)
def update_chit(
    chit_id: int,
    chit_data: ChitGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    result = update_chit_group(
        db,
        current_user.company_id,
        chit_id,
        chit_data
    )

    # =====================================================
    # CHIT NOT FOUND
    # =====================================================

    if result is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chit group not found."
        )

    # =====================================================
    # BUSINESS ERRORS
    # =====================================================

    if isinstance(result, dict):

        error = result.get("error")

        if error == "no_members":

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one member is required to activate the chit."
            )

        if error == "chit_start_date_missing":

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chit start date is required before activating the chit."
            )

        if error == "chit_duration_missing":

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chit duration must be greater than zero."
            )

        if error == "installments_already_generated":

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Installments have already been generated for this chit."
            )

        if error == "chit_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chit group not found."
            )

    

    if error == "cannot_change_month_schedule_after_payment":

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot change the monthly schedule after a payment has been made."
        )   
        
    return result 


# =========================================================
# DELETE CHIT
# =========================================================

@router.delete(
    "/{chit_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_chit(
    chit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    deleted = delete_chit_group(
        db,
        current_user.company_id,
        chit_id
    )

    if not deleted:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chit group not found."
        )

    return None