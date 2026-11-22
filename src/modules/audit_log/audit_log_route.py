from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from ...core.http.uuid_param import parse_optional_uuid
from ...core.security.permission_guard import require_permission
from .domain.audit_log_domain import AuditLogFilter
from .handlers.audit_log_handlers import auditLogHandler

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("", dependencies=[Depends(require_permission("audit_log.get"))])
async def get_all_audit_logs(
    user_id: Optional[str] = None,
    affected_table: Optional[str] = None,
    record_id: Optional[str] = None,
    action: Optional[str] = None,
    result: Optional[Literal["successful", "failed", "blocked"]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    f = AuditLogFilter(
        user_id=parse_optional_uuid(user_id, "user_id"),
        affected_table=affected_table or None,
        record_id=parse_optional_uuid(record_id, "record_id"),
        action=action or None,
        result=result,
        date_from=date_from,
        date_to=date_to,
    )
    return await auditLogHandler.get_all(f, limit, offset)


@router.get("/{audit_log_id}", dependencies=[Depends(require_permission("audit_log.get"))])
async def get_audit_log_by_id(audit_log_id: str):
    return await auditLogHandler.get_by_id(audit_log_id)
