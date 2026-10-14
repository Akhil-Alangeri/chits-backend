from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.admin.user import User

from app.services.dashboard_service import get_dashboard


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


# =========================================================
# DASHBOARD
# =========================================================

@router.get("")
def dashboard(
    year: int | None = Query(
        default=None,
        description="Year to use for historical monthly analytics.",
    ),
    expense_month: int | None = Query(
        default=None,
        ge=1,
        le=12,
        description="Month to use for the selected year's expense total (1-12).",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get dashboard data for the authenticated user's company.

    Query parameters:
        year:
            Optional analysis year. When omitted, the service uses the
            current year / its configured default behavior.

        expense_month:
            Optional month (1-12) used for the selected year's expense
            analysis.
    """

    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a company.",
        )

    return get_dashboard(
        db=db,
        company_id=current_user.company_id,
        year=year,
        expense_month=expense_month,
    )
