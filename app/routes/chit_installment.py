from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from fastapi import APIRouter, Depends, HTTPException, Query, status

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.models.admin.user import User

from app.schemas.chit_installment import (
    ChitInstallmentResponse,
    ChitInstallmentsGenerate,
)

from app.services.chit_installment_service import (
    generate_installments_for_chit,
    get_installments_for_chit,
)

from app.services.payment_transaction import get_chit_payment_details

router = APIRouter(
    prefix="/chits",
    tags=["Chit Installments"],
)


# =========================================================
# GENERATE INSTALLMENTS
# =========================================================

@router.post(
    "/{chit_id}/installments/generate",
    response_model=List[ChitInstallmentResponse],
    status_code=status.HTTP_201_CREATED,
)
def generate_installments(
    chit_id: int,
    data: ChitInstallmentsGenerate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    result = generate_installments_for_chit(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
        start_date=data.start_date,
        installment_count=data.installment_count,
    )

    if isinstance(result, dict):

        error = result.get("error")

        if error == "chit_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chit not found.",
            )

        if error == "invalid_installment_count":

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Installment count must be greater than zero.",
            )

        if error == "no_confirmed_members":

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No confirmed members found for this chit.",
            )

        if error == "installments_already_generated":

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Installments have already been generated for this chit.",
            )

    return result


# =========================================================
# GET INSTALLMENTS
# =========================================================

@router.get(
    "/{chit_id}/installments",
    response_model=List[ChitInstallmentResponse],
)
def get_installments(
    chit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    result = get_installments_for_chit(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
    )

    if isinstance(result, dict):

        if result.get("error") == "chit_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chit not found.",
            )

    return result






# ==============================================================
#  GET CHIT PAYMENT DETAILS
 # ===========================================================
 
@router.get("/{chit_id}/payments")
def get_chit_payments(
    chit_id: int,

    month: int | None = Query(
        default=None,
        ge=1,
        le=12,
    ),

    year: int | None = Query(
        default=None,
        ge=2000,
        le=2100,
    ),

    status_filter: str | None = Query(
        default=None,
        alias="status",
    ),

    db: Session = Depends(get_db),

    # IMPORTANT:
    # Replace this with your existing auth dependency
    current_user=Depends(get_current_user),
):

    result = get_chit_payment_details(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
        month=month,
        year=year,
        status_filter=status_filter,
    )

    # =====================================================
    # CHIT NOT FOUND
    # =====================================================

    if (
        isinstance(result, dict)
        and result.get("error")
        == "chit_not_found"
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chit not found.",
        )

    # =====================================================
    # INVALID STATUS
    # =====================================================

    if (
        isinstance(result, dict)
        and result.get("error")
        == "invalid_status"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid payment status. "
                "Allowed values: all, paid, partial, due."
            ),
        )

    return result