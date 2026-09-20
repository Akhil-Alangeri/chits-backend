from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.admin.user import User

from app.schemas.company_profile import (
    CompanyProfileUpdate,
    CompanyProfileResponse,

    LoginIdUpdate,
    LoginIdUpdateResponse,

    PasswordUpdate,
    PasswordUpdateResponse,
)

from app.services.company_profile_service import (
    get_company_profile,
    update_company_profile,
    update_login_id,
    update_password,
)


router = APIRouter(
    prefix="/company",
    tags=["Company Profile"]
)


# =========================================================
# GET COMPANY PROFILE
# =========================================================

@router.get(
    "/profile",
    response_model=CompanyProfileResponse
)
def get_profile(

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    )

):

    result = get_company_profile(
        db=db,
        user=current_user
    )


    if result.get("error") == "company_not_found":

        raise HTTPException(
            status_code=404,
            detail="Company not found."
        )


    return {
        "success": True,
        "message": "Company profile retrieved successfully.",
        "data": result
    }


# =========================================================
# UPDATE COMPANY PROFILE
# =========================================================

@router.put(
    "/profile",
    response_model=CompanyProfileResponse
)
def update_profile(

    data: CompanyProfileUpdate,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    )

):

    result = update_company_profile(
        db=db,
        user=current_user,
        data=data
    )


    if result.get("error") == "company_not_found":

        raise HTTPException(
            status_code=404,
            detail="Company not found."
        )


    return {
        "success": True,
        "message": "Company profile updated successfully.",
        "data": result
    }


# =========================================================
# UPDATE LOGIN ID
# =========================================================

@router.put(
    "/profile/login-id",
    response_model=LoginIdUpdateResponse
)
def change_login_id(

    data: LoginIdUpdate,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    )

):

    result = update_login_id(
        db=db,
        user=current_user,
        new_login_id=data.login_id
    )


    if result.get("error") == "same_login_id":

        raise HTTPException(
            status_code=400,
            detail="New Login ID is same as current Login ID."
        )


    if result.get("error") == "login_id_already_exists":

        raise HTTPException(
            status_code=409,
            detail="Login ID already exists."
        )


    return {
        "success": True,
        "message": "Login ID updated successfully.",
        "login_id": result["login_id"]
    }


# =========================================================
# UPDATE PASSWORD
# =========================================================

@router.put(
    "/profile/password",
    response_model=PasswordUpdateResponse
)
def change_password(

    data: PasswordUpdate,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    )

):

    result = update_password(

        db=db,

        user=current_user,

        current_password=data.current_password,

        new_password=data.new_password,

        confirm_password=data.confirm_password

    )


    if result.get("error") == "invalid_current_password":

        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect."
        )


    if result.get("error") == "password_mismatch":

        raise HTTPException(
            status_code=400,
            detail="New password and confirm password do not match."
        )


    if result.get("error") == "same_password":

        raise HTTPException(
            status_code=400,
            detail="New password must be different from current password."
        )


    return {
        "success": True,
        "message": "Password updated successfully."
    }