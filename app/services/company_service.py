
from fastapi import UploadFile
from sqlalchemy.orm import Session
from app.models.admin.company import Company
from app.models.admin.user import User
from app.schemas.company import CompanyCreate
from app.core.security import hash_password
from pathlib import Path
from uuid import uuid4


def create_company(
    db: Session,
    company_name: str,
    mobile: str,
    email: str,
    address: str,
    logo: UploadFile | None = None,
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
    db.commit()
    db.refresh(company)

    return company
# ==========================================
# GET ALL COMPANIES
# ==========================================

def get_all_companies(
    db: Session
):

    companies = (
        db.query(Company)
        .order_by(Company.id.desc())
        .all()
    )

    return companies

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
def get_company_details(
    db: Session,
    company_id: int
):
    return (
        db.query(Company)
        .filter(
            Company.id == company_id
        )
        .first()
    )
    
    
    
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
    company_id: int
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
    
    
    