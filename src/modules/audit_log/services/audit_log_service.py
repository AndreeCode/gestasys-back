from uuid import UUID

from ....core.db.connection import connection
from ....core.http.app_error import NotFoundError
from ..domain.audit_log_domain import AuditLog, AuditLogFilter
from ..repositories.audit_log_repositories import auditLogRepository


class AuditLogService:
    async def get_all(self, f: AuditLogFilter, limit: int, offset: int) -> tuple[list[AuditLog], int]:
        async with connection() as conn:
            return await auditLogRepository.get_all(conn, f, limit, offset)

    async def get_by_id(self, log_id: UUID) -> AuditLog:
        async with connection() as conn:
            log = await auditLogRepository.get_by_id(conn, log_id)
        if log is None:
            raise NotFoundError("Registro de auditoria no encontrado")
        return log


auditLogService = AuditLogService()
