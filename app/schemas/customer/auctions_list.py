from datetime import date

from pydantic import BaseModel, Field


class CustomerAuctionWinner(BaseModel):
    month_date: str
    customer_name: str


class CustomerAuctionWinnersResponse(BaseModel):
    success: bool
    message: str
    auction_winners: list[CustomerAuctionWinner]