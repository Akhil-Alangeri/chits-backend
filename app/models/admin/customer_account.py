# from sqlalchemy import (
#     BigInteger,
#     Column,
#     DateTime,
#     String,
#     UniqueConstraint,
# )
# from sqlalchemy.orm import relationship
# from sqlalchemy.sql import func

# from app.core.database import Base


# class CustomerAccount(Base):

#     __tablename__ = "customer_accounts"

#     __table_args__ = (
#         UniqueConstraint(
#             "mobile",
#             name="uq_customer_account_mobile",
#         ),
#     )

#     # =====================================================
#     # PRIMARY KEY
#     # =====================================================

#     id = Column(
#         BigInteger,
#         primary_key=True,
#         autoincrement=True,
#     )

#     # =====================================================
#     # GLOBAL LOGIN MOBILE
#     # =====================================================

#     mobile = Column(
#         String(20),
#         nullable=False,
#         unique=True,
#         index=True,
#     )

#     # =====================================================
#     # LOGIN PASSWORD
#     # =====================================================

#     password_hash = Column(
#         String(255),
#         nullable=True,
#     )

#     # =====================================================
#     # CUSTOMER DETAILS
#     # =====================================================

#     display_name = Column(
#         String(150),
#         nullable=False,
#     )

#     email = Column(
#         String(150),
#         nullable=True,
#     )

#     # =====================================================
#     # ACCOUNT STATUS
#     # =====================================================

#     # pending
#     # active
#     # blocked

#     status = Column(
#         String(20),
#         nullable=False,
#         default="pending",
#         index=True,
#     )

#     # =====================================================
#     # LOGIN INFORMATION
#     # =====================================================

#     last_login_at = Column(
#         DateTime,
#         nullable=True,
#     )

#     # =====================================================
#     # TIMESTAMPS
#     # =====================================================

#     created_at = Column(
#         DateTime,
#         server_default=func.now(),
#     )

#     updated_at = Column(
#         DateTime,
#         server_default=func.now(),
#         onupdate=func.now(),
#     )

#     # =====================================================
#     # RELATIONSHIP
#     # =====================================================

#     # customer_profiles = relationship(
#     #     "CustomerProfile",
#     #     back_populates="customer_account",
#     # )