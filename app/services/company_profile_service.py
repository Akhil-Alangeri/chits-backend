from sqlalchemy.orm import Session
from app.services.logo_storage import LOGO_TYPES, save_logo

from fastapi import UploadFile

from app.models.admin.company import Company
from app.models.admin.user import User

from app.core.security import (
    verify_password,
    hash_password,
)

from app.services.audit_log_service import (
    create_audit_log,
    snapshot_model,
)


COMPANY_PROFILE_AUDIT_FIELDS = [
    "id",
    "company_name",
    "email",
    "mobile",
    "address",
    "logo_url",
    "status",
]


# =========================================================
# GET COMPANY PROFILE
# =========================================================

def get_company_profile(
    db: Session,
    user: User
):

    company = (
        db.query(Company)
        .filter(
            Company.id == user.company_id
        )
        .first()
    )

    if not company:
        return {
            "error": "company_not_found"
        }

    return {
        "id": company.id,
        "company_name": company.company_name,
        "logo_url": company.logo_url,
        "email": company.email,
        "mobile": company.mobile,
        "address": company.address,
        "status": company.status,
        "login_id": user.login_id,
    }


# =========================================================
# UPDATE COMPANY PROFILE
# =========================================================

async def update_company_profile(
    db: Session,
    user: User,
    company_name: str,
    email: str,
    mobile: str,
    address: str,
    logo: UploadFile | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
):

    company = (
        db.query(Company)
        .filter(
            Company.id == user.company_id
        )
        .first()
    )

    if not company:
        return {
            "error": "company_not_found"
        }

    old_values = snapshot_model(
        company,
        COMPANY_PROFILE_AUDIT_FIELDS,
    )

    # =========================================
    # COMPANY NAME
    # =========================================

    if company_name is not None:
        company.company_name = company_name.strip()

    # =========================================
    # EMAIL
    # =========================================

    if email is not None:
        company.email = email.strip()

    # =========================================
    # MOBILE
    # =========================================

    if mobile is not None:
        company.mobile = mobile.strip()

    # =========================================
    # ADDRESS
    # =========================================

    if address is not None:
        company.address = address.strip()

    # =========================================
    # COMPANY LOGO
    # =========================================

    if logo is not None:

        # -----------------------------------------
        # ALLOWED IMAGE TYPES
        # -----------------------------------------

        allowed_types = LOGO_TYPES

        if logo.content_type not in allowed_types:

            return {
                "error": "invalid_logo_type"
            }

        # -----------------------------------------
        # READ FILE
        # -----------------------------------------

        file_content = await logo.read()

        # -----------------------------------------
        # MAXIMUM 2 MB
        # -----------------------------------------

        max_size = 2 * 1024 * 1024

        if len(file_content) > max_size:

            return {
                "error": "logo_too_large"
            }

        company.logo_url = save_logo(file_content, logo.content_type)

    # =========================================
    # SAVE DATABASE
    # =========================================

    db.flush()

    create_audit_log(
        db=db,
        company_id=company.id,
        user_id=user.id,
        action="UPDATE",
        module="Company Profile",
        entity_type="Company",
        entity_id=company.id,
        description=(
            f"Updated company profile for "
            f"'{company.company_name}'"
        ),
        old_values=old_values,
        new_values=snapshot_model(
            company,
            COMPANY_PROFILE_AUDIT_FIELDS,
        ),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()

    db.refresh(company)

    # =========================================
    # RESPONSE
    # =========================================

    return {
        "id": company.id,
        "company_name": company.company_name,
        "logo_url": company.logo_url,
        "email": company.email,
        "mobile": company.mobile,
        "address": company.address,
        "status": company.status,
        "login_id": user.login_id,
    }
# =========================================================
# UPDATE LOGIN ID
# =========================================================

def update_login_id(
    db: Session,
    user: User,
    new_login_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
):

    new_login_id = new_login_id.strip()


    # -----------------------------------------
    # SAME LOGIN ID
    # -----------------------------------------

    if new_login_id == user.login_id:

        return {
            "error": "same_login_id"
        }


    # -----------------------------------------
    # CHECK DUPLICATE LOGIN ID
    # -----------------------------------------

    existing_user = (
        db.query(User)
        .filter(
            User.login_id == new_login_id,
            User.id != user.id
        )
        .first()
    )

    if existing_user:

        return {
            "error": "login_id_already_exists"
        }

    old_values = {
        "login_id": user.login_id,
    }


    # -----------------------------------------
    # UPDATE
    # -----------------------------------------

    user.login_id = new_login_id

    db.flush()

    if user.company_id is not None:

        create_audit_log(
            db=db,
            company_id=user.company_id,
            user_id=user.id,
            action="UPDATE",
            module="Company Profile",
            entity_type="User",
            entity_id=user.id,
            description="Updated company login ID",
            old_values=old_values,
            new_values={
                "login_id": user.login_id,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

    db.commit()

    db.refresh(user)


    return {
        "login_id": user.login_id
    }


# =========================================================
# UPDATE PASSWORD
# =========================================================

def update_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    confirm_password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
):

    # -----------------------------------------
    # VERIFY CURRENT PASSWORD
    # -----------------------------------------

    if not verify_password(
        current_password,
        user.password_hash
    ):

        return {
            "error": "invalid_current_password"
        }


    # -----------------------------------------
    # CONFIRM NEW PASSWORD
    # -----------------------------------------

    if new_password != confirm_password:

        return {
            "error": "password_mismatch"
        }


    # -----------------------------------------
    # PREVENT SAME PASSWORD
    # -----------------------------------------

    if verify_password(
        new_password,
        user.password_hash
    ):

        return {
            "error": "same_password"
        }


    # -----------------------------------------
    # HASH NEW PASSWORD
    # -----------------------------------------

    user.password_hash = hash_password(
        new_password
    )

    db.flush()

    if user.company_id is not None:

        create_audit_log(
            db=db,
            company_id=user.company_id,
            user_id=user.id,
            action="UPDATE",
            module="Company Profile",
            entity_type="User",
            entity_id=user.id,
            description="Changed company account password",
            old_values={
                "password_changed": False,
            },
            new_values={
                "password_changed": True,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )


    db.commit()

    db.refresh(user)


    return {
        "success": True
    }
