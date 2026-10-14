from __future__ import annotations

from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_customer

from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_group import ChitGroup

from app.schemas.chit_group import ChitGroupResponse


# ============================================================
# CUSTOMER UPCOMING CHITS ROUTER
# ============================================================

router = APIRouter(
    prefix="/customer/my-chits",
    tags=["Customer Upcoming Chits"],
)


# ============================================================
# RESOLVE AUTHENTICATED CUSTOMER MOBILE
# ============================================================

def _get_customer_mobile(
    db: Session,
    current_customer: dict,
) -> str:
    """
    Resolve the authenticated customer's mobile number.

    The current customer JWT may contain either:

        mobile

    or only:

        customer_profile_id

    In the second case, resolve the mobile number from the
    active CustomerProfile.
    """

    # --------------------------------------------------------
    # 1. MOBILE PRESENT IN JWT
    # --------------------------------------------------------

    mobile = current_customer.get("mobile")

    if mobile:
        mobile = str(mobile).strip()

        if mobile:
            return mobile

    # --------------------------------------------------------
    # 2. FALLBACK TO CUSTOMER PROFILE ID
    # --------------------------------------------------------

    customer_profile_id = current_customer.get(
        "customer_profile_id"
    )

    if not customer_profile_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer identity is missing from authentication.",
        )

    # --------------------------------------------------------
    # 3. FETCH ACTIVE CUSTOMER PROFILE
    # --------------------------------------------------------

    customer_profile = (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.id == int(customer_profile_id),
            CustomerProfile.status == "active",
        )
        .first()
    )

    if not customer_profile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Active customer profile not found.",
        )

    if not customer_profile.mobile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer mobile number could not be resolved.",
        )

    return str(customer_profile.mobile).strip()


# ============================================================
# VERIFY CUSTOMER HAS ACCESS TO COMPANY
# ============================================================

def _verify_company_access(
    db: Session,
    mobile: str,
    company_id: int,
) -> None:
    """
    Verify that the authenticated customer belongs to the
    requested company.

    Access is granted only when:

        CustomerProfile.mobile == authenticated mobile
        CustomerProfile.company_id == requested company
        CustomerProfile.status == active
        ChitMember.status == confirmed
    """

    customer_profile = (
        db.query(CustomerProfile)
        .join(
            ChitMember,
            ChitMember.customer_profile_id
            == CustomerProfile.id,
        )
        .filter(
            CustomerProfile.company_id == company_id,
            CustomerProfile.mobile == mobile,
            CustomerProfile.status == "active",
            ChitMember.status == "confirmed",
        )
        .first()
    )

    if not customer_profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You are not authorized to access "
                "this company's chit information."
            ),
        )


# ============================================================
# GET UPCOMING CHITS FOR CUSTOMER'S COMPANY
# ============================================================

@router.get(
    "/companies/{company_id}/upcoming",
    response_model=List[ChitGroupResponse],
)
def get_customer_upcoming_chits(
    company_id: int,
    db: Session = Depends(get_db),
    current_customer: dict = Depends(get_current_customer),
):
    """
    Get all upcoming chits created by the company.

    IMPORTANT:

    This is a customer-only endpoint.

    The customer can only see upcoming chits from a company
    where the authenticated customer already has a confirmed
    membership.

    Only status='upcoming' chits are returned.
    """

    # --------------------------------------------------------
    # 1. RESOLVE AUTHENTICATED CUSTOMER
    # --------------------------------------------------------

    mobile = _get_customer_mobile(
        db=db,
        current_customer=current_customer,
    )

    # --------------------------------------------------------
    # 2. VERIFY COMPANY ACCESS
    # --------------------------------------------------------

    _verify_company_access(
        db=db,
        mobile=mobile,
        company_id=company_id,
    )

    # --------------------------------------------------------
    # 3. FETCH UPCOMING CHITS
    # --------------------------------------------------------

    chits = (
        db.query(ChitGroup)
        .filter(
            ChitGroup.company_id == company_id,
            ChitGroup.status == "upcoming",
        )
        .order_by(
            ChitGroup.start_date.asc(),
            ChitGroup.id.desc(),
        )
        .all()
    )

    # --------------------------------------------------------
    # 4. RETURN EMPTY LIST WHEN NOTHING IS AVAILABLE
    # --------------------------------------------------------

    return chits


# ============================================================
# GET SINGLE UPCOMING CHIT DETAILS
# ============================================================

@router.get(
    "/companies/{company_id}/upcoming/{chit_id}",
    response_model=ChitGroupResponse,
)
def get_customer_upcoming_chit_details(
    company_id: int,
    chit_id: int,
    db: Session = Depends(get_db),
    current_customer: dict = Depends(get_current_customer),
):
    """
    Get complete details of one upcoming chit.

    This returns the same ChitGroupResponse structure used by
    the admin chit details API, including the monthly schedule.

    The customer can access it only when:

        1. Customer belongs to the requested company.
        2. Chit belongs to the requested company.
        3. Chit status is 'upcoming'.
    """

    # --------------------------------------------------------
    # 1. RESOLVE AUTHENTICATED CUSTOMER
    # --------------------------------------------------------

    mobile = _get_customer_mobile(
        db=db,
        current_customer=current_customer,
    )

    # --------------------------------------------------------
    # 2. VERIFY COMPANY ACCESS
    # --------------------------------------------------------

    _verify_company_access(
        db=db,
        mobile=mobile,
        company_id=company_id,
    )

    # --------------------------------------------------------
    # 3. FETCH SPECIFIC UPCOMING CHIT
    # --------------------------------------------------------

    chit = (
        db.query(ChitGroup)
        .filter(
            ChitGroup.id == chit_id,
            ChitGroup.company_id == company_id,
            ChitGroup.status == "upcoming",
        )
        .first()
    )

    # --------------------------------------------------------
    # 4. NOT FOUND / NOT UPCOMING
    # --------------------------------------------------------

    if not chit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upcoming chit not found.",
        )

    # --------------------------------------------------------
    # 5. RETURN COMPLETE CHIT DETAILS
    # --------------------------------------------------------

    return chit