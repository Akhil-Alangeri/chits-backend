from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.admin.user import User

from app.schemas.audit_log import AuditLogListResponse

from app.services.audit_log_service import (
    get_audit_history,
)


router = APIRouter(
    prefix="/admin/audit-history",
    tags=["Admin Audit History"],
)


# =========================================================
# GET AUDIT HISTORY
# =========================================================

@router.get(
    "",
    response_model=AuditLogListResponse,
)
def get_audit_history_route(
    page: int = Query(
        default=1,
        ge=1,
    ),

    page_size: int = Query(
        default=25,
        ge=1,
        le=100,
    ),

    action: str | None = Query(
        default=None,
    ),

    module: str | None = Query(
        default=None,
    ),

    user_id: int | None = Query(
        default=None,
    ),

    entity_type: str | None = Query(
        default=None,
    ),

    entity_id: int | None = Query(
        default=None,
    ),

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    ),
):

    items, total = get_audit_history(
        db=db,
        company_id=current_user.company_id,
        page=page,
        page_size=page_size,
        action=action,
        module=module,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )

    return {
        "success": True,
        "message": "Audit history fetched successfully.",
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }