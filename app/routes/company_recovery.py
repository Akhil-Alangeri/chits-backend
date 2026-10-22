"""Company-admin-only email recovery. All state is shared through SQL."""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import SECRET_KEY, hash_password
from app.models import User, Company
from app.models.admin.company_recovery import CompanyRecovery, RecoveryRate
from app.schemas.company_user import PasswordChange
from app.services.company_recovery_email import send_recovery_email

router = APIRouter(prefix="/auth/company", tags=["Company password recovery"])
logger = logging.getLogger(__name__)
GENERIC = {"message": "If an eligible account exists for this email address, a verification code will be sent."}

def digest(value):
    return hmac.new(SECRET_KEY.encode(), ("company-recovery:" + value).encode(), hashlib.sha256).hexdigest()

class Identity(BaseModel):
    email: EmailStr
    login_id: str = Field(min_length=1, max_length=50)

class Verify(Identity):
    otp: str = Field(pattern=r"^[0-9]{6}$")

class Reset(BaseModel):
    reset_token: str = Field(min_length=40, max_length=100)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_policy(cls, value):
        return PasswordChange.validate_password(value)

def limit(db, key, maximum):
    """Unique insert + row lock serializes rate counters across workers."""
    key = digest(key)
    now = datetime.utcnow()
    try:
        with db.begin_nested():
            db.add(RecoveryRate(key=key, window_start=now, count=0))
            db.flush()
    except IntegrityError:
        pass
    row = db.query(RecoveryRate).filter_by(key=key).with_for_update().populate_existing().one()
    if row.window_start <= now - timedelta(hours=1):
        row.window_start, row.count = now, 0
    row.count += 1
    allowed = row.count <= maximum
    db.commit()
    return allowed

def source_limit(db, request):
    # Do not trust client-controlled X-Forwarded-For. Configure trusted proxy handling at ASGI ingress.
    host = request.client.host if request.client else "unknown"
    if not limit(db, "source:" + host, 60):
        raise HTTPException(429, "Too many recovery requests. Please try again later.")

def eligible(user):
    return (user is not None and user.role == "company_admin" and user.status == "active"
            and user.company is not None and user.company.status == "active" and bool(user.password_hash))

def account(db, data):
    return db.query(User).join(Company).filter(User.login_id == data.login_id.strip(),
        func.lower(Company.email) == str(data.email).lower()).first()

def invalid():
    raise HTTPException(400, "Invalid or expired verification. Please request a new code.")

@router.post("/forgot-password")
def forgot(data: Identity, request: Request, db: Session = Depends(get_db)):
    source_limit(db, request)
    if not limit(db, "account:" + data.login_id.strip(), 5):
        return GENERIC
    user = account(db, data)
    if not eligible(user):
        return GENERIC
    # Lock the account first everywhere, then recovery state, to avoid deadlocks.
    user = db.query(User).filter_by(id=user.id).with_for_update().populate_existing().one()
    state = db.query(CompanyRecovery).filter_by(user_id=user.id).with_for_update().populate_existing().first()
    now = datetime.utcnow()
    if not eligible(user):
        db.rollback()
        return GENERIC
    if state and state.sent_at and state.sent_at > now - timedelta(seconds=60):
        db.rollback()
        return GENERIC
    if state is None:
        state = CompanyRecovery(user_id=user.id)
        db.add(state)
    otp = f"{secrets.randbelow(1000000):06d}"
    # A resend must never accidentally reissue the immediately preceding six digits.
    while state.otp_hash and hmac.compare_digest(state.otp_hash, digest(f"{user.id}:{otp}")):
        otp = f"{secrets.randbelow(1000000):06d}"
    state.otp_hash = None
    state.token_hash = None
    state.token_expires = None
    state.sent_at = now
    state.attempts = 0
    state.password_fingerprint = digest(user.password_hash)
    try:
        send_recovery_email(user.company.email, user.full_name or "Company Admin", otp, secrets.token_hex(16))
        state.otp_hash = digest(f"{user.id}:{otp}")
        state.otp_expires = datetime.utcnow() + timedelta(minutes=5)
    except Exception as exc:
        # No recipient, provider exception text, credentials, or OTP in logs.
        logger.error("Company recovery SMTP delivery failed (%s); check SMTP secrets, TLS and outbound connectivity", type(exc).__name__)
    db.commit()
    return GENERIC

@router.post("/verify-reset-otp")
def verify(data: Verify, request: Request, db: Session = Depends(get_db)):
    source_limit(db, request)
    user = account(db, data)
    if not eligible(user):
        invalid()
    user = db.query(User).filter_by(id=user.id).with_for_update().populate_existing().one()
    state = db.query(CompanyRecovery).filter_by(user_id=user.id).with_for_update().populate_existing().first()
    if (not eligible(user) or not state or not state.otp_hash or state.attempts >= 5
            or not state.otp_expires or state.otp_expires <= datetime.utcnow()
            or state.password_fingerprint != digest(user.password_hash)):
        db.rollback()
        invalid()
    state.attempts += 1
    if not hmac.compare_digest(state.otp_hash, digest(f"{user.id}:{data.otp}")):
        if state.attempts >= 5:
            state.otp_hash = None
        db.commit()
        invalid()
    token = secrets.token_urlsafe(32)
    claimed = db.query(CompanyRecovery).filter(
        CompanyRecovery.user_id == user.id,
        CompanyRecovery.otp_hash == state.otp_hash,
        CompanyRecovery.attempts < 5,
        CompanyRecovery.otp_expires > datetime.utcnow(),
    ).update({CompanyRecovery.otp_hash: None, CompanyRecovery.token_hash: digest(token),
              CompanyRecovery.token_expires: datetime.utcnow() + timedelta(minutes=5)}, synchronize_session=False)
    if claimed != 1:
        db.rollback()
        invalid()
    db.commit()
    return {"reset_token": token, "expires_in": 300}

@router.post("/reset-password")
def reset(data: Reset, request: Request, db: Session = Depends(get_db)):
    source_limit(db, request)
    token_hash = digest(data.reset_token)
    candidate = db.query(CompanyRecovery).filter_by(token_hash=token_hash).first()
    if not candidate:
        invalid()
    user = db.query(User).filter_by(id=candidate.user_id).with_for_update().populate_existing().first()
    state = db.query(CompanyRecovery).filter_by(user_id=candidate.user_id).with_for_update().populate_existing().one()
    if (not eligible(user) or state.token_hash != token_hash or not state.token_expires
            or state.token_expires <= datetime.utcnow()
            or state.password_fingerprint != digest(user.password_hash)):
        db.rollback()
        invalid()
    claimed = db.query(CompanyRecovery).filter(
        CompanyRecovery.user_id == user.id, CompanyRecovery.token_hash == token_hash,
        CompanyRecovery.token_expires > datetime.utcnow(),
    ).update({CompanyRecovery.token_hash: None, CompanyRecovery.otp_hash: None,
              CompanyRecovery.token_expires: None}, synchronize_session=False)
    if claimed != 1:
        db.rollback()
        invalid()
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Your password has been updated successfully. You can now sign in using your new password."}
