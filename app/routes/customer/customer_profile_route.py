from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_customer

from app.schemas.customer.customer_profile import (
    CustomerProfileResponse,
    CustomerProfileData,
)

from app.services.customer.customer_profile import (
    get_customer_profile,
)


router = APIRouter(
    prefix="/customer/profile",
    tags=["Customer Profile"],
)


@router.get(
    "",
    response_model=CustomerProfileResponse,
)
def get_my_customer_profile(
    db: Session = Depends(get_db),
    current_customer=Depends(get_current_customer),
):
    customer_profile_id = current_customer["customer_profile_id"]

    profile = get_customer_profile(
        db=db,
        customer_profile_id=customer_profile_id,
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer profile not found.",
        )

    return CustomerProfileResponse(
        success=True,
        message="Customer profile fetched successfully",
        profile=CustomerProfileData(
            customer_profile_id=profile.id,
            customer_code=profile.customer_code,
            display_name=profile.display_name,
            legal_name=profile.legal_name,
            mobile=profile.mobile,
            email=profile.email,
            address=profile.address,
            status=profile.status,
        ),
    )