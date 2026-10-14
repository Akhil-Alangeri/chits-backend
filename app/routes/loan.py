from fastapi import (APIRouter,Depends,HTTPException,Request,status,)

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.models.admin.user import User

from app.schemas.loan import (
    LoanCreate,
    LoanDetailResponse,
    LoanResponse,
    LoanSummary,
    LoanUpdate,
)

from app.schemas.loan_transaction import (
    LoanTransactionCreate,
    LoanTransactionResponse,
)

from app.services.loan_services import (
    cancel_loan,
    create_loan,
    create_loan_transaction,
    get_loan_detail,
    get_loan_summary,
    get_loan_transactions,
    get_loans,
    update_loan,
)
from app.services.audit_log_service import get_request_metadata


from app.services.entitlement_service import require_company_feature

router = APIRouter(
    dependencies=[Depends(require_company_feature("loans"))],
    prefix="/loans",
    tags=["Loans"],
)


# =========================================================
# CREATE LOAN
# =========================================================

@router.post(
    "",
    response_model=LoanResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_loan_route(
    data: LoanCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    ip_address, user_agent = get_request_metadata(request)

    return create_loan(
        db=db,
        company_id=current_user.company_id,
        created_by=current_user.id,
        loan_data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )


# =========================================================
# GET ALL LOANS
# =========================================================

@router.get(
    "",
    response_model=list[LoanResponse],
)
def get_loans_route(
    direction: str | None = None,
    status_value: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    return get_loans(
        db=db,
        company_id=current_user.company_id,
        direction=direction,
        status=status_value,
    )


# =========================================================
# GET LOAN SUMMARY
# IMPORTANT:
# Keep this BEFORE /{loan_id}
# =========================================================

@router.get(
    "/{loan_id}/summary",
    response_model=LoanSummary,
)
def get_loan_summary_route(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    result = get_loan_summary(
        db=db,
        company_id=current_user.company_id,
        loan_id=loan_id,
    )

    if isinstance(result, dict):
        if result.get("error") == "loan_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Loan not found.",
            )

    return result


# =========================================================
# GET TRANSACTIONS
# IMPORTANT:
# Keep this BEFORE /{loan_id}
# =========================================================

@router.get(
    "/{loan_id}/transactions",
    response_model=list[LoanTransactionResponse],
)
def get_loan_transactions_route(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    result = get_loan_transactions(
        db=db,
        company_id=current_user.company_id,
        loan_id=loan_id,
    )

    if isinstance(result, dict):
        if result.get("error") == "loan_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Loan not found.",
            )

    return result


# =========================================================
# CREATE LOAN TRANSACTION
# =========================================================

@router.post(
    "/{loan_id}/transactions",
    response_model=LoanTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_loan_transaction_route(
    loan_id: int,
    data: LoanTransactionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    ip_address, user_agent = get_request_metadata(request)

    result = create_loan_transaction(
        db=db,
        company_id=current_user.company_id,
        loan_id=loan_id,
        created_by=current_user.id,
        transaction_data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if isinstance(result, dict):
        error = result.get("error")

        if error == "loan_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Loan not found.",
            )

        if error == "loan_cancelled":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"],
            )

        if error == "disbursement_already_exists":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=result["message"],
            )

        if error in (
            "invalid_transaction_amount",
            "invalid_payment_amount",
            "payment_amount_mismatch",
            "invalid_disbursement",
            "invalid_interest_payment",
            "principal_repayment_exceeds_balance",
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"],
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    return result


# =========================================================
# GET LOAN DETAIL
# =========================================================

@router.get(
    "/{loan_id}",
    response_model=LoanDetailResponse,
)
def get_loan_route(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    result = get_loan_detail(
        db=db,
        company_id=current_user.company_id,
        loan_id=loan_id,
    )

    if isinstance(result, dict):
        if result.get("error") == "loan_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Loan not found.",
            )

    return result


# =========================================================
# UPDATE LOAN
# =========================================================

@router.put(
    "/{loan_id}",
    response_model=LoanResponse,
)
def update_loan_route(
    loan_id: int,
    data: LoanUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    ip_address, user_agent = get_request_metadata(request)

    result = update_loan(
        db=db,
        company_id=current_user.company_id,
        loan_id=loan_id,
        loan_data=data,
        updated_by=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if isinstance(result, dict):
        error = result.get("error")

        if error == "loan_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Loan not found.",
            )

        if error == "invalid_due_date":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"],
            )

        if error == "principal_below_paid_amount":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"],
            )

    return result


# =========================================================
# CANCEL LOAN
# =========================================================

@router.patch(
    "/{loan_id}/cancel",
    response_model=LoanResponse,
)
def cancel_loan_route(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    ip_address, user_agent = get_request_metadata(request)

    result = cancel_loan(
        db=db,
        company_id=current_user.company_id,
        loan_id=loan_id,
        cancelled_by=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if isinstance(result, dict):
        error = result.get("error")

        if error == "loan_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Loan not found.",
            )

        if error == "loan_closed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"],
            )

    return result
