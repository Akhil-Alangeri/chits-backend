from datetime import datetime

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    company_id = Column(
        BigInteger,
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    category = Column(
        String(50),
        nullable=False,
        index=True,
    )

    amount = Column(
        BigInteger,
        nullable=False,
    )

    description = Column(
        Text,
        nullable=True,
    )

    expense_date = Column(
        Date,
        nullable=False,
        index=True,
    )

    payment_method = Column(
        String(10),
        nullable=False,
        index=True,
    )

    reference = Column(
        String(150),
        nullable=True,
    )

    notes = Column(
        Text,
        nullable=True,
    )

    created_by = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    company = relationship(
        "Company",
        foreign_keys=[company_id],
    )

    created_user = relationship(
        "User",
        foreign_keys=[created_by],
    )
    
    
    