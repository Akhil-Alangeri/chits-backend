
from typing import Optional

from pydantic import BaseModel


class CompanyLoginRequest(BaseModel):
    login_id: str
    password: str


class CompanyResponse(BaseModel):
    id: int
    company_name: str
    login_id: str
    email: str
    logo_url: Optional[str] = None


class CompanyLoginResponse(BaseModel):
    success: bool
    message: str
    access_token: str
    token_type: str
    company: CompanyResponse

