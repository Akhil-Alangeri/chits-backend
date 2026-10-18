"""Platform authentication and single-use, server-bound SMS password recovery."""
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import SECRET_KEY, hash_password, verify_password, create_access_token, decode_access_token
from app.models.admin.user import User

router = APIRouter(prefix="/super-admin/auth", tags=["Super Admin authentication"])
bearer = HTTPBearer(auto_error=False)

class Login(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=72)

class Recovery(BaseModel):
    username: str = Field(min_length=1, max_length=50)

class Reset(Recovery):
    otp: str = Field(pattern=r"^[0-9]{6}$")
    new_password: str = Field(min_length=8, max_length=72)

class Change(BaseModel):
    current_password: str = Field(max_length=72)
    new_password: str = Field(min_length=8, max_length=72)

def password_hash(password):
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(422, "Password must be at most 72 UTF-8 bytes.")
    return hash_password(password)

def find_admin(db, username):
    return db.query(User).filter(User.login_id == username, User.role == "super_admin",
                                 User.company_id.is_(None), User.status == "active").with_for_update().first()

def require_super_admin(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    payload = decode_access_token(credentials.credentials) if credentials else None
    if not payload or payload.get("token_type") != "super_admin" or not str(payload.get("sub", "")).isdigit():
        raise HTTPException(401, "Invalid or expired Super Admin session.")
    user = db.query(User).filter(User.id == int(payload["sub"]), User.role == "super_admin",
                                 User.company_id.is_(None), User.status == "active").with_for_update().first()
    if not user or payload.get("session_version") != user.session_version:
        raise HTTPException(401, "Invalid or expired Super Admin session.")
    return user

def invalidate(user):
    user.session_version += 1
    user.failed_attempts = 0
    user.locked_until = None
    user.reset_hash = None
    user.reset_expires = None
    user.reset_attempts = 0

@router.post("/login")
def login(data: Login, db: Session = Depends(get_db)):
    user = find_admin(db, data.username)
    now = datetime.utcnow()
    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(429, "Account temporarily locked. Try again later.")
    if len(data.password.encode("utf-8")) > 72 or not user or not verify_password(data.password, user.password_hash):
        if user:
            user.failed_attempts += 1
            if user.failed_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)
                user.failed_attempts = 0
            db.commit()
        raise HTTPException(401, "Invalid username or password.")
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    token = create_access_token({"sub": str(user.id), "token_type": "super_admin", "session_version": user.session_version}, expires_minutes=60)
    db.commit()
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me")
def me(user=Depends(require_super_admin)):
    return {"username": user.login_id}

@router.post("/logout")
def logout(user=Depends(require_super_admin), db: Session = Depends(get_db)):
    user.session_version += 1
    db.commit()
    return {"message": "Signed out."}

@router.post("/change-password")
def change(data: Change, user=Depends(require_super_admin), db: Session = Depends(get_db)):
    if len(data.current_password.encode("utf-8")) > 72 or not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    user.password_hash = password_hash(data.new_password)
    invalidate(user)
    db.commit()
    return {"message": "Password updated. Sign in with your new password."}

def recovery_mobile(username):
    mobile = os.getenv("SUPER_ADMIN_RESET_MOBILE", "")
    if username != os.getenv("SUPER_ADMIN_RESET_USERNAME", "admin") or not re.fullmatch(r"[6-9][0-9]{9}", mobile):
        return None
    return mobile

def otp_digest(username, mobile, otp):
    return hmac.new(SECRET_KEY.encode(), f"super-admin-reset:{username}:{mobile}:{otp}".encode(), hashlib.sha256).hexdigest()

@router.post("/forgot-password")
async def forgot(data: Recovery, db: Session = Depends(get_db)):
    user = find_admin(db, data.username)
    mobile = recovery_mobile(data.username)
    if not user or not mobile:
        raise HTTPException(400, "Password recovery is unavailable for this account. Contact the administrator.")
    now = datetime.utcnow()
    if user.reset_sent_at and now - user.reset_sent_at < timedelta(seconds=60):
        raise HTTPException(429, "Please wait 60 seconds before requesting another OTP.")
    if user.reset_expires and user.reset_expires > now and user.reset_attempts >= 5:
        raise HTTPException(429, "Too many attempts. Try again after 10 minutes.")
    key, template = os.getenv("MSG91_AUTH_KEY"), os.getenv("SUPER_ADMIN_MSG91_TEMPLATE_ID") or os.getenv("MSG91_TEMPLATE_ID")
    if not key or not template:
        raise HTTPException(503, "OTP service is not configured.")
    otp = f"{secrets.randbelow(1000000):06d}"
    user.reset_hash = otp_digest(data.username, mobile, otp)
    user.reset_sent_at = now
    user.reset_expires = now + timedelta(minutes=10)
    user.reset_attempts = 0
    # Persist cooldown before network I/O; concurrent requests cannot bypass it.
    db.commit()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post("https://control.msg91.com/api/v5/otp", headers={"authkey": key},
                params={"mobile": "91" + mobile, "template_id": template, "otp": otp, "otp_length": 6, "otp_expiry": 10})
        body = response.json()
        if response.status_code >= 400 or not isinstance(body, dict) or body.get("type") != "success":
            raise ValueError("Provider rejected SMS")
    except (httpx.RequestError, ValueError):
        raise HTTPException(503, "Unable to send OTP. Please try again after 60 seconds.") from None
    return {"message": "OTP sent to your registered mobile number.", "masked_mobile": "******" + mobile[-4:], "retry_after": 60}

@router.post("/reset-password")
def reset(data: Reset, db: Session = Depends(get_db)):
    new_hash = password_hash(data.new_password)
    user = find_admin(db, data.username)
    mobile = recovery_mobile(data.username)
    now = datetime.utcnow()
    if not user or not mobile or not user.reset_hash or not user.reset_expires or user.reset_expires <= now or user.reset_attempts >= 5:
        raise HTTPException(400, "Invalid or expired OTP. Request a new OTP.")
    user.reset_attempts += 1
    if not hmac.compare_digest(user.reset_hash, otp_digest(data.username, mobile, data.otp)):
        db.commit()
        raise HTTPException(400, "Invalid or expired OTP.")
    user.password_hash = new_hash
    invalidate(user)
    db.commit()
    return {"message": "Password reset successfully. Sign in with your new password."}
