from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile

from ...core.security.permission_guard import require_permission
from ...core.security.principal import current_principal
from ..data_import.handlers.data_import_handlers import dataImportHandler
from .handlers.pregnancy_handlers import (
    PregnancyCreateRequest,
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
):
    return build_filter(q, health_facility_id, status, risk_level, active, due_from, due_to)


@router.get("", dependencies=[Depends(require_permission("pregnancy.get"))])
async def get_all_pregnancies(
    f=Depends(pregnancy_filter), limit: int = Query(25, ge=1, le=500), offset: int = Query(0, ge=0)
):
    return await pregnancyHandler.get_all(f, limit, offset)


@router.get("/stats", dependencies=[Depends(require_permission("pregnancy.get"))])
async def get_pregnancy_stats(health_facility_id: Optional[str] = None):
    return await pregnancyHandler.stats(health_facility_id)


@router.get("/export", dependencies=[Depends(require_permission("pregnancy.export"))])
async def export_pregnancies(f=Depends(pregnancy_filter), delimiter: Optional[str] = None):
    return await dataImportHandler.export(f, delimiter)


@router.get("/import/template", dependencies=[Depends(require_permission("pregnancy.import"))])
async def import_template():
    return dataImportHandler.template()


@router.post("/import", dependencies=[Depends(require_permission("pregnancy.import"))])
async def import_pregnancies(request: Request, file: UploadFile = File(...), dry_run: bool = False):
    return await dataImportHandler.import_file(current_principal(request).user_id, file, dry_run)


@router.get("/{pregnancy_id}", dependencies=[Depends(require_permission("pregnancy.get"))])
async def get_pregnancy_by_id(pregnancy_id: str):
    return await pregnancyHandler.get_by_id(pregnancy_id)


@router.post("", dependencies=[Depends(require_permission("pregnancy.post"))])
async def create_pregnancy(request: Request, body: PregnancyCreateRequest):
    return await pregnancyHandler.create(current_principal(request).user_id, body)


@router.put("/{pregnancy_id}", dependencies=[Depends(require_permission("pregnancy.put"))])
async def update_pregnancy(pregnancy_id: str, body: PregnancyUpdateRequest):
    return await pregnancyHandler.update(pregnancy_id, body)


@router.delete("/{pregnancy_id}", dependencies=[Depends(require_permission("pregnancy.delete"))])
async def delete_pregnancy(pregnancy_id: str):
    return await pregnancyHandler.delete(pregnancy_id)
