from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.otp_service import (
    send_mobile_otp,
    verify_mobile_otp,
)


router = APIRouter(
    prefix="/customer/auth",
    tags=["Customer Auth"],
)


class SendOtpRequest(BaseModel):
    mobile_number: str


class VerifyOtpRequest(BaseModel):
    mobile_number: str
    otp: str
    
    
@router.post("/send-otp")
async def send_otp(
    payload: SendOtpRequest,
    db: Session = Depends(get_db),
):
    mobile = payload.mobile_number.strip()

    customer = (
        db.query(Customer)
        .filter(
            Customer.mobile_number == mobile
        )
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )


    await send_mobile_otp(mobile)


    return {
        "success": True,
        "message": "OTP sent successfully.",
    }
    
    
@router.post("/verify-otp")
async def verify_otp(
    payload: VerifyOtpRequest,
    db: Session = Depends(get_db),
):
    mobile = payload.mobile_number.strip()

    customer = (
        db.query(Customer)
        .filter(
            Customer.mobile_number == mobile
        )
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )


    verified = await verify_mobile_otp(
        mobile=mobile,
        otp=payload.otp,
    )


    if not verified:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OTP.",
        )


    # Existing JWT creation logic
    token = create_customer_access_token(
        customer
    )


    return {
        "success": True,
        "message": "Login successful.",
        "access_token": token,
        "token_type": "bearer",
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "mobile_number":
                customer.mobile_number,
        },
    }