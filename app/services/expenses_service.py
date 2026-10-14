
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.admin.expenses import Expense
from app.models.admin.user import User
from app.schemas.expenses import ExpenseCreate, ExpenseUpdate
from app.services.audit_log_service import (
    create_audit_log,
    snapshot_model,
)


EXPENSE_AUDIT_FIELDS = [
    "id",
    "category",
    "amount",
    "description",
    "expense_date",
    "payment_method",
    "reference",
    "notes",
]


def _expense_snapshot(expense: Expense) -> dict:
    return snapshot_model(
        expense,
        EXPENSE_AUDIT_FIELDS,
    )


def create_expense(
    db: Session,
    payload: ExpenseCreate,
    current_user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Expense:
    expense = Expense(
        company_id=current_user.company_id,
        created_by=current_user.id,
        category=payload.category,
        amount=payload.amount,
        description=payload.description,
        expense_date=payload.expense_date,
        payment_method=payload.payment_method,
        reference=payload.reference,
        notes=payload.notes,
    )

    db.add(expense)
    db.flush()

    create_audit_log(
        db=db,
        company_id=current_user.company_id,
        user_id=current_user.id,
        action="CREATE",
        module="Expenses",
        entity_type="Expense",
        entity_id=expense.id,
        description=f"Created expense #{expense.id}",
        new_values=_expense_snapshot(expense),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(expense)

    return expense


def get_expenses(
    db: Session,
    current_user: User,
) -> list[Expense]:
    return (
        db.query(Expense)
        .filter(Expense.company_id == current_user.company_id)
        .order_by(
            Expense.expense_date.desc(),
            Expense.created_at.desc(),
        )
        .all()
    )


def get_expense(
    db: Session,
    expense_id: int,
    current_user: User,
) -> Expense:
    expense = (
        db.query(Expense)
        .filter(
            Expense.id == expense_id,
            Expense.company_id == current_user.company_id,
        )
        .first()
    )

    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found.",
        )

    return expense


def update_expense(
    db: Session,
    expense_id: int,
    payload: ExpenseUpdate,
    current_user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Expense:
    expense = get_expense(
        db,
        expense_id,
        current_user,
    )

    old_values = _expense_snapshot(expense)

    update_data = payload.model_dump(exclude_unset=True)
    update_data.pop("reason", None)

    for field, value in update_data.items():
        setattr(expense, field, value)

    db.flush()

    create_audit_log(
        db=db,
        company_id=current_user.company_id,
        user_id=current_user.id,
        action="UPDATE",
        module="Expenses",
        entity_type="Expense",
        entity_id=expense.id,
        description=f"Updated expense #{expense.id}",
        old_values=old_values,
        new_values=_expense_snapshot(expense),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(expense)

    return expense


def delete_expense(
    db: Session,
    expense_id: int,
    current_user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    expense = get_expense(
        db,
        expense_id,
        current_user,
    )

    old_values = _expense_snapshot(expense)
    entity_id = expense.id

    db.delete(expense)
    db.flush()

    create_audit_log(
        db=db,
        company_id=current_user.company_id,
        user_id=current_user.id,
        action="DELETE",
        module="Expenses",
        entity_type="Expense",
        entity_id=entity_id,
        description=f"Deleted expense #{entity_id}",
        old_values=old_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()

