from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.admin.user import User
from app.models.admin.customer_profile import CustomerProfile



security = HTTPBearer()


# =========================================================
# GET CURRENT USER
# =========================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):

    token = credentials.credentials

    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )

    user = (
        db.query(User)
        .filter(
            User.id == int(user_id)
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active.",
        )

    return user


# =========================================================
# GET CURRENT COMPANY ID
# =========================================================

def get_current_company_id(
    current_user=Depends(get_current_user),
) -> int:

    company_id = current_user.company_id

    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company",
        )

    return int(company_id)




# =========================================================
# GET CURRENT CUSTOMER
# =========================================================

# =========================================================
# GET CURRENT CUSTOMER
# =========================================================

def get_current_customer(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):

    token = credentials.credentials

    payload = decode_access_token(token)

    if not payload:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired customer token.",
        )

    # -----------------------------------------------------
    # Check token type
    # -----------------------------------------------------

    if payload.get("token_type") != "customer":

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid customer authentication token.",
        )

    # -----------------------------------------------------
    # Customer profile ID
    # -----------------------------------------------------

    customer_profile_id = payload.get(
        "customer_profile_id"
    )

    if not customer_profile_id:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer identity missing.",
        )

    # -----------------------------------------------------
    # Find logged-in customer profile
    # -----------------------------------------------------

    customer = (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.id == int(
                customer_profile_id
            ),
            CustomerProfile.status == "active",
        )
        .first()
    )

    if not customer:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer profile not found.",
        )

    # -----------------------------------------------------
    # Return authenticated customer information
    # -----------------------------------------------------

    return {
        "customer_profile_id": customer.id,

        "customer_code": customer.customer_code,

        "mobile": customer.mobile,
    }