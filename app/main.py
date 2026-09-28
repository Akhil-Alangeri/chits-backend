from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.staticfiles import StaticFiles

from fastapi.middleware.cors import CORSMiddleware

# Load all SQLAlchemy models
from app.models import Company, User

from app.routes.company import router as company_router
from app.routes.auth import router as auth_router
from app.routes.chit_group import router as chit_group_router
from app.routes.customer_profile import router as admin_customer_profile_router
from app.routes.chit_member import router as chit_member_router
from app.routes.chit_installment import router as chit_installment_router
from app.routes.payment_transaction import (
    router as payment_transaction_router,
)
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
from app.routes.customer.customer_chit_router import router as customer_chit_router
from app.routes.customer.customer_dashboard_router import router as customer_dashboard_router
# ==================== Customer Routers ==============================

from app.routes.customer.customer_auth_router import router as customer_auth_router 
from app.routes.customer.customer_profile_route import router as customer_profile_router
from app.routes.customer.ticket_router import router as ticket_router
from app.routes.admin_ticket_router import router  as admin_ticket_router



from app.core.database import Base, get_db,engine


# ===============
# create Tables

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)

# =========================
# CORS
# =========================




app.add_middleware(
    CORSMiddleware,
   allow_origins=[
    "http://localhost:4200",
    "http://127.0.0.1:4200",

    "http://localhost:4201",
    "http://127.0.0.1:4201",
    
    "http://localhost:4202",
    "http://127.0.0.1:4202",
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(company_router)
app.include_router(auth_router)
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
app.include_router(customer_auth_router)
app.include_router(customer_chit_router)
app.include_router(customer_dashboard_router)
app.include_router(customer_profile_router)
app.include_router(ticket_router)
app.include_router(admin_ticket_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to Chits API"
    }


@app.get("/health")
def health(db: Session = Depends(get_db)):

    db.execute(text("SELECT 1"))

    return {
        "status": "OK",
        "database": "Connected"
    }
