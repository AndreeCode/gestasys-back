from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from ...core.security.facility_scope import Scope, facility_scope
from ...core.security.permission_guard import require_permission
from ...core.security.permissions import user_has_permission
from ...core.security.principal import current_principal
from .handlers.data_import_handlers import dataImportHandler

router = APIRouter(prefix="/imports", tags=["imports"])


async def own_imports_only(request: Request) -> Optional[UUID]:
    principal = current_principal(request)
    if principal.scope is None or await user_has_permission(principal.user_id, "audit_log.get"):
        return None
    return principal.user_id


@router.get("", dependencies=[Depends(require_permission("data_import.get"))])
async def get_all_imports(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    only_by: Optional[UUID] = Depends(own_imports_only),
    scope: Optional[Scope] = Depends(facility_scope),
):
    return await dataImportHandler.get_all(limit, offset, only_by, scope)


@router.get("/{import_id}", dependencies=[Depends(require_permission("data_import.get"))])
async def get_import_by_id(import_id: str, only_by: Optional[UUID] = Depends(own_imports_only)):
    return await dataImportHandler.get_by_id(import_id, only_by)
