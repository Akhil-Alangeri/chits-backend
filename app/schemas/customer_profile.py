from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict


class CustomerProfileCreate(BaseModel):

    display_name: str

    legal_name: str | None = None

    mobile: str

    email: str | None = None

    address: str | None = None


class CustomerProfileUpdate(BaseModel):

    display_name: str

    legal_name: str | None = None

    mobile: str

    email: str | None = None

    address: str | None = None

    status: str = "active"


class CustomerProfileResponse(BaseModel):

    id: int

    company_id: int

    customer_code: str

    display_name: str

    legal_name: str | None

    mobile: str

    email: str | None

    address: str | None

    status: str

    user_id: int | None

    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True
    )
    
    
    
class CustomerChitMembershipResponse(BaseModel):

    chit_id: int

    chit_name: str

    chit_code: str

    member_id: int

    member_number: int

    member_name: str

    status: str


class CustomerDetailsResponse(BaseModel):

    customer: CustomerProfileResponse

    active_chits: List[
        CustomerChitMembershipResponse
    ]
    
class CustomerChitMembershipResponse(BaseModel):

    chit_id: int

    chit_name: str

    chit_code: str

    member_id: int

    member_number: int

    member_name: str

    status: str

    total_due: int

    total_paid: int

    remaining_amount: int

    total_months: int

    paid_months: int

    remaining_months: int


class CustomerDetailsResponse(BaseModel):

    customer: CustomerProfileResponse

    active_chits: List[
        CustomerChitMembershipResponse
    ]