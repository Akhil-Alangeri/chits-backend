from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status
)

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.auth import (
    CompanyLoginRequest,
    CompanyLoginResponse
)

from app.services.auth_service import (
    authenticate_company
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post(
    "/company/login",
    response_model=CompanyLoginResponse
)
def company_login(
    login_data: CompanyLoginRequest,
    db: Session = Depends(get_db)
):

    result = authenticate_company(
        db,
        login_data.login_id,
        login_data.password
    )

    if result.get("error") in {"user_not_active", "company_not_found"}:
        raise HTTPException(status_code=403, detail="User account is not active or has no company.")

    # Invalid credentials
    if result.get("error") == "invalid_credentials":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login ID or password."
        )

    # Company not active
    if result.get("error") == "company_not_active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company account is not active."
        )

    # Credentials missing
    if result.get("error") == "credentials_not_configured":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Company login credentials are not configured."
        )

    

    return {
        "success": True,
        "message": "Login successful.",
        "access_token": result["access_token"],
        "token_type": "bearer",
        "company": result["company"]
    }
