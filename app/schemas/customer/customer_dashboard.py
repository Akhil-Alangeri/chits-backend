from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class CustomerDashboardSummary(BaseModel):
    """The headline numbers for a customer's complete chit portfolio."""

    active_companies: int
    active_chits: int
    active_chit_net_worth: Decimal

    total_lift_records: int
    total_lifted_amount: Decimal

    # A lift result is calculated as: lifted payout - chit value.
    # Positive values are profit, negative values are loss.
    net_lift_result: Decimal
    lift_profit_amount: Decimal
    lift_loss_amount: Decimal
    lift_result_status: str

    total_paid_amount: Decimal
    total_pending_amount: Decimal


class CustomerDashboardChit(BaseModel):
    """An active customer slot shown in the dashboard portfolio."""

    chit_member_id: int
    chit_id: int
    company_id: int
    company_name: str

    chit_name: str
    chit_code: str
    chit_value: Decimal
    monthly_emi: Decimal
    duration_months: int
    start_date: date | None = None
    member_status: str


class CustomerDashboardLift(BaseModel):
    """A compact lift record for the dashboard activity list."""

    lift_id: int
    chit_member_id: int
    company_name: str
    chit_name: str
    chit_code: str
    lift_date: date
    lifted_amount: Decimal
    payout_status: str
    net_result: Decimal


class CustomerDashboardResponse(BaseModel):
    success: bool
    message: str
    summary: CustomerDashboardSummary
    active_chits: list[CustomerDashboardChit] = Field(default_factory=list)
    recent_lifts: list[CustomerDashboardLift] = Field(default_factory=list)
