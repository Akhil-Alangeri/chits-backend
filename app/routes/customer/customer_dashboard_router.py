from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_customer
from app.schemas.customer.customer_dashboard import CustomerDashboardResponse
from app.services.customer.customer_dashboard_service import get_customer_dashboard


router = APIRouter(
    prefix="/customer/dashboard",
    tags=["Customer Dashboard"],
)


@router.get("", response_model=CustomerDashboardResponse)
def get_my_dashboard(
    db: Session = Depends(get_db),
    current_customer=Depends(get_current_customer),
):
    dashboard = get_customer_dashboard(
        db=db,
        mobile=current_customer["mobile"],
    )

    return CustomerDashboardResponse(
        success=True,
        message="Customer dashboard fetched successfully",
        **dashboard,
    )
