
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.admin.expenses import Expense
from app.models.admin.user import User
from app.schemas.expenses import ExpenseCreate, ExpenseUpdate


def create_expense(
    db: Session,
    payload: ExpenseCreate,
    current_user: User,
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
) -> Expense:
    expense = get_expense(
        db,
        expense_id,
        current_user,
    )

    update_data = payload.model_dump(exclude_unset=True)
    update_data.pop("reason", None)

    for field, value in update_data.items():
        setattr(expense, field, value)

    db.commit()
    db.refresh(expense)

    return expense


def delete_expense(
    db: Session,
    expense_id: int,
    current_user: User,
) -> None:
    expense = get_expense(
        db,
        expense_id,
        current_user,
    )

    db.delete(expense)
    db.commit()

