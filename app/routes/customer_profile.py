from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.models.admin.user import User

from app.schemas.customer_profile import (
    CustomerProfileCreate,
    CustomerProfileUpdate,
    CustomerProfileResponse,
    CustomerDetailsResponse
)

from app.services.customer_profile_service import (
    create_customer_profile,
    get_customer_profiles,
    get_customer_profile,
    update_customer_profile,
    get_customer_details
    
)


router = APIRouter(
    prefix="/customers",
    tags=["Customer Profiles"],
)


# =========================================================
# CREATE
# =========================================================

# =========================================================
# CREATE
# =========================================================

@router.post(
    "",
    response_model=CustomerProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    customer_data: CustomerProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    result = create_customer_profile(
        db=db,
        company_id=current_user.company_id,
        customer_data=customer_data,
    )

    # =====================================================
    # HANDLE SERVICE ERRORS
    # =====================================================

    if isinstance(result, dict):

        error = result.get("error")

        if error == "company_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found.",
            )

        if error == "customer_mobile_exists":

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "A customer with this mobile number "
                    "already exists in this company."
                ),
            )

    # =====================================================
    # SUCCESS
    # =====================================================

    return result
# =========================================================
# GET ALL
# =========================================================

@router.get(
    "",
    response_model=List[CustomerProfileResponse],
)
def get_customers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    return get_customer_profiles(
        db,
        current_user.company_id,
    )


# =========================================================
# GET ONE
# =========================================================

@router.get(
    "/{customer_id}",
    response_model=CustomerProfileResponse,
)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    customer = get_customer_profile(
        db,
        current_user.company_id,
        customer_id,
    )

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    return customer

# =========================================================
# UPDATE
# =========================================================

@router.put(
    "/{customer_id}",
    response_model=CustomerProfileResponse,
)
def update_customer(
    customer_id: int,
    customer_data: CustomerProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    customer = update_customer_profile(
        db,
        current_user.company_id,
        customer_id,
        customer_data,
    )

    if not customer:

        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )

    return customer


# =========================================================
# GET CUSTOMER DETAILS
# =========================================================

@router.get(
    "/{customer_id}/details",
    response_model=CustomerDetailsResponse,
)
def get_customer_details_route(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    result = get_customer_details(
        db=db,
        company_id=current_user.company_id,
        customer_id=customer_id,
    )

    if not result:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    return result