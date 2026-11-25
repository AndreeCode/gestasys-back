from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from ...core.http.uuid_param import parse_optional_uuid
from ...core.security.facility_scope import Scope, facility_scope, restrict_facility
from ...core.security.permission_guard import require_permission
from ...core.security.throttle import throttle
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
    q: Optional[str] = Query(None, max_length=100),
    health_facility_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    scope: Optional[Scope] = Depends(facility_scope),
):
    requested = parse_optional_uuid(health_facility_id, "health_facility_id")
    f = AuditLogFilter(
        user_id=parse_optional_uuid(user_id, "user_id"),
        affected_table=affected_table or None,
        record_id=parse_optional_uuid(record_id, "record_id"),
        action=action or None,
        result=result,
        date_from=date_from,
        date_to=date_to,
        q=(q or "").strip() or None,
        health_facility_ids=restrict_facility(requested, scope),
        micro_network_id=scope.micro_network_id if scope is not None and requested is None else None,
    )
    return await auditLogHandler.get_all(f, limit, offset)


@router.get("/verify", dependencies=[Depends(require_permission("audit_log.get")), Depends(throttle("audit_verify", 6, 600))])
async def verify_audit_chain(scope: Optional[Scope] = Depends(facility_scope)):
    return await auditLogHandler.verify(scope)


@router.get("/{audit_log_id}", dependencies=[Depends(require_permission("audit_log.get"))])
async def get_audit_log_by_id(audit_log_id: str, scope: Optional[Scope] = Depends(facility_scope)):
    return await auditLogHandler.get_by_id(audit_log_id, scope)
