from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
LoginId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: Name
    login_id: LoginId


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        if len(value) < 8 or len(value.encode("utf-8")) > 72:
            raise ValueError("Password must have at least 8 characters and at most 72 UTF-8 bytes.")
        return value


class UserCreate(UserUpdate, PasswordChange):
    pass


class UserStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "inactive"]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str | None
    login_id: str
    role: str
    status: str
    created_at: datetime | None
    updated_at: datetime | None
