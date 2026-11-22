from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from ...core.security.permission_guard import require_permission
from ...core.security.principal import current_principal
from .handlers.data_import_handlers import dataImportHandler

router = APIRouter(prefix="/imports", tags=["imports"])


def own_imports_only(request: Request) -> Optional[UUID]:
    principal = current_principal(request)
    return principal.user_id if principal.health_facility_id is not None else None


@router.get("", dependencies=[Depends(require_permission("data_import.get"))])
async def get_all_imports(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    only_by: Optional[UUID] = Depends(own_imports_only),
):
    return await dataImportHandler.get_all(limit, offset, only_by)


@router.get("/{import_id}", dependencies=[Depends(require_permission("data_import.get"))])
async def get_import_by_id(import_id: str, only_by: Optional[UUID] = Depends(own_imports_only)):
    return await dataImportHandler.get_by_id(import_id, only_by)
