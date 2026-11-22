from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.health_facility_domain import HealthFacility

SELECT_FACILITY = """
SELECT f.id, f.code, f.name, f.category, f.district, f.address, f.phone, f.active,
       (SELECT count(*) FROM pregnancies p WHERE p.health_facility_id = f.id AND p.active)::int AS pregnancy_count,
       f.created_at, f.updated_at
FROM health_facilities f
"""


class HealthFacilityRepository:
    async def get_all(self, conn: asyncpg.Connection, q: Optional[str], active: Optional[bool]) -> list[HealthFacility]:
        rows = await conn.fetch(
            SELECT_FACILITY
            + """
            WHERE ($1::text IS NULL OR f.name ILIKE '%' || $1 || '%' OR f.code ILIKE '%' || $1 || '%')
              AND ($2::bool IS NULL OR f.active = $2)
            ORDER BY f.name
            """,
            q,
            active,
        )
        return [from_row(HealthFacility, row) for row in rows]

    async def get_by_id(self, conn: asyncpg.Connection, facility_id: UUID) -> Optional[HealthFacility]:
        row = await conn.fetchrow(SELECT_FACILITY + " WHERE f.id = $1", facility_id)
        return from_row(HealthFacility, row) if row else None

    async def find_by_code_or_name(self, conn: asyncpg.Connection, value: str) -> Optional[HealthFacility]:
        row = await conn.fetchrow(
            SELECT_FACILITY
            + """
            WHERE upper(f.code) = upper($1) OR lower(f.name) = lower($1)
               OR lower(regexp_replace(f.name, '^(C\\.S\\.|P\\.S\\.|H\\.)\\s*', '', 'i')) = lower($1)
            ORDER BY f.active DESC
            LIMIT 1
            """,
            value.strip(),
        )
        return from_row(HealthFacility, row) if row else None

    async def create(self, conn: asyncpg.Connection, f: HealthFacility) -> UUID:
        return await conn.fetchval(
            """
            INSERT INTO health_facilities (code, name, category, district, address, phone, active)
            VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
            """,
            f.code, f.name, f.category, f.district, f.address, f.phone, f.active,
        )

    async def update(self, conn: asyncpg.Connection, f: HealthFacility) -> None:
        await conn.execute(
            """
            UPDATE health_facilities SET code = $2, name = $3, category = $4, district = $5, address = $6,
                   phone = $7, active = $8
            WHERE id = $1
            """,
            f.id, f.code, f.name, f.category, f.district, f.address, f.phone, f.active,
        )

    async def is_used(self, conn: asyncpg.Connection, facility_id: UUID) -> bool:
        return await conn.fetchval("SELECT EXISTS (SELECT 1 FROM pregnancies WHERE health_facility_id = $1)", facility_id)

    async def deactivate(self, conn: asyncpg.Connection, facility_id: UUID) -> None:
        await conn.execute("UPDATE health_facilities SET active = FALSE WHERE id = $1", facility_id)

    async def delete(self, conn: asyncpg.Connection, facility_id: UUID) -> None:
        await conn.execute("DELETE FROM health_facilities WHERE id = $1", facility_id)


healthFacilityRepository = HealthFacilityRepository()
