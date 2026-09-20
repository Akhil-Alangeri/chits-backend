from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.models.admin.user import User

from app.schemas.payment_trancation import (
    PaymentTransactionCreate,
    PaymentTransactionResponse,
    PaymentTransactionUpdate,
    PaymentHistoryResponse
)

from app.services.payment_transaction import (
    create_payment_transaction,
    get_payments_for_installment,
    delete_payment,
    update_payment,
    get_customer_chit_payment_history
)


router = APIRouter(
    prefix="/installments",
    tags=["Payment Transactions"],
)


# =========================================================
# CREATE PAYMENT
# =========================================================

@router.post(
    "/{installment_id}/payments",
    response_model=PaymentTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_payment(
    installment_id: int,
    payment_data:
        PaymentTransactionCreate,

    db: Session =
        Depends(get_db),

    current_user: User =
        Depends(get_current_user),
):

    result = create_payment_transaction(

        db=db,

        company_id=
            current_user.company_id,

        installment_id=
            installment_id,

        payment_data=
            payment_data,

        created_by=
            current_user.id,
    )


    # =====================================================
    # ERRORS
    # =====================================================

    if isinstance(result, dict):

        error = result.get("error")


        if error == "installment_not_found":

            raise HTTPException(
                status_code=
                    status.HTTP_404_NOT_FOUND,

                detail=
                    "Installment not found.",
            )


        if error == "invalid_payment_amount":

            raise HTTPException(
                status_code=
                    status.HTTP_400_BAD_REQUEST,

                detail=
                    "Payment amount must be greater than zero.",
            )


        if error == "installment_already_paid":

            raise HTTPException(
                status_code=
                    status.HTTP_409_CONFLICT,

                detail=
                    "This installment is already fully paid.",
            )


        if error == "payment_exceeds_balance":

            raise HTTPException(
                status_code=
                    status.HTTP_400_BAD_REQUEST,

                detail=(
                    f"Payment exceeds the outstanding "
                    f"balance of ₹"
                    f"{result['outstanding_amount']}."
                ),
            )


    return result


# =========================================================
# GET PAYMENTS FOR INSTALLMENT
# =========================================================

@router.get(
    "/{installment_id}/payments",
    response_model=List[PaymentTransactionResponse],
)
def get_payments(
    installment_id: int,

    db: Session =
        Depends(get_db),

    current_user: User =
        Depends(get_current_user),
):

    result = get_payments_for_installment(

        db=db,

        company_id=
            current_user.company_id,

        installment_id=
            installment_id,
    )


    if isinstance(result, dict):

        if (
            result.get("error")
            == "installment_not_found"
        ):

            raise HTTPException(
                status_code=
                    status.HTTP_404_NOT_FOUND,

                detail=
                    "Installment not found.",
            )


    return result   




# =========================================================
# UPDATE PAYMENT
# =========================================================

@router.put(
    "/payments/{payment_id}",
    response_model=PaymentTransactionResponse,
)
def update_payment_transaction(
    payment_id: int,
    payment_data: PaymentTransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    result = update_payment(
        db=db,
        company_id=current_user.company_id,
        payment_id=payment_id,
        payment_data=payment_data,
    )


    if isinstance(result, dict):

        error = result.get("error")


        if error == "payment_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found.",
            )


        if error == "invalid_amount":

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment amount must be greater than zero.",
            )


        if error == "amount_exceeds_installment":

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Payment amount exceeds the "
                    "remaining installment amount."
                ),
            )


    return result




# =========================================================
# DELETE PAYMENT
# =========================================================

@router.delete(
    "/payments/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_payment_transaction(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    result = delete_payment(
        db=db,
        company_id=current_user.company_id,
        payment_id=payment_id,
    )


    if isinstance(result, dict):

        if result.get("error") == "payment_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found.",
            )


    return None




# =========================================================
# GET CUSTOMER + CHIT PAYMENT HISTORY
# =========================================================

@router.get(
    "/customers/{customer_id}/chits/{chit_id}/members/{member_id}/payments",
    response_model=PaymentHistoryResponse,
)
def get_customer_chit_payments(
    customer_id: int,
    chit_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    result = get_customer_chit_payment_history(
        db=db,
        company_id=current_user.company_id,
        customer_id=customer_id,
        chit_id=chit_id,
        member_id=member_id,
    )


    if isinstance(result, dict):

        error = result.get("error")


        if error == "customer_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found.",
            )


        if error == "chit_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chit not found.",
            )


        if error == "membership_not_found":

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer is not a member of this chit.",
            )


    return result