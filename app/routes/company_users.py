from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import require_company_admin
from app.core.security import hash_password
from app.schemas.company_user import UserCreate, UserUpdate, UserResponse, UserStatus, PasswordChange
from app.services.company_user_service import (
    company_users, get_company_user, ensure_login_available, create_company_user,
    save_user, snapshot_model, AUDIT_FIELDS,
)

router = APIRouter(prefix="/company/users", tags=["Company Users"])


@router.get("", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db), admin=Depends(require_company_admin)):
    return company_users(db, admin).order_by("id").all()


@router.post("", response_model=UserResponse, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db), admin=Depends(require_company_admin)):
    return create_company_user(db, admin, data)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db), admin=Depends(require_company_admin)):
    return get_company_user(db, admin, user_id)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db), admin=Depends(require_company_admin)):
    user = get_company_user(db, admin, user_id, mutable=True)
    ensure_login_available(db, data.login_id, user.id)
    old = snapshot_model(user, AUDIT_FIELDS)
    user.full_name, user.login_id = data.full_name, data.login_id
    return save_user(db, admin, user, "UPDATE", old)


@router.patch("/{user_id}/status", response_model=UserResponse)
def change_status(user_id: int, data: UserStatus, db: Session = Depends(get_db), admin=Depends(require_company_admin)):
    user = get_company_user(db, admin, user_id, mutable=True)
    old = snapshot_model(user, AUDIT_FIELDS)
    user.status = data.status
    return save_user(db, admin, user, "STATUS_CHANGE", old)


@router.patch("/{user_id}/password", response_model=UserResponse)
def change_password(user_id: int, data: PasswordChange, db: Session = Depends(get_db), admin=Depends(require_company_admin)):
    user = get_company_user(db, admin, user_id, mutable=True)
    user.password_hash = hash_password(data.password)
    return save_user(db, admin, user, "UPDATE", password_changed=True)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), admin=Depends(require_company_admin)):
    user = get_company_user(db, admin, user_id, mutable=True)
    old = snapshot_model(user, AUDIT_FIELDS)
    user.status = "deleted"  # Retain historical foreign keys and reserve the login ID.
    save_user(db, admin, user, "DELETE", old)
    return Response(status_code=204)
