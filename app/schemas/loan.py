from datetime import date

from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.loan_transaction import (
    LoanTransactionResponse,
)


# =========================================================
# TYPES
# =========================================================

LoanDirection = str
LoanInterestType = str
LoanStatus = str


# =========================================================
# CREATE
# =========================================================

class LoanCreate(BaseModel):
    person_name: str = Field(
        ...,
        min_length=2,
        max_length=150,
    )

    person_mobile: str | None = Field(
        default=None,
        max_length=20,
    )

    person_address: str | None = None

    notes: str | None = None

    direction: LoanDirection

    principal_amount: Decimal = Field(
        ...,
        gt=0,
    )

    # Example:
    # 3 = 3%
    interest_rate: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    interest_type: LoanInterestType = Field(
        default="monthly",
    )

    start_date: date

    due_date: date | None = None

    @field_validator("person_name")
    @classmethod
    def validate_person_name(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Person name is required."
            )

        return value

    @field_validator("person_mobile")
    @classmethod
    def normalize_mobile(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.due_date is not None
            and self.due_date < self.start_date
        ):
            raise ValueError(
                "Due date cannot be before start date."
            )

        return self


# =========================================================
# UPDATE
# =========================================================

class LoanUpdate(BaseModel):
    person_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=150,
    )

    person_mobile: str | None = Field(
        default=None,
        max_length=20,
    )

    person_address: str | None = None

    notes: str | None = None

    direction: LoanDirection | None = None

    principal_amount: Decimal | None = Field(
        default=None,
        gt=0,
    )

    interest_rate: Decimal | None = Field(
        default=None,
        ge=0,
    )

    interest_type: LoanInterestType | None = None

    start_date: date | None = None

    due_date: date | None = None

    status: LoanStatus | None = None

    @field_validator("person_name")
    @classmethod
    def validate_person_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Person name cannot be empty."
            )

        return value

    @field_validator("person_mobile")
    @classmethod
    def normalize_mobile(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.start_date is not None
            and self.due_date is not None
            and self.due_date < self.start_date
        ):
            raise ValueError(
                "Due date cannot be before start date."
            )

        return self


# =========================================================
# LOAN SUMMARY
# =========================================================

class LoanSummary(BaseModel):
    principal_amount: Decimal

    principal_paid: Decimal

    principal_balance: Decimal

    # -----------------------------------------------------
    # Interest configuration
    # -----------------------------------------------------

    interest_rate: Decimal

    interest_type: LoanInterestType

    # One complete month interest based on the
    # CURRENT outstanding principal.
    #
    # For yearly / one_time loans the service currently
    # returns zero here.
    monthly_interest: Decimal

    # -----------------------------------------------------
    # Loan age
    # -----------------------------------------------------

    loan_age_days: int

    loan_age_months: int

    # -----------------------------------------------------
    # Interest accounting
    # -----------------------------------------------------

    # Total interest accrued from loan start until
    # the requested/current calculation date.
    interest_calculated: Decimal

    # Total discount applied against interest.
    discount: Decimal

    # Actual interest payments received/paid,
    # calculated from UPI + cash.
    interest_paid: Decimal

    # interest_calculated - interest_paid - discount
    interest_outstanding: Decimal

    # -----------------------------------------------------
    # Overall accounting
    # -----------------------------------------------------

    # Principal repayments + interest payments.
    # Disbursement is NOT included.
    total_paid: Decimal

    # Principal balance + interest outstanding.
    total_outstanding: Decimal


# =========================================================
# LOAN RESPONSE
# =========================================================

class LoanResponse(BaseModel):
    id: int

    company_id: int

    person_name: str

    person_mobile: str | None

    person_address: str | None

    notes: str | None

    direction: LoanDirection

    principal_amount: Decimal

    interest_rate: Decimal

    interest_type: LoanInterestType

    start_date: date

    due_date: date | None

    status: LoanStatus

    created_by: int | None

    created_at: object

    updated_at: object | None = None

    model_config = ConfigDict(
        from_attributes=True,
    )


# =========================================================
# DETAIL RESPONSE
# =========================================================

class LoanDetailResponse(LoanResponse):
    summary: LoanSummary

    transactions: list[
        LoanTransactionResponse
    ] = Field(
        default_factory=list,
    )