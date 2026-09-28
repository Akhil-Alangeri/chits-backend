from datetime import datetime, timedelta, timezone
import secrets

import bcrypt

from sqlalchemy.orm import Session

from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_member import ChitMember
from app.models.customer.customer_otp import CustomerOTP

from app.core.security import create_access_token


# =====================================================
# OTP CONFIGURATION
# =====================================================

OTP_LENGTH = 6

OTP_EXPIRE_MINUTES = 5

MAX_OTP_ATTEMPTS = 5


# =====================================================
# GET CUSTOMER BY MOBILE
# =====================================================

def get_customer_by_mobile(
    db: Session,
    mobile: str,
) -> CustomerProfile | None:

    customer = (
        db.query(CustomerProfile)
        .join(
            ChitMember,
            ChitMember.customer_profile_id
            == CustomerProfile.id,
        )
        .filter(
            CustomerProfile.mobile == mobile,
            CustomerProfile.status == "active",
            ChitMember.status == "confirmed",
        )
        .first()
    )

    return customer


# =====================================================
# GENERATE OTP
# =====================================================

def generate_customer_otp() -> str:

    return "".join(
        str(secrets.randbelow(10))
        for _ in range(OTP_LENGTH)
    )


# =====================================================
# SEND OTP
# =====================================================

def send_customer_otp(
    db: Session,
    mobile: str,
) -> dict:

    # -------------------------------------------------
    # Find eligible customer
    # -------------------------------------------------

    customer = get_customer_by_mobile(
        db=db,
        mobile=mobile,
    )

    if not customer:
        raise ValueError(
            "Customer is not eligible for login."
        )

    # -------------------------------------------------
    # Generate OTP
    # -------------------------------------------------

    otp = generate_customer_otp()

    # -------------------------------------------------
    # Hash OTP
    # -------------------------------------------------

    otp_hash = bcrypt.hashpw(
        otp.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    # -------------------------------------------------
    # Expiry
    # -------------------------------------------------

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=OTP_EXPIRE_MINUTES
        )
    )

    # -------------------------------------------------
    # Invalidate previous OTPs
    # -------------------------------------------------

    (
        db.query(CustomerOTP)
        .filter(
            CustomerOTP.customer_profile_id
            == customer.id,
            CustomerOTP.is_used == False,
        )
        .update(
            {
                CustomerOTP.is_used: True,
            },
            synchronize_session=False,
        )
    )

    # -------------------------------------------------
    # Create OTP record
    # -------------------------------------------------

    otp_record = CustomerOTP(
        customer_profile_id=customer.id,
        mobile=mobile,
        otp_hash=otp_hash,
        expires_at=expires_at,
        is_used=False,
        attempts=0,
    )

    db.add(otp_record)

    db.commit()

    db.refresh(otp_record)

    # -------------------------------------------------
    # DEVELOPMENT RESPONSE
    # -------------------------------------------------

    return {
        "customer_profile_id": customer.id,
        "otp_expires_in": OTP_EXPIRE_MINUTES * 60,
        "development_otp": otp,
    }


# =====================================================
# VERIFY OTP
# =====================================================

def verify_customer_otp(
    db: Session,
    mobile: str,
    otp: str,
) -> tuple[CustomerProfile, str]:

    # -------------------------------------------------
    # Find customer
    # -------------------------------------------------

    customer = get_customer_by_mobile(
        db=db,
        mobile=mobile,
    )

    if not customer:
        raise ValueError(
            "Customer is not eligible for login."
        )

    # -------------------------------------------------
    # Find latest unused OTP
    # -------------------------------------------------

    otp_record = (
        db.query(CustomerOTP)
        .filter(
            CustomerOTP.customer_profile_id
            == customer.id,

            CustomerOTP.mobile
            == mobile,

            CustomerOTP.is_used == False,
        )
        .order_by(
            CustomerOTP.created_at.desc()
        )
        .first()
    )

    if not otp_record:
        raise ValueError(
            "OTP not found. Please request a new OTP."
        )

    # -------------------------------------------------
    # Check expiry
    # -------------------------------------------------

    now = datetime.now(timezone.utc)

    expires_at = otp_record.expires_at

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(
            tzinfo=timezone.utc
        )

    if now > expires_at:

        otp_record.is_used = True

        db.commit()

        raise ValueError(
            "OTP has expired. Please request a new OTP."
        )

    # -------------------------------------------------
    # Check attempts
    # -------------------------------------------------

    if otp_record.attempts >= MAX_OTP_ATTEMPTS:

        otp_record.is_used = True

        db.commit()

        raise ValueError(
            "Too many incorrect OTP attempts. "
            "Please request a new OTP."
        )

    # -------------------------------------------------
    # Verify OTP
    # -------------------------------------------------

    is_valid = bcrypt.checkpw(
        otp.encode("utf-8"),
        otp_record.otp_hash.encode("utf-8"),
    )

    if not is_valid:

        otp_record.attempts += 1

        db.commit()

        raise ValueError(
            "Invalid OTP."
        )

    # -------------------------------------------------
    # Mark OTP as used
    # -------------------------------------------------

    otp_record.is_used = True

    otp_record.used_at = datetime.now(
        timezone.utc
    )

    db.commit()

    # -------------------------------------------------
    # Create JWT
    # -------------------------------------------------

    access_token = create_access_token(
        data={
            "sub": f"customer:{customer.id}",
            "customer_profile_id": customer.id,
            "customer_code": customer.customer_code,
            "token_type": "customer",
        },
        expires_minutes=24 * 60,
    )

    return customer, access_token