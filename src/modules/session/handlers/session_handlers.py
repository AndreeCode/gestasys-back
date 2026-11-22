from typing import Optional
from uuid import UUID

from ....core.http.list import list_response
from ....core.http.success import success
from ....core.http.uuid_param import parse_optional_uuid, parse_uuid
from ..services.session_service import sessionService


class SessionHandler:
    async def get_all(self, current: UUID, user_id: Optional[str], device_id: Optional[str], active: Optional[bool], limit: int, offset: int):
        sessions, total = await sessionService.get_all(
            parse_optional_uuid(user_id, "user_id"), parse_optional_uuid(device_id, "device_id"), active, limit, offset
        )
        for s in sessions:
            s.current = s.id == current
        return list_response(
            200,
            "Sesiones obtenidas correctamente",
            [s.to_dict() for s in sessions],
            {"total": total, "limit": limit, "offset": offset},
        )

    async def get_by_id(self, current: UUID, session_id: str):
        session = await sessionService.get_by_id(parse_uuid(session_id, "session_id"))
        session.current = session.id == current
        return success(200, "Sesion obtenida correctamente", session.to_dict())

    async def delete(self, current: UUID, session_id: str):
        await sessionService.revoke(current, parse_uuid(session_id, "session_id"))
        return success(200, "Sesion cerrada correctamente")


sessionHandler = SessionHandler()
