from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Request

from ...core.security.permission_guard import require_permission
from ...core.security.principal import current_principal
from .handlers.prenatal_control_handlers import (
    PrenatalControlCreateRequest,
    PrenatalControlUpdateRequest,
    prenatalControlHandler,
)

router = APIRouter(prefix="/prenatal-controls", tags=["prenatal-controls"])


@router.get("", dependencies=[Depends(require_permission("prenatal_control.get"))])
async def get_all_prenatal_controls(
    pregnancy_id: Optional[str] = None, date_from: Optional[date] = None, date_to: Optional[date] = None
):
    return await prenatalControlHandler.get_all(pregnancy_id, date_from, date_to)


@router.get("/{prenatal_control_id}", dependencies=[Depends(require_permission("prenatal_control.get"))])
async def get_prenatal_control_by_id(prenatal_control_id: str):
    return await prenatalControlHandler.get_by_id(prenatal_control_id)


@router.post("", dependencies=[Depends(require_permission("prenatal_control.post"))])
async def create_prenatal_control(request: Request, body: PrenatalControlCreateRequest):
    return await prenatalControlHandler.create(current_principal(request).user_id, body)


@router.put("/{prenatal_control_id}", dependencies=[Depends(require_permission("prenatal_control.put"))])
async def update_prenatal_control(prenatal_control_id: str, body: PrenatalControlUpdateRequest):
    return await prenatalControlHandler.update(prenatal_control_id, body)


@router.delete("/{prenatal_control_id}", dependencies=[Depends(require_permission("prenatal_control.delete"))])
async def delete_prenatal_control(prenatal_control_id: str):
    return await prenatalControlHandler.delete(prenatal_control_id)
