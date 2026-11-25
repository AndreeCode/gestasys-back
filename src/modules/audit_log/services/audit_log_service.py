from typing import Optional
from uuid import UUID

from ....core.db.connection import connection
from ....core.http.app_error import NotFoundError
from ....core.security.facility_scope import Scope, in_scope
from ..domain.audit_log_domain import AuditLog, AuditLogFilter
from ..repositories.audit_log_repositories import auditLogRepository


def visible(log: AuditLog, scope: Optional[Scope]) -> bool:
    if scope is None:
        return True
    if log.health_facility_id is not None and in_scope(log.health_facility_id, scope):
        return True
    return scope.micro_network_id is not None and log.micro_network_id == scope.micro_network_id


class AuditLogService:
    async def get_all(self, f: AuditLogFilter, limit: int, offset: int) -> tuple[list[AuditLog], int]:
        async with connection() as conn:
            return await auditLogRepository.get_all(conn, f, limit, offset)

    async def get_by_id(self, log_id: UUID, scope: Optional[Scope] = None) -> AuditLog:
        async with connection() as conn:
            log = await auditLogRepository.get_by_id(conn, log_id)
        if log is None or not visible(log, scope):
            raise NotFoundError("Registro de auditoria no encontrado")
        return log

    async def record_history(self, pregnancy_id: UUID) -> list[AuditLog]:
        async with connection() as conn:
            return await auditLogRepository.record_history(conn, pregnancy_id)


auditLogService = AuditLogService()
