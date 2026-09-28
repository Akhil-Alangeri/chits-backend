from pydantic import BaseModel


class CustomerProfileData(BaseModel):
    customer_profile_id: int
    customer_code: str
    display_name: str | None = None
    legal_name: str | None = None
    mobile: str
    email: str | None = None
    address: str | None = None
    status: str


class CustomerProfileResponse(BaseModel):
    success: bool
    message: str
    profile: CustomerProfileData