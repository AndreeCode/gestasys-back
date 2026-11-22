from typing import Optional
from uuid import UUID

from ....core.http.list import list_response
from ....core.http.request_models import StrictModel
from ....core.http.success import success
from ....core.http.uuid_param import parse_optional_uuid, parse_uuid
from ..services.device_service import deviceService


class DeviceUpdateRequest(StrictModel):
    trusted: bool
    blocked_reason: Optional[str] = None


class DeviceHandler:
    async def get_all(self, current_device: UUID, user_id: Optional[str], trusted: Optional[bool]):
        devices = await deviceService.get_all(parse_optional_uuid(user_id, "user_id"), trusted)
        return list_response(
            200,
            "Dispositivos obtenidos correctamente",
            [d.to_dict() for d in devices],
            {"total": len(devices), "current_device_id": current_device},
        )

    async def get_by_id(self, device_id: str):
        device = await deviceService.get_by_id(parse_uuid(device_id, "device_id"))
        return success(200, "Dispositivo obtenido correctamente", device.to_dict())

    async def update(self, current_device: UUID, device_id: str, body: DeviceUpdateRequest):
        device = await deviceService.update(current_device, parse_uuid(device_id, "device_id"), body.trusted, body.blocked_reason)
        msg = "Dispositivo desbloqueado correctamente" if device.trusted else "Dispositivo bloqueado y sus sesiones cerradas"
        return success(200, msg, device.to_dict())


deviceHandler = DeviceHandler()
