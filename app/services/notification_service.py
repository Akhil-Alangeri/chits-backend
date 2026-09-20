from datetime import date
from sqlalchemy.orm import Session

from app.models.admin.company import Company
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.chit_group import ChitGroup
from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_installment import ChitInstallment
from app.models.admin.notification_log import NotificationLog
from app.core.email import send_email


# ============================================================
# DATE HELPERS
# ============================================================

def get_current_month() -> str:
    return date.today().strftime("%Y-%m")


def get_current_date() -> date:
    return date.today()


def get_next_month_first_date(current_date: date) -> date:
    if current_date.month == 12:
        return date(current_date.year + 1, 1, 1)

    return date(
        current_date.year,
        current_date.month + 1,
        1,
    )


# ============================================================
# ACTIVE MEMBERS FOR COMPANY
# ============================================================

def get_active_members_for_company(
    db: Session,
    company_id: int,
):
    """
    Returns one row for every active chit membership.

    Example:

    Akhil -> Gold Chit
    Akhil -> Trip Chit

    These will be two separate rows.
    """

    return (
        db.query(
            ChitMember,
            CustomerProfile,
            ChitGroup,
        )
        .join(
            CustomerProfile,
            CustomerProfile.id == ChitMember.customer_profile_id,
        )
        .join(
            ChitGroup,
            ChitGroup.id == ChitMember.chit_id,
        )
        .filter(
            ChitMember.status.in_(["confirmed", "active"]),

            # Multi-tenant protection
            ChitGroup.company_id == company_id,
            CustomerProfile.company_id == company_id,

            # Only active chits
            ChitGroup.status == "active",

            # Only active customers
            CustomerProfile.status == "active",
        )
        .all()
    )


# ============================================================
# CURRENT MONTH INSTALLMENT
# ============================================================

def get_month_installment(
    db: Session,
    chit_member_id: int,
):
    """
    Get the installment belonging to this chit member
    for the current month.
    """

    today = get_current_date()

    month_start = date(
        today.year,
        today.month,
        1,
    )

    next_month_start = get_next_month_first_date(today)

    return (
        db.query(ChitInstallment)
        .filter(
            ChitInstallment.chit_member_id == chit_member_id,

            ChitInstallment.due_date >= month_start,

            ChitInstallment.due_date < next_month_start,
        )
        .order_by(
            ChitInstallment.due_date.asc()
        )
        .first()
    )


# ============================================================
# FIND EXISTING NOTIFICATION LOG
# ============================================================

def get_notification_log(
    db: Session,
    chit_member_id: int,
    notification_type: str,
    notification_month: str,
):
    return (
        db.query(NotificationLog)
        .filter(
            NotificationLog.chit_member_id == chit_member_id,
            NotificationLog.notification_type == notification_type,
            NotificationLog.notification_month == notification_month,
        )
        .first()
    )


# ============================================================
# SEND NOTIFICATION FOR ONE CHIT MEMBERSHIP
# ============================================================

def send_notification_to_member(
    db: Session,
    company: Company,
    chit_member: ChitMember,
    customer: CustomerProfile,
    chit: ChitGroup,
    force: bool = False,
):
    """
    ONE chit membership = ONE notification.

    So if Akhil has:

    Gold Chit  -> ₹7,000
    Trip Chit  -> ₹2,500

    this function is called twice and sends two emails.
    """

    notification_type = "monthly_chit_reminder"
    notification_month = get_current_month()

    # --------------------------------------------------------
    # No email
    # --------------------------------------------------------

    if not customer.email:
        return "skipped"

    # --------------------------------------------------------
    # Get this month's installment
    # --------------------------------------------------------

    installment = get_month_installment(
        db=db,
        chit_member_id=chit_member.id,
    )

    if not installment:
        return "skipped"

    # --------------------------------------------------------
    # Check duplicate notification
    # --------------------------------------------------------

    existing_log = get_notification_log(
        db=db,
        chit_member_id=chit_member.id,
        notification_type=notification_type,
        notification_month=notification_month,
    )

    if (
        existing_log
        and existing_log.status == "sent"
        and not force
    ):
        return "already_sent"

    # --------------------------------------------------------
    # Customer name
    # --------------------------------------------------------

    customer_name = (
        customer.display_name
        or customer.legal_name
        or "Customer"
    )

    # --------------------------------------------------------
    # EMI
    # --------------------------------------------------------

    # Chit monthly EMI is the configured EMI amount.
    emi_amount = chit.monthly_emi

    # Installment amount can be used as actual due amount.
    due_amount = installment.due_amount

    # --------------------------------------------------------
    # EMAIL SUBJECT
    # --------------------------------------------------------

    subject = (
        f"Your {chit.name} EMI of "
        f"₹{emi_amount:,.0f} is due"
    )

    # --------------------------------------------------------
    # EMAIL BODY
    # --------------------------------------------------------

    body = f"""
Hi {customer_name},

Your {chit.name} monthly EMI of ₹{emi_amount:,.0f} is due.

Chit Name: {chit.name}
Monthly EMI: ₹{emi_amount:,.0f}
Due Amount: ₹{due_amount:,.0f}
Due Date: {installment.due_date.strftime("%d %b %Y")}

Please make your payment on time.

Regards,
{company.company_name}
""".strip()

    # --------------------------------------------------------
    # SEND EMAIL
    # --------------------------------------------------------

    try:

        send_email(
            to_email=customer.email,
            subject=subject,
            body=body,
            reply_to=company.email,
        )

        # ----------------------------------------------------
        # Existing log -> update
        # ----------------------------------------------------

        if existing_log:

            existing_log.status = "sent"
            existing_log.sent_at = get_current_date()
            existing_log.error_message = None

        # ----------------------------------------------------
        # New log
        # ----------------------------------------------------

        else:

            new_log = NotificationLog(
                company_id=company.id,
                chit_member_id=chit_member.id,
                notification_type=notification_type,
                notification_month=notification_month,
                status="sent",
                sent_at=get_current_date(),
                error_message=None,
            )

            db.add(new_log)

        db.commit()

        return "sent"

    except Exception as exc:

        db.rollback()

        existing_log = get_notification_log(
            db=db,
            chit_member_id=chit_member.id,
            notification_type=notification_type,
            notification_month=notification_month,
        )

        if existing_log:

            existing_log.status = "failed"
            existing_log.error_message = str(exc)[:500]

        else:

            failed_log = NotificationLog(
                company_id=company.id,
                chit_member_id=chit_member.id,
                notification_type=notification_type,
                notification_month=notification_month,
                status="failed",
                sent_at=None,
                error_message=str(exc)[:500],
            )

            db.add(failed_log)

        db.commit()

        return "failed"


# ============================================================
# SEND COMPANY MONTHLY NOTIFICATIONS
# ============================================================

def send_company_monthly_notifications(
    db: Session,
    company_id: int,
    force: bool = False,
):
    """
    Sends monthly notifications only for the given company.
    """

    # --------------------------------------------------------
    # Get company
    # --------------------------------------------------------

    company = (
        db.query(Company)
        .filter(
            Company.id == company_id,
            Company.status == "active",
        )
        .first()
    )

    if not company:

        return {
            "company_id": company_id,
            "company_name": "",
            "total": 0,
            "sent": 0,
            "skipped": 0,
            "already_sent": 0,
            "failed": 0,
        }

    # --------------------------------------------------------
    # Get active memberships
    # --------------------------------------------------------

    members = get_active_members_for_company(
        db=db,
        company_id=company_id,
    )

    total = len(members)

    sent = 0
    skipped = 0
    already_sent = 0
    failed = 0

    # --------------------------------------------------------
    # ONE MEMBERSHIP = ONE EMAIL
    # --------------------------------------------------------

    for (
        chit_member,
        customer,
        chit,
    ) in members:

        result = send_notification_to_member(
            db=db,
            company=company,
            chit_member=chit_member,
            customer=customer,
            chit=chit,
            force=force,
        )

        if result == "sent":
            sent += 1

        elif result == "skipped":
            skipped += 1

        elif result == "already_sent":
            already_sent += 1

        elif result == "failed":
            failed += 1

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return {
        "company_id": company.id,
        "company_name": company.company_name,
        "total": total,
        "sent": sent,
        "skipped": skipped,
        "already_sent": already_sent,
        "failed": failed,
    }


# ============================================================
# SEND FOR ALL COMPANIES
# ============================================================

def send_all_companies_monthly_notifications(
    db: Session,
):
    """
    Automatic scheduler uses this function.

    Every active company is processed separately.
    """

    companies = (
        db.query(Company)
        .filter(
            Company.status == "active"
        )
        .all()
    )

    company_results = []

    total = 0
    sent = 0
    skipped = 0
    already_sent = 0
    failed = 0

    for company in companies:

        result = send_company_monthly_notifications(
            db=db,
            company_id=company.id,
            force=False,
        )

        company_results.append(result)

        total += result["total"]
        sent += result["sent"]
        skipped += result["skipped"]
        already_sent += result["already_sent"]
        failed += result["failed"]

    return {
        "companies": len(companies),
        "total": total,
        "sent": sent,
        "skipped": skipped,
        "already_sent": already_sent,
        "failed": failed,
        "company_results": company_results,
    }