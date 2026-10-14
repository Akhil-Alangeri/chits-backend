from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.models.admin.audit_log import AuditLog


def get_request_metadata(
    request: Request,
) -> tuple[str | None, str | None]:
    client = request.client

    return (
        client.host if client else None,
        request.headers.get("user-agent"),
    )


# =========================================================
# SNAPSHOT MODEL
# =========================================================

def snapshot_model(
    obj: Any,
    fields: list[str],
) -> dict[str, Any]:
    """
    Create a JSON-safe snapshot of selected model fields.
    """

    if obj is None:
        return {}

    data = {}

    for field in fields:
        data[field] = getattr(
            obj,
            field,
            None,
        )

    return jsonable_encoder(data)


# =========================================================
# CREATE AUDIT RECORD
# =========================================================

def create_audit_log(
    db: Session,
    *,
    company_id: int,
    user_id: int | None,
    action: str,
    module: str,
    description: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:

    audit = AuditLog(
        company_id=company_id,
        user_id=user_id,
        action=action,
        module=module,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        old_values=(
            jsonable_encoder(old_values)
            if old_values is not None
            else None
        ),
        new_values=(
            jsonable_encoder(new_values)
            if new_values is not None
            else None
        ),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.add(audit)

    # DO NOT COMMIT HERE.
    # Business operation + audit should commit together.
    db.flush()

    return audit

# =========================================================
# GET AUDIT HISTORY
# =========================================================

def get_audit_history(
    db: Session,
    *,
    company_id: int,
    page: int = 1,
    page_size: int = 25,
    action: str | None = None,
    module: str | None = None,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> tuple[list[AuditLog], int]:

    query = (
        db.query(AuditLog)
        .filter(
            AuditLog.company_id == company_id
        )
    )

    # =====================================================
    # FILTERS
    # =====================================================

    from app.services.entitlement_service import get_company_effective_features
    features = get_company_effective_features(db, company_id)
    if not features.get("loans", False):
        query = query.filter(AuditLog.module.notin_(["Loans", "Loan Transactions"]))
    if not features.get("expenses", False):
        query = query.filter(AuditLog.module != "Expenses")

    if action:
        query = query.filter(
            AuditLog.action == action
        )

    if module:
        query = query.filter(
            AuditLog.module == module
        )

    if user_id:
        query = query.filter(
            AuditLog.user_id == user_id
        )

    if entity_type:
        query = query.filter(
            AuditLog.entity_type == entity_type
        )

    if entity_id:
        query = query.filter(
            AuditLog.entity_id == entity_id
        )

    # =====================================================
    # TOTAL
    # =====================================================

    total = query.count()

    # =====================================================
    # PAGINATION
    # =====================================================

    offset = (page - 1) * page_size

    items = (
        query
        .order_by(
            AuditLog.created_at.desc(),
            AuditLog.id.desc(),
        )
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # Fetch only safe actor fields once for this page, scoped to the same tenant.
    # Soft-deleted/inactive users remain identifiable in historical records.
    from app.models.admin.user import User
    actor_ids = {item.user_id for item in items if item.user_id is not None}
    actors = {
        user.id: user for user in db.query(User.id, User.full_name, User.login_id)
        .filter(User.company_id == company_id, User.id.in_(actor_ids)).all()
    } if actor_ids else {}
    for item in items:
        actor = actors.get(item.user_id)
        item.user_name = ((actor.full_name or "").strip() or actor.login_id) if actor else None
        item.user_login_id = actor.login_id if actor else None
    return items, total
