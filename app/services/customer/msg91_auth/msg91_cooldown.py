"""Persistent metadata only. MSG91 owns the OTP; no OTP or hash is stored."""
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import Base


class Msg91LoginState(Base):
    __tablename__ = "customer_msg91_login_state"
    mobile = Column(String(10), primary_key=True)
    sent_at = Column(DateTime, nullable=True)
    next_send_at = Column(DateTime, nullable=True)
    active = Column(Boolean, nullable=False, default=False)
    attempts = Column(Integer, nullable=False, default=0)


def locked_state(db: Session, mobile: str) -> Msg91LoginState:
    state = db.query(Msg91LoginState).filter_by(mobile=mobile).first()
    if state is None:
        try:
            # SAVEPOINT handles two workers creating the same mobile concurrently.
            with db.begin_nested():
                db.add(Msg91LoginState(mobile=mobile))
                db.flush()
        except IntegrityError:
            pass
    # Refresh after acquiring the lock; another worker may have updated the row.
    return db.query(Msg91LoginState).filter_by(mobile=mobile).populate_existing().with_for_update().one()
