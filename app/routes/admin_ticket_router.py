# ============================================================
# ADMIN SUPPORT TICKET ROUTES
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.admin.user import User

from app.schemas.support.ticket import (
    TicketMessageCreate,
    TicketMessageResponse,
    TicketStatusUpdate,
    TicketPriorityUpdate,
    TicketAssignmentUpdate,
    TicketCategoryUpdate,
    SupportTicketDetailResponse,
)

from app.services.support.ticket_service import (
    get_admin_tickets,
    get_admin_ticket_details,
    create_admin_message,
    update_ticket_status,
    update_ticket_priority,
    update_ticket_category,
    assign_ticket,
)
from app.services.audit_log_service import get_request_metadata


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/admin/tickets",
    tags=["Admin Support Tickets"],
)


# ============================================================
# GET ADMIN TICKETS
# ============================================================

@router.get("")
def list_tickets(
    status_filter: str | None = Query(
        default=None,
        alias="status",
    ),
    priority: str | None = None,
    assigned_to_user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get support tickets belonging only to the
    authenticated admin's company.
    """

    company_id = current_user.company_id

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Company information not found.",
        )

    try:

        tickets = get_admin_tickets(
            db=db,
            company_id=company_id,
            status=status_filter,
            priority=priority,
            assigned_to_user_id=assigned_to_user_id,
        )

        return {
            "success": True,
            "message": "Support tickets fetched successfully.",
            "tickets": tickets,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ============================================================
# GET ADMIN TICKET DETAILS
# ============================================================

@router.get(
    "/{ticket_id}",
    response_model=SupportTicketDetailResponse,
)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get one support ticket.

    Admin can only access tickets belonging
    to their own company.
    """

    company_id = current_user.company_id

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Company information not found.",
        )

    ticket = get_admin_ticket_details(
        db=db,
        company_id=company_id,
        ticket_id=ticket_id,
    )

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Support ticket not found.",
        )

    customer_name = None
    customer_mobile = None

    if ticket.customer_profile:

        customer_name = ticket.customer_profile.display_name
        customer_mobile = ticket.customer_profile.mobile

    return SupportTicketDetailResponse(
        id=ticket.id,
        ticket_number=ticket.ticket_number,
        company_id=ticket.company_id,
        customer_profile_id=ticket.customer_profile_id,

        customer_name=customer_name,
        customer_mobile=customer_mobile,

        subject=ticket.subject,
        description=ticket.description,
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        assigned_to_user_id=ticket.assigned_to_user_id,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
        messages=ticket.messages,
    )


# ============================================================
# ADD ADMIN MESSAGE
# ============================================================

@router.post(
    "/{ticket_id}/messages",
    status_code=status.HTTP_201_CREATED,
)
def add_message(
    ticket_id: int,
    data: TicketMessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add an admin/company reply to a customer ticket.
    """

    company_id = current_user.company_id
    user_id = current_user.id

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Company information not found.",
        )

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User information not found.",
        )

    ip_address, user_agent = get_request_metadata(request)

    try:

        message = create_admin_message(
            db=db,
            company_id=company_id,
            user_id=user_id,
            ticket_id=ticket_id,
            message=data.message,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "success": True,
            "message": "Message added successfully.",
            "data": message,
        }

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


# ============================================================
# UPDATE STATUS
# ============================================================

@router.patch("/{ticket_id}/status")
def change_status(
    ticket_id: int,
    data: TicketStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company_id = current_user.company_id

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Company information not found.",
        )

    ip_address, user_agent = get_request_metadata(request)

    try:

        ticket = update_ticket_status(
            db=db,
            company_id=company_id,
            ticket_id=ticket_id,
            status=data.status,
            updated_by=current_user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "success": True,
            "message": "Ticket status updated successfully.",
            "ticket": ticket,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ============================================================
# UPDATE PRIORITY
# ============================================================

@router.patch("/{ticket_id}/priority")
def change_priority(
    ticket_id: int,
    data: TicketPriorityUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company_id = current_user.company_id

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Company information not found.",
        )

    ip_address, user_agent = get_request_metadata(request)

    try:

        ticket = update_ticket_priority(
            db=db,
            company_id=company_id,
            ticket_id=ticket_id,
            priority=data.priority,
            updated_by=current_user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "success": True,
            "message": "Ticket priority updated successfully.",
            "ticket": ticket,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ============================================================
# UPDATE CATEGORY
# ============================================================

@router.patch("/{ticket_id}/category")
def change_category(
    ticket_id: int,
    data: TicketCategoryUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company_id = current_user.company_id

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Company information not found.",
        )

    ip_address, user_agent = get_request_metadata(request)

    try:

        ticket = update_ticket_category(
            db=db,
            company_id=company_id,
            ticket_id=ticket_id,
            category=data.category,
            updated_by=current_user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "success": True,
            "message": "Ticket category updated successfully.",
            "ticket": ticket,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ============================================================
# ASSIGN TICKET
# ============================================================

@router.patch("/{ticket_id}/assign")
def assign_ticket_to_user(
    ticket_id: int,
    data: TicketAssignmentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company_id = current_user.company_id

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Company information not found.",
        )

    ip_address, user_agent = get_request_metadata(request)

    try:

        ticket = assign_ticket(
            db=db,
            company_id=company_id,
            ticket_id=ticket_id,
            assigned_to_user_id=data.assigned_to_user_id,
            updated_by=current_user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "success": True,
            "message": "Ticket assignment updated successfully.",
            "ticket": ticket,
        }

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
