from sqlalchemy.orm import Session

from app.models.admin.company import Company
from app.models.admin.user import User

from app.core.security import (
    verify_password,
    create_access_token
)


def authenticate_company(
    db: Session,
    login_id: str,
    password: str
):

    # =========================================
    # FIND USER BY LOGIN ID
    # =========================================

    user = (
        db.query(User)
        .filter(
            User.login_id == login_id
        )
        .first()
    )


    # =========================================
    # USER NOT FOUND
    # =========================================

    if not user:

        return {
            "error": "invalid_credentials"
        }


    # =========================================
    # USER MUST BE ACTIVE
    # =========================================

    if user.status != "active":

        return {
            "error": "user_not_active"
        }


    # =========================================
    # COMPANY
    # =========================================

    company = user.company

    if not company:

        return {
            "error": "company_not_found"
        }


    # =========================================
    # COMPANY MUST BE ACTIVE
    # =========================================

    if company.status != "active":

        return {
            "error": "company_not_active"
        }


    # =========================================
    # PASSWORD HASH CHECK
    # =========================================

    if not user.password_hash:

        return {
            "error": "credentials_not_configured"
        }


    # =========================================
    # VERIFY PASSWORD
    # =========================================

    if not verify_password(
        password,
        user.password_hash
    ):

        return {
            "error": "invalid_credentials"
        }


    # =========================================
    # CREATE JWT
    # =========================================

    access_token = create_access_token({

        "sub": str(user.id),

        "user_id": user.id,

        "company_id": user.company_id,

        "login_id": user.login_id,

        "role": user.role,

    })


    # =========================================
    # SUCCESS
    # =========================================

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "company": {
            "id": company.id,
            "company_name": company.company_name,
            "login_id": user.login_id,
            "email": company.email,
            "logo_url":company.logo_url
        }
    }