from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.micro_network_domain import MicroNetwork

SELECT_NETWORK = """
SELECT m.id, m.code, m.name, m.network, m.active,
       (SELECT count(*) FROM health_facilities f WHERE f.micro_network_id = m.id AND f.active)::int AS facility_count,
       (SELECT count(*) FROM pregnancies p JOIN health_facilities f ON f.id = p.health_facility_id
        WHERE f.micro_network_id = m.id AND p.active)::int AS pregnancy_count,
       (SELECT count(*) FROM users u LEFT JOIN health_facilities f ON f.id = u.health_facility_id
        WHERE u.active AND (u.micro_network_id = m.id OR f.micro_network_id = m.id))::int AS user_count,
       m.created_at, m.updated_at
FROM micro_networks m
"""


class MicroNetworkRepository:
    async def get_all(
        self, conn: asyncpg.Connection, q: Optional[str], active: Optional[bool], only: Optional[UUID] = None
    ) -> list[MicroNetwork]:
        rows = await conn.fetch(
            SELECT_NETWORK
            + """
            WHERE ($1::text IS NULL OR m.name ILIKE '%' || $1 || '%' OR m.code ILIKE '%' || $1 || '%')
              AND ($2::bool IS NULL OR m.active = $2)
              AND ($3::uuid IS NULL OR m.id = $3)
            ORDER BY m.name
            """,
            q,
            active,
            only,
        )
        return [from_row(MicroNetwork, row) for row in rows]

    async def get_by_id(self, conn: asyncpg.Connection, network_id: UUID) -> Optional[MicroNetwork]:
        row = await conn.fetchrow(SELECT_NETWORK + " WHERE m.id = $1", network_id)
        return from_row(MicroNetwork, row) if row else None

    async def find_by_name(self, conn: asyncpg.Connection, name: str) -> Optional[MicroNetwork]:
        row = await conn.fetchrow(
            SELECT_NETWORK
            + """
            WHERE lower(m.name) = lower($1) OR upper(m.code) = upper($1)
               OR lower(regexp_replace(m.name, '^(micro\\s*red|mr\\.?)\\s*(de\\s+salud\\s+)?', '', 'i')) = lower($1)
            LIMIT 1
            """,
            name.strip(),
        )
        return from_row(MicroNetwork, row) if row else None

    async def create(self, conn: asyncpg.Connection, m: MicroNetwork) -> UUID:
        return await conn.fetchval(
            "INSERT INTO micro_networks (code, name, network, active) VALUES ($1, $2, $3, $4) RETURNING id",
            m.code,
            m.name,
            m.network,
            m.active,
        )

    async def update(self, conn: asyncpg.Connection, m: MicroNetwork) -> None:
        await conn.execute(
            "UPDATE micro_networks SET code = $2, name = $3, network = $4, active = $5 WHERE id = $1",
            m.id,
            m.code,
            m.name,
            m.network,
            m.active,
        )


microNetworkRepository = MicroNetworkRepository()
