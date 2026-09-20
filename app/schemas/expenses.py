from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ExpenseCategory = Literal[
    "office",
    "rent",
    "electricity",
    "salary",
    "transport",
    "maintenance",
    "other",
]

ExpensePaymentMethod = Literal[
    "cash",
    "upi",
]


class ExpenseCreate(BaseModel):
    category: ExpenseCategory
    amount: int = Field(..., gt=0)
    description: str | None = Field(default=None, max_length=2000)
    expense_date: date
    payment_method: ExpensePaymentMethod
    reference: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value):
        if value is None:
            return None

        value = value.strip()
        return value or None

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, value):
        if value is None:
            return None

        value = value.strip()
        return value or None

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value):
        if value is None:
            return None

        value = value.strip()
        return value or None


class ExpenseUpdate(BaseModel):
    category: ExpenseCategory | None = None
    amount: int | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=2000)
    expense_date: date | None = None
    payment_method: ExpensePaymentMethod | None = None
    reference: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=2000)

    reason: str = Field(
        ...,
        min_length=3,
        max_length=1000,
    )

    @field_validator("description")
    @classmethod
    def validate_description(cls, value):
        if value is None:
            return None

        value = value.strip()
        return value or None

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, value):
        if value is None:
            return None

        value = value.strip()
        return value or None

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value):
        if value is None:
            return None

        value = value.strip()
        return value or None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value):
        value = value.strip()

        if not value:
            raise ValueError("Edit reason is required.")

        return value


class ExpenseResponse(BaseModel):
    id: int
    company_id: int
    category: ExpenseCategory
    amount: int
    description: str | None
    expense_date: date
    payment_method: ExpensePaymentMethod
    reference: str | None
    notes: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)