from typing import Literal, Optional
from uuid import UUID

from fastapi.responses import FileResponse

from ....core.http.list import list_response
from ....core.http.request_models import StrictModel
from ....core.http.success import success
from ....core.http.uuid_param import parse_uuid
from ..services.backup_service import backupService


class BackupCreateRequest(StrictModel):
    priority: Literal["high", "normal", "low"] = "high"


class BackupHandler:
    async def get_all(self, kind: Optional[str], status: Optional[str], limit: int, offset: int):
        items, total = await backupService.get_all(kind, status, limit, offset)
        return list_response(
            200,
            "Backups obtenidos correctamente",
            [b.to_dict() for b in items],
            {"total": total, "limit": limit, "offset": offset},
        )

    async def status(self):
        return success(200, "Estado de backups obtenido correctamente", await backupService.status())

    async def get_by_id(self, backup_id: str):
        backup = await backupService.get_by_id(parse_uuid(backup_id, "backup_id"))
        return success(200, "Backup obtenido correctamente", backup.to_dict())

    async def create(self, created_by: UUID, body: Optional[BackupCreateRequest]):
        priority = body.priority if body else "high"
        backup = await backupService.start("manual", priority, created_by)
        return success(202, f"Backup iniciado: consulta su estado en /api/backups/{backup.id}", backup.to_dict())

    async def download(self, backup_id: str):
        backup = await backupService.get_by_id(parse_uuid(backup_id, "backup_id"))
        path = backupService.file_path(backup)
        return FileResponse(path, filename=path.name, media_type="application/octet-stream")

    async def delete(self, backup_id: str):
        await backupService.delete(parse_uuid(backup_id, "backup_id"))
        return success(200, "Backup eliminado correctamente")


backupHandler = BackupHandler()
