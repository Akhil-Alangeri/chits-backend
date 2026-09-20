from sqlalchemy.orm import Session

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

def update_company_profile(
    db: Session,
    user: User,
    data
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

    # -----------------------------------------
    # COMPANY NAME
    # -----------------------------------------

    if data.company_name is not None:

        company.company_name = data.company_name.strip()


    # -----------------------------------------
    # EMAIL
    # -----------------------------------------

    if data.email is not None:

        company.email = str(data.email)


    # -----------------------------------------
    # MOBILE
    # -----------------------------------------

    if data.mobile is not None:

        company.mobile = data.mobile.strip()


    # -----------------------------------------
    # ADDRESS
    # -----------------------------------------

    if data.address is not None:

        company.address = data.address.strip()


    # -----------------------------------------
    # LOGO URL
    # -----------------------------------------

    if data.logo_url is not None:

        company.logo_url = data.logo_url.strip()


    db.commit()

    db.refresh(company)

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