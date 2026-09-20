from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChitMemberCreate(BaseModel):

    customer_profile_id: int

    member_name: str

    notes: str | None = None
    slot_number:int| None =None


class ChitMemberUpdate(BaseModel):

    member_name: str | None = None

    status: str | None = None

    cancel_reason: str | None = None

    notes: str | None = None
    slot_number:int


class ChitMemberResponse(BaseModel):

    id: int

    chit_id: int

    customer_profile_id: int

    member_number: int

    member_name: str

    status: str

    joined_at: datetime | None

    confirmed_at: datetime | None

    cancelled_at: datetime | None

    cancel_reason: str | None

    notes: str | None
    slot_number:int| None =None

    model_config = ConfigDict(
        from_attributes=True
    )