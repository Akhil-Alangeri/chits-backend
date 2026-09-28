from sqlalchemy.orm import Session
from app.models.admin.customer_profile import CustomerProfile


def get_customer_profile(
    db:Session,
    customer_profile_id:int
):
    return (
        db.query(CustomerProfile)
        .filter(
            CustomerProfile.id==customer_profile_id,
            CustomerProfile.status == "active"  
        )
        .first()      
    )
    
