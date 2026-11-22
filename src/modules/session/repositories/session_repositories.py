from datetime import datetime
from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.session_domain import Session

SELECT_SESSION = """
SELECT s.id, s.user_id, u.username, u.full_name, s.device_id, host(s.ip_address) AS ip_address, s.user_agent,
       s.created_at, s.expires_at, s.revoked, s.revoked_reason, s.revoked_at,
       (NOT s.revoked AND s.expires_at > NOW()) AS active
FROM sessions s
JOIN users u ON u.id = s.user_id
"""

WHERE = """
WHERE ($1::uuid IS NULL OR s.user_id = $1) AND ($2::uuid IS NULL OR s.device_id = $2)
  AND ($3::bool IS NULL OR (NOT s.revoked AND s.expires_at > NOW()) = $3)
"""


class SessionRepository:
    async def create(
        self,
        conn: asyncpg.Connection,
        session_id: UUID,
        user_id: UUID,
        device_id: UUID,
        token_hash: str,
        ip: Optional[str],
        user_agent: Optional[str],
        expires_at: datetime,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO sessions (id, user_id, device_id, token_hash, ip_address, user_agent, expires_at)
            VALUES ($1, $2, $3, $4, $5::text::inet, $6, $7)
            """,
            session_id,
            user_id,
            device_id,
            token_hash,
            ip,
            user_agent,
            expires_at,
        )

    async def revoke_by_token(self, conn: asyncpg.Connection, token_hash: str, reason: str) -> None:
        await conn.execute(
            "UPDATE sessions SET revoked = TRUE, revoked_reason = $2, revoked_at = NOW() WHERE token_hash = $1 AND NOT revoked",
            token_hash,
            reason,
        )

    async def list_active_for_user(self, conn: asyncpg.Connection, user_id: UUID) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT s.id, s.created_at, s.last_activity_at, s.expires_at, host(s.ip_address) AS ip_address, s.user_agent
            FROM sessions s
            WHERE s.user_id = $1 AND NOT s.revoked AND s.expires_at > NOW()
            ORDER BY s.last_activity_at DESC
            """,
            user_id,
        )
        return [dict(row) for row in rows]

    async def revoke_own(self, conn: asyncpg.Connection, user_id: UUID, session_id: UUID, reason: str) -> bool:
        result = await conn.execute(
            """
            UPDATE sessions SET revoked = TRUE, revoked_reason = $3, revoked_at = NOW()
            WHERE id = $1 AND user_id = $2 AND NOT revoked
            """,
            session_id,
            user_id,
            reason,
        )
        return result.endswith(" 1")

    async def revoke(self, conn: asyncpg.Connection, session_id: UUID, reason: str) -> None:
        await conn.execute(
            "UPDATE sessions SET revoked = TRUE, revoked_reason = $2, revoked_at = NOW() WHERE id = $1", session_id, reason
        )

    async def get_all(self, conn, user_id, device_id, active, limit: int, offset: int) -> tuple[list[Session], int]:
        total = await conn.fetchval("SELECT count(*) FROM sessions s" + WHERE, user_id, device_id, active)
        rows = await conn.fetch(
            SELECT_SESSION + WHERE + " ORDER BY s.created_at DESC LIMIT $4 OFFSET $5",
            user_id,
            device_id,
            active,
            limit,
            offset,
        )
        return [from_row(Session, row) for row in rows], total

    async def get_by_id(self, conn: asyncpg.Connection, session_id: UUID) -> Optional[Session]:
        row = await conn.fetchrow(SELECT_SESSION + " WHERE s.id = $1", session_id)
        return from_row(Session, row) if row else None


sessionRepository = SessionRepository()
