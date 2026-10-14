from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
    Form,
    File,
    UploadFile,
)
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db

from app.schemas.company import (
    CompanyCreate,
    CompanyResponse
)
from app.schemas.company import CompanyStatusUpdate
from app.services.company_service import change_company_status

from app.services.company_service import (
    create_company,
    get_all_companies,
    get_pending_companies,
    get_company_details,
    approve_company,
)

from app.services.email_service import (
    send_company_credentials
)
from app.services.audit_log_service import (
    get_request_metadata,
)


router = APIRouter(
    prefix="/companies",
    tags=["Companies"]
)


@router.patch("/{company_id}/status", response_model=CompanyResponse)
def update_company_status(company_id: int, data: CompanyStatusUpdate, request: Request,
                          db: Session = Depends(get_db)):
    ip_address, user_agent = get_request_metadata(request)
    return change_company_status(db, company_id, data.status, ip_address, user_agent)


# =========================================================
# REGISTER COMPANY
# =========================================================

@router.post(
    "/register",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED
)
def register_company(
    request: Request,
    company_name: str = Form(...),
    mobile: str = Form(...),
    email: str = Form(...),
    address: str = Form(...),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db)
):

    ip_address, user_agent = get_request_metadata(request)

    result = create_company(
        db=db,
        company_name=company_name,
        mobile=mobile,
        email=email,
        address=address,
        logo=logo,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if isinstance(result, dict):

        if result.get("error") == "mobile_exists":
            raise HTTPException(
                status_code=409,
                detail="Mobile number is already registered."
            )

        if result.get("error") == "email_exists":
            raise HTTPException(
                status_code=409,
                detail="Email address is already registered."
            )

        if result.get("error") == "invalid_logo_type":
            raise HTTPException(
                status_code=400,
                detail="Only PNG and JPG images are allowed."
            )

        if result.get("error") == "logo_too_large":
            raise HTTPException(
                status_code=400,
                detail="Logo size must not exceed 2 MB."
            )

    return result
# =========================================================
# GET ALL COMPANIES
# =========================================================

@router.get(
    "",
    response_model=List[CompanyResponse]
)
def get_companies(
    db: Session = Depends(get_db)
):

    return get_all_companies(db)


# =========================================================
# GET PENDING COMPANIES
# =========================================================

@router.get(
    "/requests",
    response_model=List[CompanyResponse]
)
def get_company_requests(
    db: Session = Depends(get_db)
):

    return get_pending_companies(db)


# =========================================================
# GET COMPANY DETAILS
# =========================================================

@router.get(
    "/{company_id}",
    response_model=CompanyResponse
)
def get_company(
    company_id: int,
    db: Session = Depends(get_db)
):
    company = get_company_details(
        db,
        company_id
    )
    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found."
        )
    return company
# =========================================================
# APPROVE COMPANY
# =========================================================

@router.put(
    "/{company_id}/approve"
)
async def approve_company_registration(
    company_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    ip_address, user_agent = get_request_metadata(request)

    result = approve_company(
        db,
        company_id,
        ip_address,
        user_agent,
    )
    # Company not found
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Company not found."
        )
    # Company already processed
    if isinstance(result, dict):
        if result.get("error") == "already_processed":
            raise HTTPException(
                status_code=400,
                detail="Company is already processed."
            )

    # =====================================================
    # SEND LOGIN CREDENTIALS
    # =====================================================

    await send_company_credentials(
        recipient_email=result["company"].email,
        company_name=result["company"].company_name,
        login_id=result["login_id"],
        temporary_password=result["password"],
    )
    return {
        "success": True,
        "message":
            "Company approved and login credentials sent.",
        "login_id":
            result["login_id"]
    }
