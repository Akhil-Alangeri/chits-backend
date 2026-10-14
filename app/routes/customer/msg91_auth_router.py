import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.customer.customer_auth import CustomerTokenResponse
from app.services.customer.msg91_auth.msg91_auth_schema import Msg91SendOtpRequest, Msg91VerifyOtpRequest, Msg91OtpResponse
from app.services.customer.msg91_auth import msg91_auth_service as service

router = APIRouter(prefix="/customer/msg91-auth", tags=["Customer MSG91 Authentication"])


async def send_response(db, mobile, resend=False):
    try:
        return await service.send(db, mobile, resend)
    except HTTPException as error:
        if error.status_code == 429 and isinstance(error.detail, dict):
            return JSONResponse(status_code=429, content={"detail": error.detail["message"], "retry_after": error.detail["retry_after"]}, headers=error.headers)
        raise


@router.post("/send-otp", response_model=Msg91OtpResponse)
def send_otp(request: Msg91SendOtpRequest, db: Session = Depends(get_db)):
    return asyncio.run(send_response(db, request.mobile_number))


@router.post("/resend-otp", response_model=Msg91OtpResponse)
def resend_otp(request: Msg91SendOtpRequest, db: Session = Depends(get_db)):
    return asyncio.run(send_response(db, request.mobile_number, True))


@router.post("/verify-otp", response_model=CustomerTokenResponse)
def verify_otp(request: Msg91VerifyOtpRequest, db: Session = Depends(get_db)):
    return asyncio.run(service.verify(db, request.mobile_number, request.otp))
