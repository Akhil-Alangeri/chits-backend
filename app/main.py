import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routes.company_logos import router as company_logos_router
from app.services.logo_storage import UPLOAD_ROOT
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

# Load SQLAlchemy models
from app.models import Company, User

# ==================== Admin / Company Routers ====================

from app.routes.company import router as company_router
from app.routes.auth import router as auth_router
from app.routes.company_users import router as company_users_router
from app.routes.chit_group import router as chit_group_router
from app.routes.customer_profile import router as admin_customer_profile_router
from app.routes.chit_member import router as chit_member_router
from app.routes.chit_installment import router as chit_installment_router
from app.routes.payment_transaction import router as payment_transaction_router
from app.routes.payment_summary import router as payment_summary_router
from app.routes.notification import router as notification_router
from app.routes.dashboard_router import router as dashboard_router
from app.routes.chit_lift_router import router as chit_lift_router
from app.routes.loan import router as loan_router
from app.routes.expenses import router as expenses_router
from app.routes.collection_report import router as collections_report
from app.routes.due_reports import router as due_reports
from app.routes.loan_reports import router as loan_reports
from app.routes.expenses_reports_router import router as expenses_reports_router
from app.routes.chit_reports import router as chit_reports_router
from app.routes.ledger_reports import router as ledger_reports_router
from app.routes.company_profile import router as company_profile_router
from app.routes.admin_ticket_router import router as admin_ticket_router
from app.routes.audit_log_router import router as audit_log_router

# ==================== Subscription ====================

from app.routes.subscription import (
    router as subscription_router,
    company_router as entitlement_router,
)

# ==================== Customer Routers ====================

from app.routes.customer.customer_chit_router import router as customer_chit_router
from app.routes.customer.customer_dashboard_router import router as customer_dashboard_router
from app.routes.customer.customer_profile_route import router as customer_profile_router
from app.routes.customer.ticket_router import router as ticket_router
from app.routes.customer.customer_receipt_router import router as customer_receipt_router
from app.routes.customer.upcoming_chits_router import router as upcoming_chits_router
from app.routes.customer.auctions_list_router import router as auctions_list_router
from app.routes.customer.msg91_auth_router import router as customer_msg91_auth_router


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="NexNidhi API",
    version="1.0.0",
)


# =========================================================
# COMPANY LOGOS AND LEGACY LOCAL UPLOADS
# =========================================================

(UPLOAD_ROOT / "company-logos").mkdir(parents=True, exist_ok=True)

# Register before the legacy static mount so bucket objects are served too.
app.include_router(company_logos_router)

app.mount(
    "/uploads",
    StaticFiles(directory=str(UPLOAD_ROOT)),
    name="uploads",
)


# =========================================================
# CORS
# =========================================================

default_origins = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    "http://localhost:4201",
    "http://127.0.0.1:4201",
    "http://localhost:4202",
    "http://127.0.0.1:4202",

    "https://nexnidhi.in",
    "https://www.nexnidhi.in",
    "https://admin.nexnidhi.in",
    "https://customer.nexnidhi.in",
    "https://super-admin.nexnidhi.in",
]

cors_env = os.getenv("CORS_ORIGINS", "")

if cors_env:
    allowed_origins = [
        origin.strip()
        for origin in cors_env.split(",")
        if origin.strip()
    ]
else:
    allowed_origins = default_origins

if "*" in allowed_origins:
    raise RuntimeError(
        "CORS_ORIGINS must list explicit origins when credentials are enabled"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# ROUTERS
# =========================================================

from app.routes.super_admin_auth import router as super_admin_auth_router
app.include_router(super_admin_auth_router)

app.include_router(subscription_router)
app.include_router(entitlement_router)

app.include_router(company_router)
app.include_router(auth_router)
app.include_router(company_users_router)
app.include_router(chit_group_router)
app.include_router(admin_customer_profile_router)
app.include_router(chit_member_router)
app.include_router(chit_installment_router)
app.include_router(payment_transaction_router)
app.include_router(payment_summary_router)
app.include_router(notification_router)
app.include_router(dashboard_router)
app.include_router(chit_lift_router)
app.include_router(loan_router)
app.include_router(expenses_router)

app.include_router(collections_report)
app.include_router(due_reports)
app.include_router(loan_reports)
app.include_router(expenses_reports_router)
app.include_router(chit_reports_router)
app.include_router(ledger_reports_router)

app.include_router(company_profile_router)

app.include_router(customer_msg91_auth_router)
app.include_router(customer_chit_router)
app.include_router(customer_dashboard_router)
app.include_router(customer_profile_router)

app.include_router(ticket_router)
app.include_router(admin_ticket_router)

app.include_router(customer_receipt_router)
app.include_router(audit_log_router)
app.include_router(upcoming_chits_router)
app.include_router(auctions_list_router)


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def home():
    return {
        "message": "Welcome to NexNidhi API"
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))

    return {
        "status": "OK",
        "database": "Connected",
    }
from app.routes.company_recovery import router as company_recovery_router
app.include_router(company_recovery_router)
