from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_customer

from app.schemas.customer.customer_chit import (
    CustomerCompanyResponse,
    CustomerCompanyStatistics,
    CustomerChitResponse,
    CustomerMyChitsResponse,
    CustomerCompanyChitsResponse,
    CustomerChitDetailsResponse
)

from app.services.customer.customer_chit_service import (
    get_customer_membership_companies,
    get_customer_company_chits,
    get_customer_chit_details
)


# =========================================================
# CUSTOMER MY CHITS ROUTER
# =========================================================

router = APIRouter(
    prefix="/customer",
    tags=["Customer My Chits"],
)


# =========================================================
# GET CUSTOMER MEMBERSHIP COMPANIES
# =========================================================
#
# Endpoint:
#
# GET /customer/my-chits
#
# Returns all companies where the logged-in customer
# has an active customer profile and confirmed chit membership.
#
# =========================================================

@router.get(
    "/my-chits",
    response_model=CustomerMyChitsResponse,
)
def get_my_chit_companies(
    db: Session = Depends(get_db),
    current_customer=Depends(get_current_customer),
):

    # -----------------------------------------------------
    # Get mobile from authenticated customer
    # -----------------------------------------------------

    mobile = current_customer["mobile"]

    # -----------------------------------------------------
    # Get companies
    # -----------------------------------------------------

    companies = get_customer_membership_companies(
        db=db,
        mobile=mobile,
    )

    # -----------------------------------------------------
    # Convert query result to response objects
    # -----------------------------------------------------

    company_list = []

    for company in companies:

        company_list.append(
            CustomerCompanyResponse(
                company_id=company.company_id,
                company_name=company.company_name,
                logo_url=company.logo_url,
                customer_profile_id=company.customer_profile_id,
                customer_code=company.customer_code,
            )
        )

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return CustomerMyChitsResponse(
        success=True,
        message="Customer membership companies fetched successfully",
        companies=company_list,
    )


# =========================================================
# GET CUSTOMER CHITS OF SELECTED COMPANY
# =========================================================
#
# Endpoint:
#
# GET /customer/my-chits/companies/{company_id}
#
# Returns:
#
# 1. Company details
# 2. Company statistics
# 3. Logged-in customer's confirmed chits
#
# =========================================================

@router.get(
    "/my-chits/companies/{company_id}",
    response_model=CustomerCompanyChitsResponse,
)
def get_company_chits(
    company_id: int,
    db: Session = Depends(get_db),
    current_customer=Depends(get_current_customer),
):

    # -----------------------------------------------------
    # Get mobile from authenticated customer
    # -----------------------------------------------------

    mobile = current_customer["mobile"]

    # -----------------------------------------------------
    # Get company + customer chits
    # -----------------------------------------------------

    result = get_customer_company_chits(
        db=db,
        mobile=mobile,
        company_id=company_id,
    )

    # -----------------------------------------------------
    # Customer is not a confirmed member of this company
    # -----------------------------------------------------

    if not result:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a confirmed member of this company.",
        )

    # =====================================================
    # COMPANY
    # =====================================================

    company = result["company"]

    company_response = CustomerCompanyResponse(
        company_id=company.company_id,
        company_name=company.company_name,
        logo_url=company.logo_url,
        customer_profile_id=company.customer_profile_id,
        customer_code=company.customer_code,
    )

    # =====================================================
    # CUSTOMER CHITS
    # =====================================================

    chit_list = []

    for member, customer, chit in result["chits"]:

        chit_list.append(
            CustomerChitResponse(
                chit_member_id=member.id,

                chit_id=chit.id,

                chit_name=chit.name,

                chit_code=chit.code,

                customer_profile_id=customer.id,

                customer_code=customer.customer_code,

                member_number=member.member_number,

                slot_number=member.slot_number,

                member_name=member.member_name,

                member_status=member.status,

                chit_value=chit.chit_value,

                monthly_emi=chit.monthly_emi,

                duration_months=chit.duration_months,

                start_date=chit.start_date,
            )
        )

    # =====================================================
    # FINAL RESPONSE
    # =====================================================

    return CustomerCompanyChitsResponse(
        success=True,

        message=(
            "Company details and customer chits "
            "fetched successfully"
        ),

        company=company_response,

        statistics=CustomerCompanyStatistics(
            active_chits=result["active_chits"],
            active_members=result["active_members"],
        ),

        chits=chit_list,
    )
    
    
    
    
    
# ============================================================
# CUSTOMER - SPECIFIC CHIT SLOT DETAILS
# ============================================================

@router.get(
    "/my-chits/{chit_member_id}/details",
    response_model=CustomerChitDetailsResponse,
)
def get_my_chit_details(
    chit_member_id: int,
    db: Session = Depends(get_db),
    current_customer=Depends(get_current_customer),
):
    # -----------------------------------------------------
    # Get authenticated customer's mobile
    # -----------------------------------------------------

    mobile = current_customer["mobile"]

    # -----------------------------------------------------
    # Fetch exact chit slot
    # -----------------------------------------------------

    result = get_customer_chit_details(
        db=db,
        mobile=mobile,
        chit_member_id=chit_member_id,
    )

    # -----------------------------------------------------
    # Authorization failed
    # -----------------------------------------------------

    if not result:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You are not authorized to view "
                "this chit slot."
            ),
        )

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return CustomerChitDetailsResponse(
        success=True,
        message="Chit details fetched successfully",
        chit=result["chit"],
        payment_summary=result["payment_summary"],
        monthly_payments=result["monthly_payments"],
        lift_details=result["lift_details"],
    )