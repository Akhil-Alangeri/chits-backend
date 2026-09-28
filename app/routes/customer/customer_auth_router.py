from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.schemas.customer.customer_auth import (
    CustomerSendOTPRequest,
    CustomerSendOTPResponse,
    CustomerVerifyOTPRequest,
    CustomerTokenResponse,
)

from app.services.customer.customer_auth_service import (
    send_customer_otp,
    verify_customer_otp,
)


router = APIRouter(
    prefix="/customer/auth",
    tags=["Customer Authentication"],
)


# =====================================================
# SEND OTP
# =====================================================

@router.post(
    "/send-otp",
    response_model=CustomerSendOTPResponse,
)
def send_otp(
    request: CustomerSendOTPRequest,
    db: Session = Depends(get_db),
):

    mobile = request.mobile.strip()

    try:

        result = send_customer_otp(
            db=db,
            mobile=mobile,
        )

    except ValueError as error:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        )

    return CustomerSendOTPResponse(
        success=True,
        message="OTP generated successfully.",
        otp_expires_in=result["otp_expires_in"],
        development_otp=result["development_otp"],
    )


# =====================================================
# VERIFY OTP
# =====================================================

@router.post(
    "/verify-otp",
    response_model=CustomerTokenResponse,
)
def verify_otp(
    request: CustomerVerifyOTPRequest,
    db: Session = Depends(get_db),
):

    try:

        customer, access_token = verify_customer_otp(
            db=db,
            mobile=request.mobile.strip(),
            otp=request.otp.strip(),
        )

    except ValueError as error:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        )

    return CustomerTokenResponse(
        success=True,
        message="Login successful.",
        access_token=access_token,
        token_type="bearer",
        expires_in=24 * 60 * 60,
    )