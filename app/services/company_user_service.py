from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.admin.user import User
from app.core.security import hash_password
from app.services.audit_log_service import create_audit_log, snapshot_model
from app.services.entitlement_service import (
    ensure_company_feature,
    ensure_staff_capacity,
    lock_company,
)
from app.services.subscription_transactions import retry_subscription_transaction

AUDIT_FIELDS = ["id", "full_name", "login_id", "role", "status"]


def company_users(db: Session, admin: User):
    return db.query(User).filter(
        User.company_id == admin.company_id,
        User.role.in_(["company_admin", "company_user"]),
        User.status != "deleted",
    )


def get_company_user(db, admin, user_id, *, mutable=False):
    if mutable:
        # All staff mutations use company -> user lock order. Refresh after
        # waiting so concurrent deactivation/reactivation cannot use stale state.
        lock_company(db, admin.company_id)
    query = company_users(db, admin).filter(User.id == user_id)
    if mutable:
        query = query.populate_existing().with_for_update()
    user = query.first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    # Protect all admin accounts, including the original approval account.
    if mutable and (user.id == admin.id or user.role != "company_user"):
        raise HTTPException(status_code=403, detail="Company admin accounts are protected.")
    return user


def ensure_login_available(db, login_id, exclude_id=None):
    query = db.query(User).filter(User.login_id == login_id)
    if exclude_id is not None:
        query = query.filter(User.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=409, detail="Login ID already exists.")


def save_user(db, admin, user, action, old_values=None, *, password_changed=False):
    try:
        db.flush()
        create_audit_log(
            db=db, company_id=admin.company_id, user_id=admin.id,
            action=action, module="Users", entity_type="User", entity_id=user.id,
            description=f"{action} company user '{user.login_id}'",
            old_values=old_values,
            new_values=({"password_changed": True} if password_changed else snapshot_model(user, AUDIT_FIELDS)),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="User could not be saved; Login ID may already exist.")
    db.refresh(user)
    return user


@retry_subscription_transaction
def create_company_user(db, admin, data):
    lock_company(db, admin.company_id)
    ensure_company_feature(db, admin.company_id, "staff_permissions", current=True)
    ensure_login_available(db, data.login_id)
    ensure_staff_capacity(db, admin.company_id)
    user = User(company_id=admin.company_id, full_name=data.full_name,
                login_id=data.login_id, password_hash=hash_password(data.password),
                role="company_user", status="active")
    db.add(user)
    return save_user(db, admin, user, "CREATE")
