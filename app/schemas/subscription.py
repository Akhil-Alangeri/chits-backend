from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=150)
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=80)
    description: str | None = Field(default=None, max_length=5000)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    billing_cycle: Literal["monthly", "quarterly", "yearly", "one_time"]
    is_active: StrictBool = True
    features: dict[str, StrictBool] = Field(default_factory=dict)


class CompanySubscriptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: int = Field(gt=0)
    overrides: dict[str, StrictBool | None] = Field(default_factory=dict)
