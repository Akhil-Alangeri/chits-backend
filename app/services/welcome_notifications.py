"""Transaction-local eligibility hooks and a durable, lease-based delivery worker."""
import logging
from datetime import timedelta
from uuid import uuid4

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import and_, or_, func
from sqlalchemy.exc import IntegrityError

from app.models.admin.chit_member import ChitMember
from app.models.admin.chit_group import ChitGroup
from app.models.admin.customer_profile import CustomerProfile
from app.models.admin.company import Company
from app.models.admin.welcome_outbox import WelcomeOutbox, utc_now
from app.services.welcome_email import EmailConfigurationError, send_welcome_email
from app.services.welcome_template import render_welcome

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 8
LEASE = timedelta(minutes=10)


def normalized(status):
    return (status or "").strip().lower()


def membership_context(db, membership_id, company_id):
    # Join through the exact company profile. Never look up by mobile/global user.
    return (
        db.query(ChitMember, ChitGroup, CustomerProfile, Company)
        .join(ChitGroup, ChitGroup.id == ChitMember.chit_id)
        .join(CustomerProfile, CustomerProfile.id == ChitMember.customer_profile_id)
        .join(Company, Company.id == ChitGroup.company_id)
        .filter(ChitMember.id == membership_id, Company.id == company_id,
                CustomerProfile.company_id == ChitGroup.company_id)
        .first()
    )


def eligible(context):
    return bool(context and normalized(context[0].status) in {"active", "confirmed"}
                and normalized(context[1].status) == "active")


def enqueue_membership_welcome(db, membership_id, company_id):
    """No commit or provider calls. The caller owns the business transaction."""
    db.flush()
    if not eligible(membership_context(db, membership_id, company_id)):
        return False
    key = (WelcomeOutbox.membership_id == membership_id,
           WelcomeOutbox.notification_type == "membership_welcome")
    existing = db.query(WelcomeOutbox).filter(*key).first()
    if existing:
        # A fresh eligibility event can resume a previously ineligible notification.
        if existing.status == "failed" and existing.last_error == "membership_ineligible":
            db.query(WelcomeOutbox).filter(*key, WelcomeOutbox.status == "failed",
                WelcomeOutbox.last_error == "membership_ineligible").update({
                    WelcomeOutbox.status: "pending", WelcomeOutbox.available_at: utc_now(),
                    WelcomeOutbox.attempts: 0, WelcomeOutbox.last_error: None,
                }, synchronize_session=False)
        return False
    try:
        with db.begin_nested():
            db.add(WelcomeOutbox(membership_id=membership_id, company_id=company_id))
            db.flush()
    except IntegrityError:
        # Unique constraint is authoritative under simultaneous eligibility events.
        # FOR UPDATE is a current read on MySQL, including under REPEATABLE READ.
        if not db.query(WelcomeOutbox).filter(*key).with_for_update().first():
            raise
        return False
    return True


def enqueue_group_welcomes(db, chit_id, company_id):
    db.flush()
    members = (db.query(ChitMember.id).join(ChitGroup, ChitGroup.id == ChitMember.chit_id)
               .filter(ChitGroup.id == chit_id, ChitGroup.company_id == company_id,
                       func.lower(func.trim(ChitMember.status)).in_(["active", "confirmed"]))
               .all())
    for (membership_id,) in members:
        enqueue_membership_welcome(db, membership_id, company_id)


def due_filter(now):
    return or_(
        and_(WelcomeOutbox.status.in_(["pending", "failed"]),
             WelcomeOutbox.available_at.isnot(None), WelcomeOutbox.available_at <= now),
        and_(WelcomeOutbox.status == "processing", WelcomeOutbox.claimed_at <= now - LEASE),
    )


def claim_one(session_factory):
    """Atomic compare-and-set; competing processes may select but cannot claim twice."""
    now = utc_now()
    with session_factory() as db:
        ids = [row[0] for row in db.query(WelcomeOutbox.id).filter(due_filter(now))
               .order_by(WelcomeOutbox.id).limit(100).all()]
        for outbox_id in ids:
            token = str(uuid4())
            changed = (db.query(WelcomeOutbox).filter(WelcomeOutbox.id == outbox_id, due_filter(now))
                       .update({WelcomeOutbox.status: "processing", WelcomeOutbox.claim_token: token,
                                WelcomeOutbox.claimed_at: now, WelcomeOutbox.updated_at: now,
                                WelcomeOutbox.attempts: WelcomeOutbox.attempts + 1},
                               synchronize_session=False))
            db.commit()
            if changed:
                return outbox_id, token
    return None


def finish(session_factory, outbox_id, token, *, error=None, terminal=False):
    now = utc_now()
    with session_factory() as db:
        ownership = (WelcomeOutbox.id == outbox_id, WelcomeOutbox.status == "processing",
                     WelcomeOutbox.claim_token == token)
        row = db.query(WelcomeOutbox).filter(*ownership).first()
        if not row:
            return False
        retry = error and not terminal and row.attempts < MAX_ATTEMPTS
        available_at = now + timedelta(seconds=min(3600, 60 * 2 ** min(row.attempts - 1, 6))) if retry else None
        # Fence at UPDATE time, not just SELECT time: ownership may change between them.
        changed = db.query(WelcomeOutbox).filter(*ownership).update({
            WelcomeOutbox.status: "failed" if error else "sent",
            WelcomeOutbox.last_error: error,
            WelcomeOutbox.sent_at: None if error else now,  # SMTP acceptance, not inbox delivery.
            WelcomeOutbox.available_at: available_at,
            WelcomeOutbox.claim_token: None, WelcomeOutbox.claimed_at: None,
            WelcomeOutbox.updated_at: now,
        }, synchronize_session=False)
        db.commit()
    if error and changed:
        # Never log provider exceptions: these can contain recipient addresses or secrets.
        logger.warning("Membership welcome attempt failed: outbox=%s reason=%s", outbox_id, error)
    return bool(changed)


def deliver_claim(session_factory, claim, send=send_welcome_email):
    outbox_id, token = claim
    error = None
    terminal = False
    payload = None
    with session_factory() as db:
        row = db.query(WelcomeOutbox).filter(WelcomeOutbox.id == outbox_id,
                WelcomeOutbox.status == "processing", WelcomeOutbox.claim_token == token).first()
        if not row:
            return False
        context = membership_context(db, row.membership_id, row.company_id)
        if row.attempts > MAX_ATTEMPTS:
            error, terminal = "attempt_limit", True
        elif not eligible(context):
            error, terminal = "membership_ineligible", True
        else:
            member, chit, customer, company = context
            try:
                recipient = validate_email(customer.email or "", check_deliverability=False).normalized
            except EmailNotValidError:
                error = "missing_or_invalid_email"
            else:
                subject, text, html = render_welcome(customer.display_name, company.company_name,
                                                   chit.name, normalized(member.status))
                payload = recipient, subject, text, html, row.id
    # All DB transactions/connections from payload loading are closed before network I/O.
    if payload:
        try:
            send(*payload)
        except EmailConfigurationError:
            error = "smtp_not_configured"
        except Exception:
            error = "provider_error"
    return finish(session_factory, outbox_id, token, error=error, terminal=terminal)


def process_welcome_batch(session_factory, limit=100, send=send_welcome_email):
    processed = 0
    for _ in range(limit):
        claim = claim_one(session_factory)
        if claim is None:
            break
        deliver_claim(session_factory, claim, send=send)
        processed += 1
    return processed
