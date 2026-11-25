from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile

from ...core.security.facility_scope import Scope, facility_scope
from ...core.security.permission_guard import require_permission
from ...core.security.throttle import throttle
from ...core.security.principal import current_principal
from ..data_import.handlers.data_import_handlers import dataImportHandler
from .handlers.pregnancy_handlers import (
    PregnancyCreateRequest,
    PregnancySearchRequest,
    PregnancyUpdateRequest,
    Risk,
    Status,
    build_filter,
    pregnancyHandler,
)

router = APIRouter(prefix="/pregnancies", tags=["pregnancies"])


def pregnancy_filter(
    q: Optional[str] = None,
    health_facility_id: Optional[str] = None,
    status: Optional[Status] = None,
    risk_level: Optional[Risk] = None,
    active: Optional[bool] = None,
    due_from: Optional[date] = None,
    due_to: Optional[date] = None,
    scope: Optional[Scope] = Depends(facility_scope),
):
    return build_filter(q, health_facility_id, status, risk_level, active, due_from, due_to, scope)


@router.get("", dependencies=[Depends(require_permission("pregnancy.get"))])
async def get_all_pregnancies(
    f=Depends(pregnancy_filter), limit: int = Query(25, ge=1, le=500), offset: int = Query(0, ge=0)
):
    return await pregnancyHandler.get_all(f, limit, offset)


def body_filter(body: PregnancySearchRequest, scope: Optional[Scope]):
    return build_filter(
        body.q, body.health_facility_id, body.status, body.risk_level, body.active, body.due_from, body.due_to, scope,
        body.mark,
    )


@router.post("/search", dependencies=[Depends(require_permission("pregnancy.get"))])
async def search_pregnancies(body: PregnancySearchRequest, scope: Optional[Scope] = Depends(facility_scope)):
    return await pregnancyHandler.get_all(body_filter(body, scope), body.limit, body.offset)


@router.post("/export", dependencies=[Depends(require_permission("pregnancy.export")), Depends(throttle("export", 10, 600))])
async def export_pregnancies_post(body: PregnancySearchRequest, scope: Optional[Scope] = Depends(facility_scope)):
    return await dataImportHandler.export(body_filter(body, scope), body.delimiter)


@router.get("/stats", dependencies=[Depends(require_permission("pregnancy.get"))])
async def get_pregnancy_stats(health_facility_id: Optional[str] = None, scope: Optional[Scope] = Depends(facility_scope)):
    return await pregnancyHandler.stats(health_facility_id, scope)


@router.get("/export", dependencies=[Depends(require_permission("pregnancy.export")), Depends(throttle("export", 10, 600))])
async def export_pregnancies(f=Depends(pregnancy_filter), delimiter: Optional[str] = None):
    return await dataImportHandler.export(f, delimiter)


@router.post(
    "/export/minsa",
    dependencies=[Depends(require_permission("pregnancy.export")), Depends(throttle("export", 10, 600))],
)
async def export_pregnancies_minsa(body: PregnancySearchRequest, scope: Optional[Scope] = Depends(facility_scope)):
    return await dataImportHandler.export_minsa(body_filter(body, scope), body.sections)


@router.post("/minsa", dependencies=[Depends(require_permission("pregnancy.get"))])
async def view_pregnancies_minsa(body: PregnancySearchRequest, scope: Optional[Scope] = Depends(facility_scope)):
    return await dataImportHandler.minsa_view(body_filter(body, scope), body.sections, min(body.limit, 100), body.offset)


@router.get("/import/template", dependencies=[Depends(require_permission("pregnancy.import"))])
async def import_template():
    return dataImportHandler.template()


@router.post("/import", dependencies=[Depends(require_permission("pregnancy.import")), Depends(throttle("import", 20, 600))])
async def import_pregnancies(request: Request, file: UploadFile = File(...), dry_run: bool = False):
    principal = current_principal(request)
    return await dataImportHandler.import_file(principal.user_id, principal.scope, file, dry_run)


@router.get("/{pregnancy_id}", dependencies=[Depends(require_permission("pregnancy.get"))])
async def get_pregnancy_by_id(pregnancy_id: str, scope: Optional[Scope] = Depends(facility_scope)):
    return await pregnancyHandler.get_by_id(pregnancy_id, scope)


@router.get("/{pregnancy_id}/history", dependencies=[Depends(require_permission("pregnancy.get"))])
async def get_pregnancy_history(pregnancy_id: str, scope: Optional[Scope] = Depends(facility_scope)):
    return await pregnancyHandler.history(pregnancy_id, scope)


@router.post("", dependencies=[Depends(require_permission("pregnancy.post"))])
async def create_pregnancy(request: Request, body: PregnancyCreateRequest):
    principal = current_principal(request)
    return await pregnancyHandler.create(principal.user_id, principal.scope, body)


@router.put("/{pregnancy_id}", dependencies=[Depends(require_permission("pregnancy.put"))])
async def update_pregnancy(
    pregnancy_id: str, body: PregnancyUpdateRequest, scope: Optional[Scope] = Depends(facility_scope)
):
    return await pregnancyHandler.update(pregnancy_id, body, scope)


@router.delete("/{pregnancy_id}", dependencies=[Depends(require_permission("pregnancy.delete"))])
async def delete_pregnancy(pregnancy_id: str, scope: Optional[Scope] = Depends(facility_scope)):
    return await pregnancyHandler.delete(pregnancy_id, scope)
