import math
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.security import create_access_token
from app.services.customer.customer_auth_service import get_customer_by_mobile
from app.services.customer.msg91_auth.msg91_cooldown import locked_state
from app.services.customer.msg91_auth import msg91_otp_service as provider


def eligible_customer(db: Session, mobile: str):
    customer = get_customer_by_mobile(db, mobile)
    if not customer:
        raise HTTPException(401, "Customer is not eligible for login.")
    return customer


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def send(db: Session, mobile: str, resend: bool = False):
    try:
        eligible_customer(db, mobile)
        state = locked_state(db, mobile)
        now = utcnow()
        if state.next_send_at and state.next_send_at > now:
            remaining = max(1, math.ceil((state.next_send_at - now).total_seconds()))
            raise HTTPException(429, {"message": "Please wait before requesting another OTP.", "retry_after": remaining}, headers={"Retry-After": str(remaining)})
        if resend and not state.sent_at:
            raise HTTPException(400, "Please request an OTP first.")
        # Reserve before the network call, so a timeout/restart cannot bypass
        # the cooldown after a potentially delivered SMS. Never store the OTP.
        state.next_send_at = now + timedelta(seconds=60)
        state.active = False
        state.attempts = 0
        db.commit()
        request_id = await provider.send_otp(mobile)
        state = locked_state(db, mobile)
        state.sent_at = utcnow()
        state.next_send_at = state.sent_at + timedelta(seconds=60)
        state.active = True
        state.attempts = 0
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return {"success": True, "message": "OTP resent successfully." if resend else "OTP sent successfully.", "resend_after": 60, "request_id": request_id}


async def verify(db: Session, mobile: str, otp: str):
    try:
        state = locked_state(db, mobile)
        if not state.active or not state.sent_at or utcnow() >= state.sent_at + timedelta(minutes=10):
            raise HTTPException(401, "Invalid or expired OTP.")
        if state.attempts >= 5:
            raise HTTPException(429, "Too many incorrect OTP attempts. Please request a new OTP.")
        try:
            await provider.verify_otp(mobile, otp)
        except HTTPException as error:
            if error.status_code == 401:
                state.attempts += 1
                db.commit()
            raise
        customer = eligible_customer(db, mobile)
        token = create_access_token(data={
            "sub": f"customer:{customer.id}", "customer_profile_id": customer.id,
            "customer_code": customer.customer_code, "token_type": "customer",
        }, expires_minutes=24 * 60)
        state.active = False
        db.commit()
        return {"success": True, "message": "Login successful.", "access_token": token, "token_type": "bearer", "expires_in": 86400}
    except BaseException:
        db.rollback()
        raise
