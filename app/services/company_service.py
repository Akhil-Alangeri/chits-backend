
from fastapi import UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import case, func
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_group import ChitGroup
from fastapi import HTTPException


def change_company_status(db, company_id, new_status, ip_address=None, user_agent=None):
    company = db.query(Company).filter(Company.id == company_id).with_for_update().first()
    if company is None:
        raise HTTPException(404, "Company not found.")
    if company.status not in {"active", "inactive"}:
        raise HTTPException(409, "Only approved active/inactive companies can be changed here. Use the company approval flow for pending registrations.")
    if company.status == new_status:
        return company
    old_status = company.status
    company.status = new_status
    create_audit_log(db, company_id=company.id, user_id=None, action="STATUS_CHANGE",
        module="Companies", entity_type="Company", entity_id=company.id,
        description=f"Changed company status from '{old_status}' to '{new_status}'",
        old_values={"status": old_status}, new_values={"status": new_status},
        ip_address=ip_address, user_agent=user_agent)
    db.commit()
    db.refresh(company)
    return company
from app.models.admin.company import Company
from app.models.admin.user import User
from app.schemas.company import CompanyCreate
from app.core.security import hash_password
from pathlib import Path
from uuid import uuid4
from app.services.audit_log_service import (
    create_audit_log,
    snapshot_model,
)


COMPANY_AUDIT_FIELDS = [
    "id",
    "company_name",
    "email",
    "mobile",
    "address",
    "logo_url",
    "status",
]

USER_AUDIT_FIELDS = [
    "id",
    "company_id",
    "login_id",
    "role",
    "status",
]


def create_company(
    db: Session,
    company_name: str,
    mobile: str,
    email: str,
    address: str,
    logo: UploadFile | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
):
    # ==========================================
    # CHECK MOBILE NUMBER EXISTS
    # ==========================================

    existing_mobile = (
        db.query(Company)
        .filter(Company.mobile == mobile)
        .first()
    )

    # if existing_mobile:
    #     return {"error": "mobile_exists"}

    # ==========================================
    # CHECK EMAIL EXISTS
    # ==========================================

    # existing_email = (
    #     db.query(Company)
    #     .filter(Company.email == email)
    #     .first()
    # )

    # if existing_email:
    #     return {"error": "email_exists"}

    # ==========================================
    # LOGO
    # ==========================================

    logo_url = None

    if logo:
        # Allowed image types
        allowed_types = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
        }

        if logo.content_type not in allowed_types:
            return {
                "error": "invalid_logo_type"
            }

        # Read file
        file_content = logo.file.read()

        # Maximum 2 MB
        max_size = 2 * 1024 * 1024

        if len(file_content) > max_size:
            return {
                "error": "logo_too_large"
            }

        # ==========================================
        # CREATE LOGO DIRECTORY
        # ==========================================

        upload_dir = Path(
            "uploads/company-logos"
        )

        upload_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        # ==========================================
        # UNIQUE FILE NAME
        # ==========================================

        extension = allowed_types[
            logo.content_type
        ]

        filename = (
            f"company_{uuid4().hex}"
            f"{extension}"
        )

        file_path = upload_dir / filename

        # ==========================================
        # SAVE FILE
        # ==========================================

        with open(file_path, "wb") as file:
            file.write(file_content)

        # ==========================================
        # URL STORED IN DATABASE
        # ==========================================

        logo_url = (
            f"/uploads/company-logos/{filename}"
        )

    # ==========================================
    # CREATE COMPANY
    # ==========================================

    company = Company(
        company_name=company_name,
        mobile=mobile,
        email=email,
        address=address,
        logo_url=logo_url,
    )

    db.add(company)

    db.flush()

    create_audit_log(
        db=db,
        company_id=company.id,
        user_id=None,
        action="CREATE",
        module="Companies",
        entity_type="Company",
        entity_id=company.id,
        description=(
            f"Registered company '{company.company_name}'"
        ),
        new_values=snapshot_model(
            company,
            COMPANY_AUDIT_FIELDS,
        ),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.commit()
    db.refresh(company)

    return company
# ==========================================
# GET ALL COMPANIES
# ==========================================

def add_company_overviews(db: Session, companies):
    """Load company activity in bulk without multiplying customers by chit groups."""
    if not companies:
        return companies
    company_ids = [company.id for company in companies]
    counts = {
        company_id: (total, active)
        for company_id, total, active in db.query(
            CustomerProfile.company_id,
            func.count(CustomerProfile.id),
            func.sum(case((CustomerProfile.status == "active", 1), else_=0)),
        ).filter(CustomerProfile.company_id.in_(company_ids))
        .group_by(CustomerProfile.company_id).all()
    }
    amounts = {}
    for company_id, amount in db.query(
        ChitGroup.company_id, ChitGroup.chit_value
    ).filter(ChitGroup.company_id.in_(company_ids)).order_by(ChitGroup.id).all():
        amounts.setdefault(company_id, []).append(amount)
    for company in companies:
        company.total_customers_count, company.active_customers_count = counts.get(company.id, (0, 0))
        company.chit_group_amounts = amounts.get(company.id, [])
    return companies


def get_all_companies(
    db: Session
):

    companies = (
        db.query(Company)
        .order_by(Company.id.desc())
        .all()
    )

    return add_company_overviews(db, companies)

def get_pending_companies(
    db: Session
):
    companies = (
        db.query(Company)
        .filter(Company.status=="pending")
        .order_by(Company.id.desc())
        .all()
    )
    

    return companies

#=============================
#   Get Single Company Details
def get_company_details(db: Session, company_id: int):
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is not None:
        add_company_overviews(db, [company])
    return company


#===========================
# Generating Login Ids to company
#===========================
def generate_company_login_id(
    db: Session,
    company: Company
) -> str:

    # =========================================
    # FIRST WORD OF COMPANY NAME
    # =========================================

    first_word = (
        company.company_name
        .strip()
        .split()[0]
    )

    prefix = first_word[:5].upper()


    # =========================================
    # FIND EXISTING USER LOGIN IDs
    # WITH SAME PREFIX
    # =========================================

    existing_users = (
        db.query(User)
        .filter(
            User.login_id.like(
                f"{prefix}-%"
            )
        )
        .all()
    )


    numbers = []

    for existing in existing_users:

        if not existing.login_id:
            continue

        try:

            number = int(
                existing.login_id.split("-")[-1]
            )

            numbers.append(number)

        except ValueError:

            continue


    # =========================================
    # GENERATE NEXT NUMBER
    # =========================================

    next_number = (
        max(numbers) + 1
        if numbers
        else 1
    )


    return f"{prefix}-{next_number:03d}"
    
# =============================
#Change Status As Pending to Active  
#===============================


def approve_company(
    db: Session,
    company_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
):
    company = (
        db.query(Company)
        .filter(
            Company.id == company_id
        )
        .first()
    )

    if not company:
        return None


    # =====================================
    # ONLY PENDING COMPANIES CAN BE APPROVED
    # =====================================

    if company.status != "pending":

        return {
            "error": "already_processed"
        }

    old_company_values = snapshot_model(
        company,
        COMPANY_AUDIT_FIELDS,
    )


    # =====================================
    # GENERATE COMPANY LOGIN ID
    # =====================================

    login_id = generate_company_login_id(
        db,
        company
    )


    # =====================================
    # GENERATE TEMPORARY PASSWORD
    #
    # First word of company name
    # +
    # Last 5 digits of mobile
    # =====================================

    company_part = (
        company.company_name
        .strip()
        .split()[0][:5]
    )

    mobile_part = company.mobile[-5:]

    plain_password = (
        company_part +
        mobile_part
    )


    # =====================================
    # SAVE LOGIN CREDENTIALS
    # =====================================

    user = User(
        company_id=company.id,
        login_id=login_id,
        password_hash=hash_password(plain_password),
        role="company_admin",
        status="active"
    )

    db.add(user)
    # =====================================
    # ACTIVATE COMPANY
    # =====================================

    company.status = "active"

    db.flush()

    create_audit_log(
        db=db,
        company_id=company.id,
        user_id=None,
        action="CREATE",
        module="Users",
        entity_type="User",
        entity_id=user.id,
        description=(
            f"Created company admin '{user.login_id}' "
            f"for company '{company.company_name}'"
        ),
        new_values=snapshot_model(
            user,
            USER_AUDIT_FIELDS,
        ),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    new_company_values = snapshot_model(
        company,
        COMPANY_AUDIT_FIELDS,
    )

    create_audit_log(
        db=db,
        company_id=company.id,
        user_id=None,
        action="STATUS_CHANGE",
        module="Companies",
        entity_type="Company",
        entity_id=company.id,
        description=(
            f"Changed company '{company.company_name}' status "
            f"from '{old_company_values['status']}' to "
            f"'{new_company_values['status']}'"
        ),
        old_values=old_company_values,
        new_values=new_company_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # =====================================
    # SAVE DATABASE
    # =====================================

    db.commit()
    db.refresh(company)

    # =====================================
    # TEMPORARY DEVELOPMENT RESPONSE
    # =====================================

    return {
        "company": company,
        "login_id": login_id,
        "password": plain_password
    }
