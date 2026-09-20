from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.models.admin.user import User

from app.schemas.payment_summary import (
    ChitPaymentSummaryResponse,
    MemberPaymentSummaryResponse,
)

from app.services.payment_transaction import (
    get_chit_payment_summary,
    get_member_payment_summary,
)


router = APIRouter(
    prefix="/chits",
    tags=["Payment Summary"],
)


# =========================================================
# CHIT PAYMENT SUMMARY
# =========================================================

@router.get(
    "/{chit_id}/payment-summary",
    response_model=ChitPaymentSummaryResponse,
)
def get_chit_summary(
    chit_id: int,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    ),
):

    result = get_chit_payment_summary(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
    )


    if isinstance(result, dict):

        if result.get("error") == "chit_not_found":

            raise HTTPException(
                status_code=404,
                detail="Chit not found.",
            )


    return result


# =========================================================
# MEMBER PAYMENT SUMMARY
# =========================================================

@router.get(
    "/{chit_id}/members/{member_id}/payment-summary",
    response_model=MemberPaymentSummaryResponse,
)
def get_member_summary(
    chit_id: int,

    member_id: int,

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    ),
):

    result = get_member_payment_summary(
        db=db,
        company_id=current_user.company_id,
        chit_id=chit_id,
        member_id=member_id,
    )


    if isinstance(result, dict):

        if result.get("error") == "member_not_found":

            raise HTTPException(
                status_code=404,
                detail="Member not found.",
            )


    return result