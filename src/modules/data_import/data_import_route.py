from fastapi import APIRouter, Depends, Query

from ...core.security.permission_guard import require_permission
from .handlers.data_import_handlers import dataImportHandler

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("", dependencies=[Depends(require_permission("data_import.get"))])
async def get_all_imports(limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0)):
    return await dataImportHandler.get_all(limit, offset)


@router.get("/{import_id}", dependencies=[Depends(require_permission("data_import.get"))])
async def get_import_by_id(import_id: str):
    return await dataImportHandler.get_by_id(import_id)
