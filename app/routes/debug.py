from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from sqlalchemy import func
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.payment_transaction import PaymentTransaction
from app.models.chit_installment import ChitInstallment
from app.models.chit_member import ChitMember
from app.models.chit_group import ChitGroup


router = APIRouter()

@router.get("/debug/payment-method-summary")
def payment_method_summary(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    rows = (
        db.query(
            PaymentTransaction.payment_method,
            func.count(PaymentTransaction.id).label("count"),
            func.coalesce(
                func.sum(PaymentTransaction.amount), 0
            ).label("total"),
        )
        .join(
            ChitInstallment,
            ChitInstallment.id == PaymentTransaction.installment_id,
        )
        .join(
            ChitMember,
            ChitMember.id == ChitInstallment.chit_member_id,
        )
        .join(
            ChitGroup,
            ChitGroup.id == ChitMember.chit_id,
        )
        .filter(
            ChitGroup.company_id == current_user.company_id,
        )
        .group_by(PaymentTransaction.payment_method)
        .all()
    )

    return [
        {
            "payment_method": row.payment_method,
            "count": row.count,
            "total": float(row.total or 0),
        }
        for row in rows
    ]