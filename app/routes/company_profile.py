from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    File,
    Form,
    Request,
    UploadFile,
)

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
from app.services.audit_log_service import (
    get_request_metadata,
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

# =========================================================
# UPDATE COMPANY PROFILE
# =========================================================

# =========================================================
# UPDATE COMPANY PROFILE
# =========================================================

@router.put(
    "/profile",
    response_model=CompanyProfileResponse
)
async def update_profile(

    request: Request,

    company_name: str = Form(...),

    email: str = Form(""),

    mobile: str = Form(""),

    address: str = Form(""),

    logo: UploadFile | None = File(None),

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    )

):

    ip_address, user_agent = get_request_metadata(request)

    result = await update_company_profile(
        db=db,
        user=current_user,
        company_name=company_name,
        email=email,
        mobile=mobile,
        address=address,
        logo=logo,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if result.get("error") == "company_not_found":

        raise HTTPException(
            status_code=404,
            detail="Company not found."
        )

    if result.get("error") == "invalid_logo_type":

        raise HTTPException(
            status_code=400,
            detail="Only PNG, JPEG and WEBP images are allowed."
        )

    if result.get("error") == "logo_too_large":

        raise HTTPException(
            status_code=400,
            detail="Logo size must be less than 2 MB."
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

    request: Request,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    )

):

    ip_address, user_agent = get_request_metadata(request)

    result = update_login_id(
        db=db,
        user=current_user,
        new_login_id=data.login_id,
        ip_address=ip_address,
        user_agent=user_agent,
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

    request: Request,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    )

):

    ip_address, user_agent = get_request_metadata(request)

    result = update_password(

        db=db,

        user=current_user,

        current_password=data.current_password,

        new_password=data.new_password,

        confirm_password=data.confirm_password,

        ip_address=ip_address,

        user_agent=user_agent,

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
