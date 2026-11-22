from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, Query, Request

from ...core.security.permission_guard import require_permission
from ...core.security.principal import current_principal
from .handlers.backup_handlers import BackupCreateRequest, backupHandler

router = APIRouter(prefix="/backups", tags=["backups"])


@router.get("", dependencies=[Depends(require_permission("backup.get"))])
async def get_all_backups(
    kind: Optional[Literal["manual", "automatic"]] = None,
    status: Optional[Literal["running", "completed", "failed"]] = None,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await backupHandler.get_all(kind, status, limit, offset)


@router.get("/status", dependencies=[Depends(require_permission("backup.get"))])
async def get_backup_status():
    return await backupHandler.status()


@router.get("/{backup_id}", dependencies=[Depends(require_permission("backup.get"))])
async def get_backup_by_id(backup_id: str):
    return await backupHandler.get_by_id(backup_id)


@router.get("/{backup_id}/file", dependencies=[Depends(require_permission("backup.get"))])
async def download_backup(backup_id: str):
    return await backupHandler.download(backup_id)


@router.post("", dependencies=[Depends(require_permission("backup.post"))])
async def create_backup(request: Request, body: Optional[BackupCreateRequest] = Body(default=None)):
    return await backupHandler.create(current_principal(request).user_id, body)


@router.delete("/{backup_id}", dependencies=[Depends(require_permission("backup.delete"))])
async def delete_backup(backup_id: str):
    return await backupHandler.delete(backup_id)
