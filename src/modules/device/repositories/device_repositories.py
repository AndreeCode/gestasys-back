from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.device_domain import Device

SELECT_DEVICE = """
SELECT d.id, d.user_id, u.username, u.full_name, d.device_hash, d.user_agent, d.first_seen_at, d.last_seen_at,
       d.trusted, d.blocked_reason, d.blocked_at,
       (SELECT count(*) FROM sessions s WHERE s.device_id = d.id AND NOT s.revoked AND s.expires_at > NOW())::int
           AS active_sessions
FROM devices d
JOIN users u ON u.id = d.user_id
"""


class DeviceRepository:
    async def get_all(self, conn: asyncpg.Connection, user_id: Optional[UUID], trusted: Optional[bool]) -> list[Device]:
        rows = await conn.fetch(
            SELECT_DEVICE
            + " WHERE ($1::uuid IS NULL OR d.user_id = $1) AND ($2::bool IS NULL OR d.trusted = $2) ORDER BY d.last_seen_at DESC",
            user_id,
            trusted,
        )
        return [from_row(Device, row) for row in rows]

    async def get_by_id(self, conn: asyncpg.Connection, device_id: UUID) -> Optional[Device]:
        row = await conn.fetchrow(SELECT_DEVICE + " WHERE d.id = $1", device_id)
        return from_row(Device, row) if row else None

    async def register(self, conn: asyncpg.Connection, user_id: UUID, device_hash: str, user_agent: Optional[str]) -> Device:
        device_id = await conn.fetchval(
            """
            INSERT INTO devices (user_id, device_hash, user_agent) VALUES ($1, $2, $3)
            ON CONFLICT (user_id, device_hash)
            DO UPDATE SET last_seen_at = NOW(), user_agent = COALESCE(EXCLUDED.user_agent, devices.user_agent)
            RETURNING id
            """,
            user_id,
            device_hash,
            user_agent,
        )
        return await self.get_by_id(conn, device_id)

    async def update(self, conn: asyncpg.Connection, device_id: UUID, trusted: bool, reason: Optional[str]) -> None:
        await conn.execute("UPDATE devices SET trusted = $2, blocked_reason = $3 WHERE id = $1", device_id, trusted, reason)


deviceRepository = DeviceRepository()
