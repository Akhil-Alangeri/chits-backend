from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.core.dependencies import (
    get_current_customer,
)

from app.schemas.customer.auctions_list import (
    CustomerAuctionWinnersResponse,
)

from app.services.customer.auctions_list_service import (
    get_customer_chit_auction_winners,
)


router = APIRouter(
    prefix="/customer/my-chits",
    tags=["Customer Auctions"],
)


@router.get(
    "/{chit_member_id}/auction-winners",
    response_model=CustomerAuctionWinnersResponse,
)
def get_customer_auction_winners(
    chit_member_id: int,
    db: Session = Depends(get_db),
    current_customer=Depends(get_current_customer),
):

    customer_profile_id = current_customer[
        "customer_profile_id"
    ]

    result = get_customer_chit_auction_winners(
        db=db,
        customer_profile_id=customer_profile_id,
        chit_member_id=chit_member_id,
    )

    if (
        result.get("error")
        == "chit_membership_not_found"
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chit membership not found for this customer.",
        )

    return {
        "success": True,
        "message": "Auction winners fetched successfully.",
        "auction_winners": result.get(
            "auction_winners",
            [],
        ),
    }