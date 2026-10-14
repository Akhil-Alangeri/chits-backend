
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.admin.user import User
from app.schemas.expenses import ExpenseCreate, ExpenseResponse, ExpenseUpdate
from app.services.expenses_service import (
    create_expense,
    delete_expense,
    get_expense,
    get_expenses,
    update_expense,
)
from app.services.audit_log_service import get_request_metadata

from app.services.entitlement_service import require_company_feature

router = APIRouter(
    dependencies=[Depends(require_company_feature("expenses"))],
    prefix="/expenses",
    tags=["Expenses"],
)


@router.post(
    "/",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create(
    payload: ExpenseCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip_address, user_agent = get_request_metadata(request)

    return create_expense(
        db=db,
        payload=payload,
        current_user=current_user,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@router.get(
    "/",
    response_model=list[ExpenseResponse],
)
def get_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_expenses(
        db=db,
        current_user=current_user,
    )


@router.get(
    "/{expense_id}",
    response_model=ExpenseResponse,
)
def get_by_id(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_expense(
        db=db,
        expense_id=expense_id,
        current_user=current_user,
    )


@router.put(
    "/{expense_id}",
    response_model=ExpenseResponse,
)
def update(
    expense_id: int,
    payload: ExpenseUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip_address, user_agent = get_request_metadata(request)

    return update_expense(
        db=db,
        expense_id=expense_id,
        payload=payload,
        current_user=current_user,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    
    
    
    
@router.delete(
    "/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete(
    expense_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip_address, user_agent = get_request_metadata(request)

    return delete_expense(
        db=db,
        expense_id=expense_id,
        current_user=current_user,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    
    
    
    
    

