from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.models.admin.user import User

from app.schemas.chit_lift import (
    ChitLiftCreate,
    ChitLiftResponse,
    ChitLiftUpdate,
)

from app.services.chit_lift_service import (
    create_chit_lift,
    get_eligible_members_for_lift,
    get_chit_lifts,
    get_chit_lift,
    get_member_lifts,
    update_chit_lift,
)


router = APIRouter(
    prefix="/chit-lifts",
    tags=["Chit Lifts"],
)


# =========================================================
# GET ELIGIBLE MEMBERS
# =========================================================

@router.get(
    "/chits/{chit_id}/eligible-members",
)
def get_eligible_lift_members(
    chit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    result = get_eligible_members_for_lift(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
    )

    if isinstance(result, dict):
        error = result.get("error")

        if error == "chit_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chit not found.",
            )

        if error == "no_eligible_members":
            return []

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return result


# =========================================================
# CREATE CHIT LIFT
# =========================================================

@router.post(
    "/chits/{chit_id}/members/{member_id}",
    response_model=ChitLiftResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_lift(
    chit_id: int,
    member_id: int,
    lift_data: ChitLiftCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    result = create_chit_lift(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
        member_id=member_id,
        lift_data=lift_data,
    )

    if isinstance(result, dict):
        error = result.get("error")

        if error == "chit_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chit not found.",
            )

        if error == "member_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found.",
            )

        if error == "month_required":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get(
                    "message",
                    "Chit month is required.",
                ),
            )

        if error == "month_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chit month not found.",
            )

        if error == "member_already_lifted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This member/slot has already lifted "
                    "in this chit."
                ),
            )

        if error == "month_already_lifted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This month already has a lift winner."
                ),
            )

        if error == "lift_conflict":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=result.get(
                    "message",
                    "Lift conflict.",
                ),
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return result


# =========================================================
# GET ALL LIFTS FOR CHIT
# =========================================================

@router.get(
    "/chits/{chit_id}",
    response_model=list[ChitLiftResponse],
)
def get_lifts(
    chit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    result = get_chit_lifts(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
    )

    if isinstance(result, dict):
        if result.get("error") == "chit_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chit not found.",
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error"),
        )

    return result


# =========================================================
# GET SINGLE LIFT
# =========================================================

@router.get(
    "/chits/{chit_id}/{lift_id}",
    response_model=ChitLiftResponse,
)
def get_lift(
    chit_id: int,
    lift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    result = get_chit_lift(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
        lift_id=lift_id,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lift not found.",
        )

    return result


# =========================================================
# GET MEMBER LIFT HISTORY
# =========================================================

@router.get(
    "/chits/{chit_id}/members/{member_id}",
    response_model=list[ChitLiftResponse],
)
def get_member_lift_history(
    chit_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    result = get_member_lifts(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
        member_id=member_id,
    )

    if isinstance(result, dict):
        if result.get("error") == "member_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found.",
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error"),
        )

    return result


# =========================================================
# UPDATE CHIT LIFT
# =========================================================

@router.put(
    "/chits/{chit_id}/{lift_id}",
    response_model=ChitLiftResponse,
)
def update_lift(
    chit_id: int,
    lift_id: int,
    lift_data: ChitLiftUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    result = update_chit_lift(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
        lift_id=lift_id,
        lift_data=lift_data,
    )

    if isinstance(result, dict):
        error = result.get("error")

        if error == "lift_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lift not found.",
            )

        if error == "chit_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chit not found.",
            )

        if error == "member_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found.",
            )

        if error == "month_required":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get(
                    "message",
                    "Chit month is required.",
                ),
            )

        if error == "month_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chit month not found.",
            )

        if error == "edit_reason_required":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Edit reason is required.",
            )

        if error == "member_already_lifted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "The selected member/slot has already "
                    "lifted in this chit."
                ),
            )

        if error == "month_already_lifted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This month already has another "
                    "lift winner."
                ),
            )

        if error == "lift_conflict":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=result.get(
                    "message",
                    "Lift conflict.",
                ),
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return result