from ....core.http.list import list_response
from ....core.http.success import success
from ....core.http.uuid_param import parse_uuid
from ..domain.audit_log_domain import AuditLogFilter
from ..services.audit_log_service import auditLogService


class AuditLogHandler:
    async def get_all(self, f: AuditLogFilter, limit: int, offset: int):
        items, total = await auditLogService.get_all(f, limit, offset)
        return list_response(
            200,
            "Auditoria obtenida correctamente",
            [i.to_dict() for i in items],
            {"total": total, "limit": limit, "offset": offset},
        )

    async def get_by_id(self, log_id: str):
        log = await auditLogService.get_by_id(parse_uuid(log_id, "audit_log_id"))
        return success(200, "Registro de auditoria obtenido correctamente", log.to_dict())


auditLogHandler = AuditLogHandler()
