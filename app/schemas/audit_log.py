from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# =========================================================
# AUDIT LOG RESPONSE
# =========================================================

class AuditLogResponse(BaseModel):

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    company_id: int

    user_id: int | None
    user_name: str | None = None
    user_login_id: str | None = None

    action: str

    module: str

    entity_type: str | None

    entity_id: int | None

    description: str

    old_values: dict[str, Any] | None

    new_values: dict[str, Any] | None

    ip_address: str | None

    user_agent: str | None

    created_at: datetime


# =========================================================
# PAGINATED RESPONSE
# =========================================================

class AuditLogListResponse(BaseModel):

    success: bool

    message: str

    total: int

    page: int

    page_size: int

    items: list[AuditLogResponse]
