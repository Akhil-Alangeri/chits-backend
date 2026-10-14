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

from app.schemas.chit_member import (
    ChitMemberCreate,
    ChitMemberUpdate,
    ChitMemberResponse,
)

from app.services.chit_member_service import (
    add_chit_member,
    get_chit_members as get_chit_members_service,
    get_chit_member,
    update_chit_member,
    remove_chit_member,
)
from app.services.audit_log_service import get_request_metadata


router = APIRouter(
    prefix="/chits",
    tags=["Chit Members"],
)


# =========================================================
# ADD MEMBER
# =========================================================

@router.post(
    "/{chit_id}/members",
    response_model=ChitMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    chit_id: int,
    member_data: ChitMemberCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    ip_address, user_agent = get_request_metadata(request)

    result = add_chit_member(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
        member_data=member_data,
        created_by=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


    if isinstance(result, dict):

        error = result.get("error")


        if error == "chit_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chit group not found.",
            )


        if error == "customer_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found in this company.",
            )


        if error == "chit_full":

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This chit has reached its maximum member capacity.",
            )


        if error == "member_number_exists":

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This member number already exists in this chit.",
            )


        if error == "chit_start_date_missing":

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chit start date is required.",
            )


        if error == "chit_duration_missing":

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chit duration must be greater than zero.",
            )


    return result


# =========================================================
# GET ALL CURRENT MEMBERS
# =========================================================

@router.get(
    "/{chit_id}/members",
    response_model=List[ChitMemberResponse],
)
def get_members(
    chit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    return get_chit_members_service(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
    )


# =========================================================
# GET SINGLE MEMBER
# =========================================================

@router.get(
    "/members/{member_id}",
    response_model=ChitMemberResponse,
)
def get_member(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    member = get_chit_member(
        db=db,
        company_id=current_user.company_id,
        member_id=member_id,
    )

    if not member:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chit member not found.",
        )

    return member


# =========================================================
# UPDATE MEMBER
# =========================================================

@router.put(
    "/members/{member_id}",
    response_model=ChitMemberResponse,
)
def update_member(
    member_id: int,
    member_data: ChitMemberUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    ip_address, user_agent = get_request_metadata(request)

    member = update_chit_member(
        db=db,
        company_id=current_user.company_id,
        member_id=member_id,
        member_data=member_data,
        updated_by=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if not member:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chit member not found.",
        )

    return member


# =========================================================
# REMOVE MEMBER FROM CHIT
# =========================================================

@router.delete(
    "/{chit_id}/members/{member_id}",
    response_model=ChitMemberResponse,
)
def remove_member(
    chit_id: int,
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    ip_address, user_agent = get_request_metadata(request)

    result = remove_chit_member(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
        member_id=member_id,
        removed_by=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


    if isinstance(result, dict):

        error = result.get("error")


        if error == "member_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found in this chit.",
            )


        if error == "member_already_removed":

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Member has already been removed from this chit.",
            )


    return result
