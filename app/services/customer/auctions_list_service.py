from datetime import date

from sqlalchemy.orm import Session

from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_months import ChitMonth
from app.models.admin.chitlift import ChitLift
from app.models.admin.customer_profile import CustomerProfile


# =========================================================
# GET CUSTOMER CHIT AUCTION WINNERS
# =========================================================

def get_customer_chit_auction_winners(
    db: Session,
    mobile: str,
    chit_member_id: int,
):

    # =====================================================
    # VERIFY THIS CHIT MEMBER BELONGS TO LOGGED-IN CUSTOMER
    # =====================================================

    membership = (
        db.query(
            ChitMember,
            CustomerProfile,
            ChitGroup,
        )
        .join(
            CustomerProfile,
            CustomerProfile.id
            == ChitMember.customer_profile_id,
        )
        .join(
            ChitGroup,
            ChitGroup.id
            == ChitMember.chit_id,
        )
        .filter(
            # current selected chit member
            ChitMember.id == chit_member_id,

            # Match the authenticated identity across company-specific profiles,
            # as the customer chit list and details endpoints do.
            CustomerProfile.mobile == mobile,
            ChitMember.status == "confirmed",

            # customer must be active
            CustomerProfile.status
            == "active",

            # SaaS company protection
            ChitGroup.company_id
            == CustomerProfile.company_id,
        )
        .first()
    )


    if not membership:
        return {
            "error": "chit_membership_not_found",
        }


    chit_member, customer_profile, chit = membership


    # =====================================================
    # GET COMPANY + CHIT
    # =====================================================

    company_id = int(
        customer_profile.company_id
    )

    chit_id = int(
        chit.id
    )


    # =====================================================
    # GET ONLY THIS CHIT'S AUCTION WINNERS
    # =====================================================

    rows = (
        db.query(
            ChitLift,
            ChitMonth.month_date,
        )
        .outerjoin(
            ChitMonth,
            ChitMonth.id
            == ChitLift.chit_month_id,
        )
        .filter(
            ChitLift.company_id
            == company_id,

            ChitLift.chit_id
            == chit_id,
        )
        .order_by(
            ChitMonth.month_date.asc(),
            ChitLift.cycle_number.asc(),
            ChitLift.id.asc(),
        )
        .all()
    )


    # =====================================================
    # BUILD RESPONSE
    # =====================================================

    auction_winners = []

    for lift, month_date in rows:

        if not month_date:
            continue

        month_date = month_date.strftime("%b-%Y")

        auction_winners.append(
            {
                "month_date": month_date,
                "customer_name": lift.customer_name,
            }
        )       

    return {
        "auction_winners": auction_winners
    }