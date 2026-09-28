# ============================================================
# CUSTOMER SUPPORT TICKET ROUTES
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_customer

from app.schemas.support.ticket import (
    CustomerSupportTicketCreate,
    CustomerTicketDetailResponse,
    CustomerTicketPaginatedResponse,
    TicketMessageCreate,
    TicketMessageResponse,
)

from app.services.support.ticket_service import (
    create_customer_ticket,
    get_customer_tickets,
    get_customer_ticket_details,
    create_customer_message,
    get_customer_profile_for_company,
    get_customer_mobile_by_profile_id,
)


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/customer/tickets",
    tags=["Customer Support Tickets"],
)


# ============================================================
# HELPER
# ============================================================

def get_customer_mobile(
    db: Session,
    current_customer: dict,
) -> str:
    """
    Resolve the authenticated customer's mobile.

    Priority:

        1. mobile from JWT
        2. customer_profile_id from JWT
           -> CustomerProfile.mobile

    This allows the same customer to work across
    multiple companies even when the JWT was created
    from one company-specific CustomerProfile.
    """

    # --------------------------------------------------------
    # First try mobile from JWT
    # --------------------------------------------------------

    mobile = current_customer.get("mobile")

    if mobile:

        mobile = str(mobile).strip()

        if mobile:
            return mobile

    # --------------------------------------------------------
    # Fallback: resolve mobile from profile ID
    # --------------------------------------------------------

    customer_profile_id = current_customer.get(
        "customer_profile_id"
    )

    if not customer_profile_id:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer identity is missing from authentication.",
        )

    mobile = get_customer_mobile_by_profile_id(
        db=db,
        customer_profile_id=int(customer_profile_id),
    )

    if not mobile:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer mobile number could not be resolved.",
        )

    mobile = str(mobile).strip()

    if not mobile:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid customer authentication.",
        )

    return mobile


# ============================================================
# CREATE CUSTOMER TICKET
# ============================================================

@router.post(
    "",
    response_model=CustomerTicketDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket(
    data: CustomerSupportTicketCreate,
    db: Session = Depends(get_db),
    current_customer: dict = Depends(get_current_customer),
):
    """
    Create a customer support ticket.

    Authorization:

        customer mobile
        +
        selected company_id

    This resolves the correct company-specific
    CustomerProfile before creating the ticket.
    """

    # --------------------------------------------------------
    # Resolve customer mobile
    # --------------------------------------------------------

    mobile = get_customer_mobile(
        db=db,
        current_customer=current_customer,
    )

    # --------------------------------------------------------
    # Resolve company-specific profile
    # --------------------------------------------------------

    customer_profile = get_customer_profile_for_company(
        db=db,
        mobile=mobile,
        company_id=data.company_id,
    )

    if not customer_profile:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You are not authorized to create a ticket "
                "for this company."
            ),
        )

    # --------------------------------------------------------
    # Create ticket
    # --------------------------------------------------------

    try:

        ticket = create_customer_ticket(
            db=db,
            customer_profile_id=customer_profile.id,
            company_id=data.company_id,
            subject=data.subject,
            description=data.description,
            category=data.category,
            priority=data.priority,
        )

        ticket.messages

        return ticket

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ============================================================
# LIST CUSTOMER TICKETS
# ============================================================

@router.get(
    "",
    response_model=CustomerTicketPaginatedResponse,
)
def list_tickets(
    company_id: int | None = None,
    status_filter: str | None = Query(
        default=None,
        alias="status",
    ),
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
    current_customer: dict = Depends(get_current_customer),
):
    """
    Get paginated customer support tickets.

    If company_id is supplied:

        mobile + company_id
        ->
        company-specific CustomerProfile
        ->
        tickets

    Without company_id:

        JWT profile is used for backward compatibility.
    """

    # --------------------------------------------------------
    # Resolve mobile
    # --------------------------------------------------------

    mobile = get_customer_mobile(
        db=db,
        current_customer=current_customer,
    )

    # --------------------------------------------------------
    # Validate pagination
    # --------------------------------------------------------

    if page < 1:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page must be greater than or equal to 1.",
        )

    if page_size < 1 or page_size > 100:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page size must be between 1 and 100.",
        )

    # --------------------------------------------------------
    # Resolve company-specific profile
    # --------------------------------------------------------

    if company_id is not None:

        customer_profile = get_customer_profile_for_company(
            db=db,
            mobile=mobile,
            company_id=company_id,
        )

        if not customer_profile:

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this company.",
            )

        customer_profile_id = customer_profile.id

    else:

        customer_profile_id = current_customer.get(
            "customer_profile_id"
        )

        if not customer_profile_id:

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid customer authentication.",
            )

    # --------------------------------------------------------
    # Get tickets
    # --------------------------------------------------------

    try:

        tickets, total_count = get_customer_tickets(
            db=db,
            customer_profile_id=customer_profile_id,
            company_id=company_id,
            status=status_filter,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # --------------------------------------------------------
    # Pagination
    # --------------------------------------------------------

    total_pages = (
        (total_count + page_size - 1)
        // page_size
    )

    return {
        "success": True,
        "message": "Tickets fetched successfully.",
        "tickets": tickets,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total_count,
            "total_pages": total_pages,
        },
    }


# ============================================================
# GET CUSTOMER TICKET DETAILS
# ============================================================

@router.get(
    "/{ticket_id}",
    response_model=CustomerTicketDetailResponse,
)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_customer: dict = Depends(get_current_customer),
):
    """
    Get one customer ticket and all messages.

    Authorization:

        customer mobile
        +
        ticket.company_id

    NOT:

        JWT customer_profile_id alone.
    """

    # --------------------------------------------------------
    # Resolve mobile
    # --------------------------------------------------------

    mobile = get_customer_mobile(
        db=db,
        current_customer=current_customer,
    )

    # --------------------------------------------------------
    # Get ticket
    # --------------------------------------------------------

    ticket = get_customer_ticket_details(
        db=db,
        mobile=mobile,
        ticket_id=ticket_id,
    )

    if not ticket:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Ticket not found or you are not "
                "authorized to access it."
            ),
        )

    return ticket


# ============================================================
# ADD CUSTOMER MESSAGE
# ============================================================

@router.post(
    "/{ticket_id}/messages",
    response_model=TicketMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_message(
    ticket_id: int,
    data: TicketMessageCreate,
    db: Session = Depends(get_db),
    current_customer: dict = Depends(get_current_customer),
):
    """
    Add a customer message.

    Authorization:

        customer mobile
        +
        ticket.company_id

    The correct company-specific CustomerProfile
    is resolved by the service.
    """

    # --------------------------------------------------------
    # Resolve mobile
    # --------------------------------------------------------

    mobile = get_customer_mobile(
        db=db,
        current_customer=current_customer,
    )

    # --------------------------------------------------------
    # Create message
    # --------------------------------------------------------

    try:

        message = create_customer_message(
            db=db,
            mobile=mobile,
            ticket_id=ticket_id,
            message=data.message,
        )

        return message

    except ValueError as exc:

        error_message = str(exc)

        if (
            "not found" in error_message.lower()
            or "not authorized" in error_message.lower()
        ):

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_message,
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )
        
        
        