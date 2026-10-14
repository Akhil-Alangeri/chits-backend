# ============================================================
# SUPPORT TICKET SERVICE
# ============================================================

from datetime import datetime
from typing import Any

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.support.ticket import SupportTicket, TicketMessage
from app.models.admin.user import User
from app.models.admin.customer_profile import CustomerProfile
from app.services.audit_log_service import (
    create_audit_log,
    snapshot_model,
)


# ============================================================
# CONSTANTS
# ============================================================

TICKET_STATUS_OPEN = "open"
TICKET_STATUS_IN_PROGRESS = "in_progress"
TICKET_STATUS_WAITING_FOR_CUSTOMER = "waiting_for_customer"
TICKET_STATUS_RESOLVED = "resolved"
TICKET_STATUS_CLOSED = "closed"

VALID_TICKET_STATUSES = {
    TICKET_STATUS_OPEN,
    TICKET_STATUS_IN_PROGRESS,
    TICKET_STATUS_WAITING_FOR_CUSTOMER,
    TICKET_STATUS_RESOLVED,
    TICKET_STATUS_CLOSED,
}


TICKET_PRIORITY_LOW = "low"
TICKET_PRIORITY_MEDIUM = "medium"
TICKET_PRIORITY_HIGH = "high"
TICKET_PRIORITY_URGENT = "urgent"

VALID_TICKET_PRIORITIES = {
    TICKET_PRIORITY_LOW,
    TICKET_PRIORITY_MEDIUM,
    TICKET_PRIORITY_HIGH,
    TICKET_PRIORITY_URGENT,
}


VALID_TICKET_CATEGORIES = {
    "payment",
    "receipt",
    "chit_membership",
    "installment",
    "lift",
    "profile",
    "account",
    "technical",
    "other",
}


SENDER_TYPE_CUSTOMER = "customer"
SENDER_TYPE_ADMIN = "admin"


TICKET_AUDIT_FIELDS = [
    "id",
    "ticket_number",
    "customer_profile_id",
    "subject",
    "description",
    "category",
    "priority",
    "status",
    "assigned_to_user_id",
    "resolved_at",
    "closed_at",
]

TICKET_MESSAGE_AUDIT_FIELDS = [
    "id",
    "ticket_id",
    "sender_type",
    "sender_user_id",
    "sender_customer_profile_id",
]


def _ticket_snapshot(ticket: SupportTicket) -> dict:
    return snapshot_model(
        ticket,
        TICKET_AUDIT_FIELDS,
    )


def _ticket_message_snapshot(
    ticket_message: TicketMessage,
) -> dict:
    return snapshot_model(
        ticket_message,
        TICKET_MESSAGE_AUDIT_FIELDS,
    )


def _create_ticket_audit(
    db: Session,
    ticket: SupportTicket,
    *,
    action: str,
    description: str,
    user_id: int | None = None,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    create_audit_log(
        db=db,
        company_id=ticket.company_id,
        user_id=user_id,
        action=action,
        module="Support Tickets",
        entity_type="SupportTicket",
        entity_id=ticket.id,
        description=description,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )


# ============================================================
# INTERNAL HELPERS
# ============================================================

def _normalize_text(value: str | None) -> str:
    """
    Normalize user-entered text.
    """

    if value is None:
        return ""

    return value.strip()


def _validate_category(category: str) -> str:
    """
    Validate ticket category.
    """

    category = _normalize_text(category).lower()

    if category not in VALID_TICKET_CATEGORIES:
        raise ValueError(
            f"Invalid ticket category: {category}"
        )

    return category


def _validate_priority(priority: str) -> str:
    """
    Validate ticket priority.
    """

    priority = _normalize_text(priority).lower()

    if priority not in VALID_TICKET_PRIORITIES:
        raise ValueError(
            f"Invalid ticket priority: {priority}"
        )

    return priority


def _validate_status(status: str) -> str:
    """
    Validate ticket status.
    """

    status = _normalize_text(status).lower()

    if status not in VALID_TICKET_STATUSES:
        raise ValueError(
            f"Invalid ticket status: {status}"
        )

    return status


# ============================================================
# TICKET NUMBER GENERATION
# ============================================================

def generate_ticket_number(db: Session) -> str:
    """
    Generate the next ticket number.

    Examples:
        TKT-000001
        TKT-000002
        TKT-000003
    """

    last_ticket = (
        db.query(SupportTicket.ticket_number)
        .filter(
            SupportTicket.ticket_number.like("TKT-%")
        )
        .order_by(
            SupportTicket.id.desc()
        )
        .first()
    )

    if not last_ticket:
        return "TKT-000001"

    last_number = last_ticket[0]

    try:
        number_part = last_number.replace("TKT-", "")
        next_number = int(number_part) + 1

    except (ValueError, AttributeError):

        count = (
            db.query(func.count(SupportTicket.id))
            .scalar()
            or 0
        )

        next_number = count + 1

    return f"TKT-{next_number:06d}"


# ============================================================
# CUSTOMER AUTHORIZATION
# ============================================================

def get_customer_company_profile(
    db: Session,
    customer_profile_id: int,
    company_id: int,
) -> CustomerProfile | None:
    """
    Verify that a customer profile belongs to a company.
    """

    return (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.id == customer_profile_id,
            CustomerProfile.company_id == company_id,
            CustomerProfile.status == "active",
        )
        .first()
    )


def get_customer_profile_for_company(
    db: Session,
    mobile: str,
    company_id: int,
) -> CustomerProfile | None:
    """
    Resolve the company-specific customer profile
    using mobile + company_id.

    Example:

        Shiva:
            mobile = 7288010526
            profile_id = 3

        Megha:
            mobile = 7288010526
            profile_id = 7

    These are separate CustomerProfile records.
    """

    mobile = _normalize_text(mobile)

    if not mobile:
        return None

    return (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.mobile == mobile,
            CustomerProfile.company_id == company_id,
            CustomerProfile.status == "active",
        )
        .first()
    )


def get_customer_mobile_by_profile_id(
    db: Session,
    customer_profile_id: int,
) -> str | None:
    """
    Resolve customer mobile from the JWT customer_profile_id.

    Used as a fallback when the JWT does not contain
    the mobile number.
    """

    result = (
        db.query(CustomerProfile.mobile)
        .filter(
            CustomerProfile.id == customer_profile_id,
            CustomerProfile.status == "active",
        )
        .first()
    )

    if not result:
        return None

    return result[0]


def customer_can_access_company(
    db: Session,
    customer_profile_id: int,
    company_id: int,
) -> bool:
    """
    Check whether the customer profile belongs
    to the company.
    """

    profile = get_customer_company_profile(
        db=db,
        customer_profile_id=customer_profile_id,
        company_id=company_id,
    )

    return profile is not None


# ============================================================
# CUSTOMER TICKET AUTHORIZATION - LEGACY
# ============================================================

def get_customer_ticket(
    db: Session,
    customer_profile_id: int,
    ticket_id: int,
) -> SupportTicket | None:
    """
    Legacy customer ticket lookup.

    Kept for backward compatibility.

    New customer ticket details/messages should use
    mobile + ticket company authorization.
    """

    return (
        db.query(SupportTicket)
        .filter(
            SupportTicket.id == ticket_id,
            SupportTicket.customer_profile_id == customer_profile_id,
        )
        .first()
    )


def customer_can_access_ticket(
    db: Session,
    customer_profile_id: int,
    ticket_id: int,
) -> bool:
    """
    Legacy customer ticket access check.
    """

    return (
        get_customer_ticket(
            db=db,
            customer_profile_id=customer_profile_id,
            ticket_id=ticket_id,
        )
        is not None
    )


# ============================================================
# CREATE CUSTOMER TICKET
# ============================================================

def create_customer_ticket(
    db: Session,
    customer_profile_id: int,
    company_id: int,
    subject: str,
    description: str,
    category: str = "other",
    priority: str = "medium",
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SupportTicket:
    """
    Create a customer support ticket.

    The router resolves the correct company-specific
    CustomerProfile using:

        mobile + company_id

    and passes its profile ID here.
    """

    customer_profile = get_customer_company_profile(
        db=db,
        customer_profile_id=customer_profile_id,
        company_id=company_id,
    )

    if not customer_profile:
        raise ValueError(
            "You are not authorized to create a ticket for this company."
        )

    subject = _normalize_text(subject)
    description = _normalize_text(description)

    if not subject:
        raise ValueError(
            "Ticket subject is required."
        )

    if not description:
        raise ValueError(
            "Ticket description is required."
        )

    category = _validate_category(category)
    priority = _validate_priority(priority)

    ticket_number = generate_ticket_number(db)

    ticket = SupportTicket(
        ticket_number=ticket_number,
        company_id=company_id,
        customer_profile_id=customer_profile_id,
        subject=subject,
        description=description,
        category=category,
        priority=priority,
        status=TICKET_STATUS_OPEN,
    )

    db.add(ticket)
    db.flush()

    _create_ticket_audit(
        db,
        ticket,
        action="CREATE",
        description=(
            f"Customer created support ticket "
            f"'{ticket.ticket_number}'"
        ),
        new_values=_ticket_snapshot(ticket),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(ticket)

    return ticket


# ============================================================
# GET CUSTOMER TICKETS - PAGINATED
# ============================================================

def get_customer_tickets(
    db: Session,
    customer_profile_id: int,
    company_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
) -> tuple[list[SupportTicket], int]:
    """
    Get paginated customer tickets.

    Existing company/profile-based behavior is preserved.
    """

    if page < 1:
        page = 1

    if page_size < 1:
        page_size = 10

    if page_size > 100:
        page_size = 100

    query = (
        db.query(SupportTicket)
        .filter(
            SupportTicket.customer_profile_id
            == customer_profile_id
        )
    )

    if company_id is not None:
        query = query.filter(
            SupportTicket.company_id == company_id
        )

    if status is not None:
        status = _validate_status(status)

        query = query.filter(
            SupportTicket.status == status
        )

    allowed_sort_fields = {
        "created_at": SupportTicket.created_at,
        "updated_at": SupportTicket.updated_at,
        "status": SupportTicket.status,
        "ticket_number": SupportTicket.ticket_number,
    }

    sort_order = sort_order.lower()

    if sort_order not in {"asc", "desc"}:
        raise ValueError(
            "Invalid sort_order value. "
            "Allowed values: asc, desc."
        )

    priority_order = case(
        (
            SupportTicket.priority == "urgent",
            1,
        ),
        (
            SupportTicket.priority == "high",
            2,
        ),
        (
            SupportTicket.priority == "medium",
            3,
        ),
        (
            SupportTicket.priority == "low",
            4,
        ),
        else_=5,
    )

    if sort_by == "priority":

        if sort_order == "asc":

            query = query.order_by(
                priority_order.asc(),
                SupportTicket.updated_at.desc(),
                SupportTicket.id.desc(),
            )

        else:

            query = query.order_by(
                priority_order.desc(),
                SupportTicket.updated_at.desc(),
                SupportTicket.id.desc(),
            )

    else:

        if sort_by not in allowed_sort_fields:
            raise ValueError(
                "Invalid sort_by value. "
                "Allowed values: "
                "created_at, updated_at, status, "
                "priority, ticket_number."
            )

        sort_column = allowed_sort_fields[sort_by]

        if sort_order == "asc":

            query = query.order_by(
                sort_column.asc(),
                SupportTicket.id.asc(),
            )

        else:

            query = query.order_by(
                sort_column.desc(),
                SupportTicket.id.desc(),
            )

    total_count = query.order_by(None).count()

    offset = (page - 1) * page_size

    tickets = (
        query
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return tickets, total_count


# ============================================================
# CUSTOMER TICKET LOOKUP
# MOBILE + COMPANY-AWARE
# ============================================================

def get_customer_ticket_by_mobile(
    db: Session,
    mobile: str,
    ticket_id: int,
) -> tuple[SupportTicket, CustomerProfile] | None:
    """
    Resolve a customer ticket using:

        customer mobile
        +
        ticket company_id

    This is the main authorization function for
    customer ticket details and customer messages.

    It does NOT rely on the JWT customer_profile_id.
    """

    mobile = _normalize_text(mobile)

    if not mobile:
        return None

    result = (
        db.query(
            SupportTicket,
            CustomerProfile,
        )
        .join(
            CustomerProfile,
            CustomerProfile.id
            == SupportTicket.customer_profile_id,
        )
        .filter(
            # Exact ticket
            SupportTicket.id == ticket_id,

            # Same customer mobile
            CustomerProfile.mobile == mobile,

            # Profile must belong to ticket's company
            CustomerProfile.company_id
            == SupportTicket.company_id,

            # Only active profiles
            CustomerProfile.status == "active",
        )
        .first()
    )

    return result


# ============================================================
# GET CUSTOMER TICKET DETAILS
# ============================================================

def get_customer_ticket_details(
    db: Session,
    mobile: str,
    ticket_id: int,
) -> SupportTicket | None:
    """
    Get one customer ticket including messages.

    Authorization:

        mobile
        +
        ticket.company_id

    The JWT customer_profile_id is NOT used.
    """

    result = get_customer_ticket_by_mobile(
        db=db,
        mobile=mobile,
        ticket_id=ticket_id,
    )

    if not result:
        return None

    ticket, customer_profile = result

    # Load messages for response serialization.
    ticket.messages

    return ticket


# ============================================================
# CREATE CUSTOMER MESSAGE
# ============================================================

def create_customer_message(
    db: Session,
    mobile: str,
    ticket_id: int,
    message: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TicketMessage:
    """
    Add a customer reply to a ticket.

    Authorization:

        mobile
        +
        ticket.company_id

    The company-specific CustomerProfile is resolved
    automatically from the ticket.
    """

    result = get_customer_ticket_by_mobile(
        db=db,
        mobile=mobile,
        ticket_id=ticket_id,
    )

    if not result:
        raise ValueError(
            "Ticket not found or you are not authorized to access it."
        )

    ticket, customer_profile = result

    message = _normalize_text(message)

    if not message:
        raise ValueError(
            "Message cannot be empty."
        )

    if ticket.status == TICKET_STATUS_CLOSED:
        raise ValueError(
            "Closed tickets cannot receive new messages."
        )

    old_ticket_values = _ticket_snapshot(ticket)

    ticket_message = TicketMessage(
        ticket_id=ticket.id,
        sender_type=SENDER_TYPE_CUSTOMER,

        # IMPORTANT:
        # This is the profile belonging to the ticket's
        # company, not necessarily the JWT profile.
        sender_customer_profile_id=customer_profile.id,

        message=message,
    )

    db.add(ticket_message)

    # Customer replied after staff was waiting.
    if ticket.status == TICKET_STATUS_WAITING_FOR_CUSTOMER:
        ticket.status = TICKET_STATUS_IN_PROGRESS

    ticket.updated_at = datetime.utcnow()

    db.flush()

    create_audit_log(
        db=db,
        company_id=ticket.company_id,
        user_id=None,
        action="MESSAGE_CREATE",
        module="Support Ticket Messages",
        entity_type="TicketMessage",
        entity_id=ticket_message.id,
        description=(
            f"Customer added a message to support ticket "
            f"'{ticket.ticket_number}'"
        ),
        new_values=_ticket_message_snapshot(ticket_message),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    new_ticket_values = _ticket_snapshot(ticket)

    if old_ticket_values["status"] != new_ticket_values["status"]:
        _create_ticket_audit(
            db,
            ticket,
            action="STATUS_CHANGE",
            description=(
                f"Changed support ticket '{ticket.ticket_number}' "
                f"status from '{old_ticket_values['status']}' to "
                f"'{new_ticket_values['status']}'"
            ),
            old_values=old_ticket_values,
            new_values=new_ticket_values,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    db.commit()
    db.refresh(ticket_message)

    return ticket_message


# ============================================================
# ADMIN AUTHORIZATION
# ============================================================

def get_admin_ticket(
    db: Session,
    company_id: int,
    ticket_id: int,
) -> SupportTicket | None:
    """
    Get a ticket belonging to the admin's company.
    """

    return (
        db.query(SupportTicket)
        .filter(
            SupportTicket.id == ticket_id,
            SupportTicket.company_id == company_id,
        )
        .first()
    )


def admin_can_access_ticket(
    db: Session,
    company_id: int,
    ticket_id: int,
) -> bool:
    """
    Check whether a company admin can access a ticket.
    """

    return (
        get_admin_ticket(
            db=db,
            company_id=company_id,
            ticket_id=ticket_id,
        )
        is not None
    )


# ============================================================
# CREATE ADMIN TICKET
# ============================================================

def create_admin_ticket(
    db: Session,
    company_id: int,
    customer_profile_id: int,
    subject: str,
    description: str,
    category: str = "other",
    priority: str = "medium",
    created_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SupportTicket:
    """
    Allow company staff/admin to create a ticket on behalf
    of a customer belonging to the same company.
    """

    customer_profile = get_customer_company_profile(
        db=db,
        customer_profile_id=customer_profile_id,
        company_id=company_id,
    )

    if not customer_profile:
        raise ValueError(
            "Customer does not belong to this company."
        )

    subject = _normalize_text(subject)
    description = _normalize_text(description)

    if not subject:
        raise ValueError(
            "Ticket subject is required."
        )

    if not description:
        raise ValueError(
            "Ticket description is required."
        )

    category = _validate_category(category)
    priority = _validate_priority(priority)

    ticket_number = generate_ticket_number(db)

    ticket = SupportTicket(
        ticket_number=ticket_number,
        company_id=company_id,
        customer_profile_id=customer_profile_id,
        subject=subject,
        description=description,
        category=category,
        priority=priority,
        status=TICKET_STATUS_OPEN,
    )

    db.add(ticket)
    db.flush()

    _create_ticket_audit(
        db,
        ticket,
        action="CREATE",
        description=(
            f"Created support ticket "
            f"'{ticket.ticket_number}'"
        ),
        user_id=created_by,
        new_values=_ticket_snapshot(ticket),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(ticket)

    return ticket


# ============================================================
# GET ADMIN TICKETS
# ============================================================

def get_admin_tickets(
    db: Session,
    company_id: int,
    status: str | None = None,
    priority: str | None = None,
    assigned_to_user_id: int | None = None,
) -> list[SupportTicket]:
    """
    Get tickets belonging only to the authenticated admin's
    company.
    """

    query = (
        db.query(SupportTicket)
        .filter(
            SupportTicket.company_id == company_id
        )
    )

    if status is not None:

        status = _validate_status(status)

        query = query.filter(
            SupportTicket.status == status
        )

    if priority is not None:

        priority = _validate_priority(priority)

        query = query.filter(
            SupportTicket.priority == priority
        )

    if assigned_to_user_id is not None:

        query = query.filter(
            SupportTicket.assigned_to_user_id
            == assigned_to_user_id
        )

    return (
        query
        .order_by(
            SupportTicket.updated_at.desc(),
            SupportTicket.id.desc(),
        )
        .all()
    )


# ============================================================
# GET ADMIN TICKET DETAILS
# ============================================================

def get_admin_ticket_details(
    db: Session,
    company_id: int,
    ticket_id: int,
) -> SupportTicket | None:
    """
    Get one ticket belonging to the admin's company.
    """

    ticket = get_admin_ticket(
        db=db,
        company_id=company_id,
        ticket_id=ticket_id,
    )

    if not ticket:
        return None

    ticket.messages

    return ticket


# ============================================================
# CREATE ADMIN MESSAGE
# ============================================================

def create_admin_message(
    db: Session,
    company_id: int,
    user_id: int,
    ticket_id: int,
    message: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TicketMessage:
    """
    Add a company/admin reply to a ticket.
    """

    ticket = get_admin_ticket(
        db=db,
        company_id=company_id,
        ticket_id=ticket_id,
    )

    if not ticket:
        raise ValueError(
            "Ticket not found or you are not authorized to access it."
        )

    message = _normalize_text(message)

    if not message:
        raise ValueError(
            "Message cannot be empty."
        )

    if ticket.status == TICKET_STATUS_CLOSED:
        raise ValueError(
            "Closed tickets cannot receive new messages."
        )

    old_ticket_values = _ticket_snapshot(ticket)

    ticket_message = TicketMessage(
        ticket_id=ticket.id,
        sender_type=SENDER_TYPE_ADMIN,
        sender_user_id=user_id,
        message=message,
    )

    db.add(ticket_message)

    if ticket.status in {
        TICKET_STATUS_OPEN,
        TICKET_STATUS_WAITING_FOR_CUSTOMER,
    }:
        ticket.status = TICKET_STATUS_IN_PROGRESS

    ticket.updated_at = datetime.utcnow()

    db.flush()

    create_audit_log(
        db=db,
        company_id=ticket.company_id,
        user_id=user_id,
        action="MESSAGE_CREATE",
        module="Support Ticket Messages",
        entity_type="TicketMessage",
        entity_id=ticket_message.id,
        description=(
            f"Added an admin message to support ticket "
            f"'{ticket.ticket_number}'"
        ),
        new_values=_ticket_message_snapshot(ticket_message),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    new_ticket_values = _ticket_snapshot(ticket)

    if old_ticket_values["status"] != new_ticket_values["status"]:
        _create_ticket_audit(
            db,
            ticket,
            action="STATUS_CHANGE",
            description=(
                f"Changed support ticket '{ticket.ticket_number}' "
                f"status from '{old_ticket_values['status']}' to "
                f"'{new_ticket_values['status']}'"
            ),
            user_id=user_id,
            old_values=old_ticket_values,
            new_values=new_ticket_values,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    db.commit()
    db.refresh(ticket_message)

    return ticket_message


# ============================================================
# GET TICKET MESSAGES
# ============================================================

def get_ticket_messages(
    db: Session,
    ticket_id: int,
) -> list[TicketMessage]:
    """
    Get messages belonging to a ticket.
    """

    return (
        db.query(TicketMessage)
        .filter(
            TicketMessage.ticket_id == ticket_id
        )
        .order_by(
            TicketMessage.created_at.asc(),
            TicketMessage.id.asc(),
        )
        .all()
    )


# ============================================================
# UPDATE STATUS
# ============================================================

def update_ticket_status(
    db: Session,
    company_id: int,
    ticket_id: int,
    status: str,
    updated_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SupportTicket:
    """
    Update ticket status.
    """

    ticket = get_admin_ticket(
        db=db,
        company_id=company_id,
        ticket_id=ticket_id,
    )

    if not ticket:
        raise ValueError(
            "Ticket not found or you are not authorized to update it."
        )

    status = _validate_status(status)

    old_values = _ticket_snapshot(ticket)

    now = datetime.utcnow()

    ticket.status = status
    ticket.updated_at = now

    if status == TICKET_STATUS_RESOLVED:

        if ticket.resolved_at is None:
            ticket.resolved_at = now

    if status == TICKET_STATUS_CLOSED:

        if ticket.closed_at is None:
            ticket.closed_at = now

        if ticket.resolved_at is None:
            ticket.resolved_at = now

    if status in {
        TICKET_STATUS_OPEN,
        TICKET_STATUS_IN_PROGRESS,
        TICKET_STATUS_WAITING_FOR_CUSTOMER,
    }:
        ticket.closed_at = None

    db.flush()

    new_values = _ticket_snapshot(ticket)

    _create_ticket_audit(
        db,
        ticket,
        action="STATUS_CHANGE",
        description=(
            f"Changed support ticket '{ticket.ticket_number}' "
            f"status from '{old_values['status']}' to "
            f"'{new_values['status']}'"
        ),
        user_id=updated_by,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(ticket)

    return ticket


# ============================================================
# UPDATE PRIORITY
# ============================================================

def update_ticket_priority(
    db: Session,
    company_id: int,
    ticket_id: int,
    priority: str,
    updated_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SupportTicket:
    """
    Update ticket priority.
    """

    ticket = get_admin_ticket(
        db=db,
        company_id=company_id,
        ticket_id=ticket_id,
    )

    if not ticket:
        raise ValueError(
            "Ticket not found or you are not authorized to update it."
        )

    priority = _validate_priority(priority)

    old_values = _ticket_snapshot(ticket)

    ticket.priority = priority
    ticket.updated_at = datetime.utcnow()

    db.flush()

    new_values = _ticket_snapshot(ticket)

    _create_ticket_audit(
        db,
        ticket,
        action="PRIORITY_CHANGE",
        description=(
            f"Changed support ticket '{ticket.ticket_number}' "
            f"priority from '{old_values['priority']}' to "
            f"'{new_values['priority']}'"
        ),
        user_id=updated_by,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(ticket)

    return ticket


# ============================================================
# UPDATE CATEGORY
# ============================================================

def update_ticket_category(
    db: Session,
    company_id: int,
    ticket_id: int,
    category: str,
    updated_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SupportTicket:
    """
    Update ticket category.
    """

    ticket = get_admin_ticket(
        db=db,
        company_id=company_id,
        ticket_id=ticket_id,
    )

    if not ticket:
        raise ValueError(
            "Ticket not found or you are not authorized to update it."
        )

    category = _validate_category(category)

    old_values = _ticket_snapshot(ticket)

    ticket.category = category
    ticket.updated_at = datetime.utcnow()

    db.flush()

    new_values = _ticket_snapshot(ticket)

    _create_ticket_audit(
        db,
        ticket,
        action="CATEGORY_CHANGE",
        description=(
            f"Changed support ticket '{ticket.ticket_number}' "
            f"category from '{old_values['category']}' to "
            f"'{new_values['category']}'"
        ),
        user_id=updated_by,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(ticket)

    return ticket


# ============================================================
# ASSIGN TICKET
# ============================================================

def assign_ticket(
    db: Session,
    company_id: int,
    ticket_id: int,
    assigned_to_user_id: int | None,
    updated_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SupportTicket:
    """
    Assign a ticket to a company user.

    Passing None removes the assignment.
    """

    ticket = get_admin_ticket(
        db=db,
        company_id=company_id,
        ticket_id=ticket_id,
    )

    if not ticket:
        raise ValueError(
            "Ticket not found or you are not authorized to update it."
        )

    old_values = _ticket_snapshot(ticket)

    # --------------------------------------------------------
    # Remove assignment
    # --------------------------------------------------------

    if assigned_to_user_id is None:

        ticket.assigned_to_user_id = None
        ticket.updated_at = datetime.utcnow()

        db.flush()

        new_values = _ticket_snapshot(ticket)

        _create_ticket_audit(
            db,
            ticket,
            action="ASSIGN",
            description=(
                f"Removed assignment from support ticket "
                f"'{ticket.ticket_number}'"
            ),
            user_id=updated_by,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.commit()
        db.refresh(ticket)

        return ticket

    # --------------------------------------------------------
    # Verify assigned user
    # --------------------------------------------------------

    user = (
        db.query(User)
        .filter(
            User.id == assigned_to_user_id,
            User.company_id == company_id,
        )
        .first()
    )

    if not user:
        raise ValueError(
            "The selected user does not belong to this company."
        )

    ticket.assigned_to_user_id = assigned_to_user_id
    ticket.updated_at = datetime.utcnow()

    if ticket.status == TICKET_STATUS_OPEN:
        ticket.status = TICKET_STATUS_IN_PROGRESS

    db.flush()

    new_values = _ticket_snapshot(ticket)

    _create_ticket_audit(
        db,
        ticket,
        action="ASSIGN",
        description=(
            f"Assigned support ticket '{ticket.ticket_number}' "
            f"to user #{assigned_to_user_id}"
        ),
        user_id=updated_by,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if old_values["status"] != new_values["status"]:
        _create_ticket_audit(
            db,
            ticket,
            action="STATUS_CHANGE",
            description=(
                f"Changed support ticket '{ticket.ticket_number}' "
                f"status from '{old_values['status']}' to "
                f"'{new_values['status']}'"
            ),
            user_id=updated_by,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    db.commit()
    db.refresh(ticket)

    return ticket


# ============================================================
# GENERAL TICKET UPDATE
# ============================================================

def update_ticket(
    db: Session,
    company_id: int,
    ticket_id: int,
    subject: str | None = None,
    description: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    assigned_to_user_id: int | None = None,
    updated_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SupportTicket:
    """
    General admin ticket update.

    Only supplied fields are changed.
    """

    ticket = get_admin_ticket(
        db=db,
        company_id=company_id,
        ticket_id=ticket_id,
    )

    if not ticket:
        raise ValueError(
            "Ticket not found or you are not authorized to update it."
        )

    old_values = _ticket_snapshot(ticket)

    # --------------------------------------------------------
    # Subject
    # --------------------------------------------------------

    if subject is not None:

        subject = _normalize_text(subject)

        if not subject:
            raise ValueError(
                "Ticket subject cannot be empty."
            )

        ticket.subject = subject

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    if description is not None:

        description = _normalize_text(description)

        if not description:
            raise ValueError(
                "Ticket description cannot be empty."
            )

        ticket.description = description

    # --------------------------------------------------------
    # Category
    # --------------------------------------------------------

    if category is not None:
        ticket.category = _validate_category(category)

    # --------------------------------------------------------
    # Priority
    # --------------------------------------------------------

    if priority is not None:
        ticket.priority = _validate_priority(priority)

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    if status is not None:

        status = _validate_status(status)

        now = datetime.utcnow()

        ticket.status = status

        if status == TICKET_STATUS_RESOLVED:

            if ticket.resolved_at is None:
                ticket.resolved_at = now

        elif status == TICKET_STATUS_CLOSED:

            if ticket.resolved_at is None:
                ticket.resolved_at = now

            if ticket.closed_at is None:
                ticket.closed_at = now

        else:

            ticket.closed_at = None

    # --------------------------------------------------------
    # Assignment
    # --------------------------------------------------------

    if assigned_to_user_id is not None:

        user = (
            db.query(User)
            .filter(
                User.id == assigned_to_user_id,
                User.company_id == company_id,
            )
            .first()
        )

        if not user:
            raise ValueError(
                "The selected user does not belong to this company."
            )

        ticket.assigned_to_user_id = assigned_to_user_id

    ticket.updated_at = datetime.utcnow()

    db.flush()

    new_values = _ticket_snapshot(ticket)

    if old_values["status"] != new_values["status"]:
        action = "STATUS_CHANGE"
        description = (
            f"Changed support ticket '{ticket.ticket_number}' "
            f"status from '{old_values['status']}' to "
            f"'{new_values['status']}'"
        )
    elif old_values["priority"] != new_values["priority"]:
        action = "PRIORITY_CHANGE"
        description = (
            f"Changed support ticket '{ticket.ticket_number}' "
            f"priority from '{old_values['priority']}' to "
            f"'{new_values['priority']}'"
        )
    elif old_values["category"] != new_values["category"]:
        action = "CATEGORY_CHANGE"
        description = (
            f"Changed support ticket '{ticket.ticket_number}' "
            f"category from '{old_values['category']}' to "
            f"'{new_values['category']}'"
        )
    elif (
        old_values["assigned_to_user_id"]
        != new_values["assigned_to_user_id"]
    ):
        action = "ASSIGN"
        description = (
            f"Updated assignment for support ticket "
            f"'{ticket.ticket_number}'"
        )
    else:
        action = "UPDATE"
        description = (
            f"Updated support ticket '{ticket.ticket_number}'"
        )

    _create_ticket_audit(
        db,
        ticket,
        action=action,
        description=description,
        user_id=updated_by,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(ticket)

    return ticket


# ============================================================
# DELETE TICKET
# ============================================================

def delete_ticket(
    db: Session,
    company_id: int,
    ticket_id: int,
    deleted_by: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> bool:
    """
    Delete a ticket belonging to the company.

    Ticket messages are deleted automatically because
    the model relationship uses cascade.
    """

    ticket = get_admin_ticket(
        db=db,
        company_id=company_id,
        ticket_id=ticket_id,
    )

    if not ticket:
        return False

    old_values = _ticket_snapshot(ticket)
    ticket_number = ticket.ticket_number

    db.delete(ticket)
    db.flush()

    _create_ticket_audit(
        db,
        ticket,
        action="DELETE",
        description=(
            f"Deleted support ticket '{ticket_number}'"
        ),
        user_id=deleted_by,
        old_values=old_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()

    return True
