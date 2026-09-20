from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_company_id

from app.schemas.notification import (
    MonthlyNotificationResponse,
    AllCompaniesNotificationResponse,
)

from app.services.notification_service import (
    send_company_monthly_notifications,
    send_all_companies_monthly_notifications,
)


router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


# =========================================================
# SEND MONTHLY NOTIFICATION FOR CURRENT COMPANY
# =========================================================

@router.post(
    "/monthly-chit-reminder",
    response_model=MonthlyNotificationResponse,
)
def send_monthly_chit_reminder(
    db: Session = Depends(get_db),
    company_id :int=Depends(get_current_company_id)
):
    """
    Send monthly chit installment reminders
    for the current company.

    NOTE:
    Replace company_id=1 with the company ID
    from the authenticated/current user.
    """

    return send_company_monthly_notifications(
        db=db,
        company_id=company_id,
        force=True,
    )


# =========================================================
# SEND MONTHLY NOTIFICATIONS FOR ALL COMPANIES
# =========================================================

@router.post(
    "/monthly-chit-reminder/all",
    response_model=AllCompaniesNotificationResponse,
)
def send_all_monthly_chit_reminders(
    db: Session = Depends(get_db),
):
    """
    Send monthly chit installment reminders
    for every active company.

    This endpoint is mainly for scheduler/system usage.
    """

    return send_all_companies_monthly_notifications(
        db=db,
    )