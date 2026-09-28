from sqlalchemy.orm import Session
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.models.admin.company import Company
from app.models.admin.user import User

from app.core.security import (
    verify_password,
    hash_password,
)


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

        allowed_types = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
        }

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

        # -----------------------------------------
        # CREATE LOGO DIRECTORY
        # -----------------------------------------

        upload_dir = Path(
            "uploads/company-logos"
        )

        upload_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        # -----------------------------------------
        # UNIQUE FILE NAME
        # -----------------------------------------

        extension = allowed_types[
            logo.content_type
        ]

        filename = (
            f"company_{uuid4().hex}"
            f"{extension}"
        )

        file_path = upload_dir / filename

        # -----------------------------------------
        # SAVE FILE
        # -----------------------------------------

        with open(
            file_path,
            "wb"
        ) as file:

            file.write(file_content)

        # -----------------------------------------
        # SAVE URL IN DATABASE
        # -----------------------------------------

        company.logo_url = (
            f"/uploads/company-logos/{filename}"
        )

    # =========================================
    # SAVE DATABASE
    # =========================================

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
    new_login_id: str
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


    # -----------------------------------------
    # UPDATE
    # -----------------------------------------

    user.login_id = new_login_id

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
    confirm_password: str
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


    db.commit()

    db.refresh(user)


    return {
        "success": True
    }