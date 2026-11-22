from typing import Optional
from uuid import UUID

from ....core.db.connection import connection, transaction
from ....core.http.app_error import ForbiddenError, NotFoundError, ValidationError
from ....core.http.validation import clean
from ..domain.device_domain import Device
from ..repositories.device_repositories import deviceRepository


class DeviceService:
    async def get_all(self, user_id: Optional[UUID] = None, trusted: Optional[bool] = None) -> list[Device]:
        async with connection() as conn:
            return await deviceRepository.get_all(conn, user_id, trusted)

    async def get_by_id(self, device_id: UUID) -> Device:
        async with connection() as conn:
            device = await deviceRepository.get_by_id(conn, device_id)
        if device is None:
            raise NotFoundError("Dispositivo no encontrado")
        return device

    async def register(self, user_id: UUID, device_hash: str, user_agent: Optional[str]) -> Device:
        async with transaction() as conn:
            return await deviceRepository.register(conn, user_id, device_hash, user_agent)

    async def update(self, current_device: UUID, device_id: UUID, trusted: bool, blocked_reason: Optional[str]) -> Device:
        await self.get_by_id(device_id)
        reason = clean(blocked_reason)
        if not trusted:
            if device_id == current_device:
                raise ForbiddenError("No puedes bloquear el dispositivo que estas usando")
            if not reason:
                raise ValidationError("blocked_reason es obligatorio al bloquear un dispositivo")
        else:
            reason = None
        async with transaction() as conn:
            await deviceRepository.update(conn, device_id, trusted, reason)
        return await self.get_by_id(device_id)


deviceService = DeviceService()
