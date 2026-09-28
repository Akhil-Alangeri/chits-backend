from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# ENUM-LIKE VALUES
# ============================================================

# Ticket status values:
# open
# in_progress
# waiting_for_customer
# resolved
# closed

# Ticket priority values:
# low
# medium
# high
# urgent

# Ticket categories:
# payment
# receipt
# chit_membership
# installment
# lift
# profile
# account
# technical
# other


# ============================================================
# TICKET CREATE
# ============================================================

class SupportTicketCreate(BaseModel):
    """
    Customer creates a new support ticket.
    """

    subject: str = Field(
        ...,
        min_length=3,
        max_length=200,
    )

    description: str = Field(
        ...,
        min_length=1,
    )

    category: str = Field(
        default="other",
        max_length=50,
    )

    priority: str = Field(
        default="medium",
        max_length=20,
    )


# ============================================================
# TICKET MESSAGE CREATE
# ============================================================

class TicketMessageCreate(BaseModel):
    """
    Create a message/reply inside a ticket.

    sender information is NOT accepted from the frontend.
    The backend determines the sender from the authenticated user.
    """

    message: str = Field(
        ...,
        min_length=1,
    )


# ============================================================
# TICKET MESSAGE RESPONSE
# ============================================================

class TicketMessageResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    ticket_id: int

    sender_type: str

    sender_user_id: int | None = None

    sender_customer_profile_id: int | None = None

    message: str

    created_at: datetime

    updated_at: datetime


# ============================================================
# TICKET LIST RESPONSE
# ============================================================

class SupportTicketListResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    ticket_number: str

    company_id: int

    customer_profile_id: int

    subject: str

    category: str

    priority: str

    status: str

    assigned_to_user_id: int | None = None

    created_at: datetime

    updated_at: datetime

    resolved_at: datetime | None = None

    closed_at: datetime | None = None



# ============================================================
# CUSTOMER TICKET DETAIL RESPONSE
# ============================================================

class CustomerTicketDetailResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    ticket_number: str

    company_id: int

    customer_profile_id: int

    customer_name: str | None = None
    customer_mobile: str | None = None

    subject: str

    description: str

    category: str

    priority: str

    status: str

    assigned_to_user_id: int | None = None

    created_at: datetime

    updated_at: datetime

    resolved_at: datetime | None = None

    closed_at: datetime | None = None

    messages: list[TicketMessageResponse] = Field(
        default_factory=list
    )
# ============================================================
# STATUS UPDATE
# ============================================================

class TicketStatusUpdate(BaseModel):
    """
    Admin changes the ticket status.
    """

    status: str = Field(
        ...,
        max_length=30,
    )


# ============================================================
# PRIORITY UPDATE
# ============================================================

class TicketPriorityUpdate(BaseModel):
    """
    Admin changes the ticket priority.
    """

    priority: str = Field(
        ...,
        max_length=20,
    )


# ============================================================
# ASSIGNMENT
# ============================================================

class TicketAssignmentUpdate(BaseModel):
    """
    Assign or unassign a ticket to a company user/admin.

    null = remove current assignment.
    """

    assigned_to_user_id: int | None = None


# ============================================================
# CATEGORY UPDATE
# ============================================================

class TicketCategoryUpdate(BaseModel):
    """
    Allows admin to change ticket category.
    """

    category: str = Field(
        ...,
        max_length=50,
    )


# ============================================================
# GENERAL TICKET UPDATE
# ============================================================

class SupportTicketUpdate(BaseModel):
    """
    Optional general ticket update.

    All fields are optional so admin can update
    only the required values.
    """

    subject: str | None = Field(
        default=None,
        min_length=3,
        max_length=200,
    )

    description: str | None = Field(
        default=None,
        min_length=1,
    )

    category: str | None = Field(
        default=None,
        max_length=50,
    )

    priority: str | None = Field(
        default=None,
        max_length=20,
    )

    status: str | None = Field(
        default=None,
        max_length=30,
    )

    assigned_to_user_id: int | None = None


# ============================================================
# CUSTOMER TICKET LIST RESPONSE
# ============================================================

class CustomerTicketListResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    ticket_number: str

    subject: str

    category: str

    priority: str

    status: str

    assigned_to_user_id: int | None = None

    created_at: datetime

    updated_at: datetime

    resolved_at: datetime | None = None

    closed_at: datetime | None = None


# ============================================================
# CUSTOMER TICKET DETAIL RESPONSE
# ============================================================

class SupportTicketDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_number: str

    company_id: int

    customer_profile_id: int

    # Customer information
    customer_name: str | None = None
    customer_mobile: str | None = None

    subject: str
    description: str

    category: str
    priority: str
    status: str

    assigned_to_user_id: int | None = None

    created_at: datetime
    updated_at: datetime

    resolved_at: datetime | None = None
    closed_at: datetime | None = None

    messages: list[TicketMessageResponse] = Field(
        default_factory=list
    )
# ============================================================
# CUSTOMER TICKET LIST WRAPPER
# ============================================================

class CustomerTicketListApiResponse(BaseModel):

    success: bool

    message: str

    tickets: list[CustomerTicketListResponse] = Field(
        default_factory=list
    )


# ============================================================
# CUSTOMER TICKET DETAIL WRAPPER
# ============================================================

class CustomerTicketDetailApiResponse(BaseModel):

    success: bool

    message: str

    ticket: CustomerTicketDetailResponse


# ============================================================
# TICKET MESSAGE LIST RESPONSE
# ============================================================

class TicketMessageListResponse(BaseModel):

    success: bool

    message: str

    messages: list[TicketMessageResponse] = Field(
        default_factory=list
    )


# ============================================================
# TICKET CREATE RESPONSE
# ============================================================

class SupportTicketCreateResponse(BaseModel):

    success: bool

    message: str

    ticket: SupportTicketDetailResponse


# ============================================================
# MESSAGE CREATE RESPONSE
# ============================================================

class TicketMessageCreateResponse(BaseModel):

    success: bool

    message: str

    data: TicketMessageResponse


# ============================================================
# STATUS UPDATE RESPONSE
# ============================================================

class TicketStatusUpdateResponse(BaseModel):

    success: bool

    message: str

    ticket: SupportTicketDetailResponse


# ============================================================
# PRIORITY UPDATE RESPONSE
# ============================================================

class TicketPriorityUpdateResponse(BaseModel):

    success: bool

    message: str

    ticket: SupportTicketDetailResponse


# ============================================================
# ASSIGNMENT UPDATE RESPONSE
# ============================================================

class TicketAssignmentUpdateResponse(BaseModel):

    success: bool

    message: str

    ticket: SupportTicketDetailResponse
    
    
    
# ============================================================
# CUSTOMER TICKET PAGINATION
# ============================================================

class CustomerTicketPagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class CustomerTicketPaginatedResponse(BaseModel):
    success: bool
    message: str
    tickets: list[CustomerTicketListResponse] = Field(
        default_factory=list
    )
    pagination: CustomerTicketPagination
    
    
# ============================================================
# CUSTOMER TICKET CREATE
# ============================================================

class CustomerSupportTicketCreate(BaseModel):
    """
    Customer creates a new support ticket.

    company_id is supplied by the customer to identify
    which company the ticket belongs to.

    customer_profile_id is NOT accepted from the frontend.
    It is taken from the authenticated customer JWT.
    """

    company_id: int

    subject: str = Field(
        ...,
        min_length=3,
        max_length=200,
    )

    description: str = Field(
        ...,
        min_length=1,
    )

    category: str = Field(
        default="other",
        max_length=50,
    )

    priority: str = Field(
        default="medium",
        max_length=20,
    )