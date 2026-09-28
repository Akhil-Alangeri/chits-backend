from sqlalchemy import BigInteger, Column, DateTime, String,Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Company(Base):

    __tablename__ = "companies"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    company_name = Column(
        String(150),
        nullable=False
    )
    
    logo_url = Column(
        String(500),
        nullable=True
    )

    email = Column(
        String(150),
        nullable=True
    )

    mobile = Column(
        String(20),
        nullable=True
    )

    address = Column(
        String(500),
        nullable=True
    )
    
    
    status = Column(
        Enum("pending","active", "inactive", "suspended","rejected"),
        default="pending",
        nullable=False
    )
    
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    users = relationship(
        "User",
        back_populates="company"
    )
    
    login_id = Column(
        String(150),
        nullable=True,
        unique=True
    )
    
    password_hash = Column(
        String(255),
        nullable=True
    )
    
    users = relationship(
        "User",
        back_populates="company"
    )
    
    chit_groups = relationship(
        "ChitGroup",
        back_populates="company",
        cascade="all, delete-orphan"
    )  
    
    customer_profiles = relationship(
        "CustomerProfile",
        back_populates="company",
        cascade="all, delete-orphan",
    )  
       
    chit_lifts = relationship(
        "ChitLift",
        back_populates="company",
    )
    
    chit_months=relationship(
        "ChitMonth",
        back_populates="company",
    )