from uuid import UUID

from ....core.db.connection import connection, transaction
from ....core.http.app_error import BadRequestError, ConflictError, NotFoundError
from ..domain.session_domain import Session
from ..repositories.session_repositories import sessionRepository


class SessionService:
    async def get_all(self, user_id, device_id, active, limit: int, offset: int) -> tuple[list[Session], int]:
        async with connection() as conn:
            return await sessionRepository.get_all(conn, user_id, device_id, active, limit, offset)

    async def get_by_id(self, session_id: UUID) -> Session:
        async with connection() as conn:
            session = await sessionRepository.get_by_id(conn, session_id)
        if session is None:
            raise NotFoundError("Sesion no encontrada")
        return session

    async def revoke_by_token(self, token_hash: str, reason: str) -> None:
        async with transaction() as conn:
            await sessionRepository.revoke_by_token(conn, token_hash, reason)

    async def revoke(self, current_session: UUID, session_id: UUID) -> None:
        if current_session == session_id:
            raise BadRequestError("Para cerrar tu sesion actual usa /api/auth/logout")
        session = await self.get_by_id(session_id)
        if not session.active:
            raise ConflictError("La sesion ya estaba cerrada o expirada")
        async with transaction() as conn:
            await sessionRepository.revoke(conn, session_id, "revoked_by_admin")


sessionService = SessionService()
