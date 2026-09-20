from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


# =========================================================
# TRANSACTION TYPE
# =========================================================

LoanTransactionType = Literal[
    "disbursement",
    "principal_repayment",
    "interest_payment",
]


# =========================================================
# CREATE
# =========================================================

class LoanTransactionCreate(BaseModel):
    transaction_date: date

    transaction_type: LoanTransactionType

    # -----------------------------------------------------
    # Principal
    # -----------------------------------------------------

    principal_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    # -----------------------------------------------------
    # Interest discount
    #
    # Interest itself is NEVER manually entered.
    # Backend calculates it automatically.
    # -----------------------------------------------------

    discount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    # -----------------------------------------------------
    # Actual payment split
    # -----------------------------------------------------

    upi_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    cash_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    # -----------------------------------------------------
    # Optional information
    # -----------------------------------------------------

    reference: str | None = Field(
        default=None,
        max_length=150,
    )

    notes: str | None = Field(
        default=None,
        max_length=1000,
    )

    # -----------------------------------------------------
    # Validation
    # -----------------------------------------------------

    @model_validator(mode="after")
    def validate_transaction(self):

        payment_total = (
            self.upi_amount
            + self.cash_amount
        )

        # =================================================
        # DISBURSEMENT
        # =================================================

        if self.transaction_type == "disbursement":

            if self.principal_amount <= 0:
                raise ValueError(
                    "Disbursement must contain principal amount."
                )

            if self.discount != 0:
                raise ValueError(
                    "Discount is allowed only for interest payment."
                )

        # =================================================
        # PRINCIPAL REPAYMENT
        # =================================================

        elif self.transaction_type == "principal_repayment":

            if self.principal_amount <= 0:
                raise ValueError(
                    "Principal repayment must contain principal amount."
                )

            if self.discount != 0:
                raise ValueError(
                    "Discount is allowed only for interest payment."
                )

        # =================================================
        # INTEREST PAYMENT
        # =================================================

        elif self.transaction_type == "interest_payment":

            if self.principal_amount != 0:
                raise ValueError(
                    "Interest payment cannot contain principal amount."
                )

            # Interest amount is calculated in service.
            # Client sends only:
            #
            #   discount
            #   upi_amount
            #   cash_amount

        # =================================================
        # COMMON PAYMENT VALIDATION
        # =================================================

        if payment_total < 0:
            raise ValueError(
                "UPI and cash amounts cannot be negative."
            )

        return self


# =========================================================
# RESPONSE
# =========================================================

class LoanTransactionResponse(BaseModel):
    id: int

    company_id: int

    loan_id: int

    transaction_date: date

    transaction_type: LoanTransactionType

    # Actual principal involved in this transaction.
    principal_amount: Decimal

    # Backend-calculated gross interest amount.
    #
    # For interest payment:
    #
    # interest_amount =
    # payment_amount + discount
    #
    # For other transaction types:
    # 0
    interest_amount: Decimal

    # Discount applied to interest.
    discount: Decimal

    # Actual payment split.
    upi_amount: Decimal

    cash_amount: Decimal

    reference: str | None

    notes: str | None

    created_by: int | None

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )