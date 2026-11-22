from typing import Optional

from fastapi import APIRouter, Depends, Request

from ...core.security.permission_guard import require_permission
from ...core.security.principal import current_principal
from .handlers.device_handlers import DeviceUpdateRequest, deviceHandler

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", dependencies=[Depends(require_permission("device.get"))])
async def get_all_devices(request: Request, user_id: Optional[str] = None, trusted: Optional[bool] = None):
    return await deviceHandler.get_all(current_principal(request).device_id, user_id, trusted)


@router.get("/{device_id}", dependencies=[Depends(require_permission("device.get"))])
async def get_device_by_id(device_id: str):
    return await deviceHandler.get_by_id(device_id)


@router.put("/{device_id}", dependencies=[Depends(require_permission("device.put"))])
async def update_device(request: Request, device_id: str, body: DeviceUpdateRequest):
    return await deviceHandler.update(current_principal(request).device_id, device_id, body)
