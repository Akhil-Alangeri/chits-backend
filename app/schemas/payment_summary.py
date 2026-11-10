from pydantic import BaseModel, Field


class ChitPaymentSummaryResponse(BaseModel):

    total_due: int

    total_paid: int

    total_remaining: int

    paid_installments: int

    partial_installments: int

    pending_installments: int

    total_lift_amount: float

    others_amount: int

    this_month_collections: int = Field(
        description="Payments allocated to the selected installment month, regardless of payment date.",
    )

    this_month_due: int

    current_month: int

    current_year: int

    reference_month: int

    reference_year: int
    


class MemberPaymentSummaryResponse(BaseModel):

    member_id: int

    member_number: int

    customer_profile_id: int

    member_name: str

    total_due: int

    total_paid: int

    total_remaining: int
    
    
