from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.data_import_domain import DataImport

SELECT_IMPORT = """
SELECT i.id, i.file_name, i.total_rows, i.inserted, i.updated, i.failed, i.errors, i.imported_by,
       u.full_name AS imported_by_name, i.format, host(i.ip_address) AS ip_address, i.user_agent,
       f.name AS health_facility_name, mn.name AS micro_network_name, i.created_at
FROM data_imports i
LEFT JOIN users u ON u.id = i.imported_by
LEFT JOIN health_facilities f ON f.id = i.health_facility_id
LEFT JOIN micro_networks mn ON mn.id = i.micro_network_id
"""

WHERE = """
 WHERE ($1::uuid IS NULL OR i.imported_by = $1)
   AND (($2::uuid[] IS NULL AND $3::uuid IS NULL)
        OR i.health_facility_id = ANY($2) OR ($3::uuid IS NOT NULL AND i.micro_network_id = $3))
"""


class DataImportRepository:
    async def get_all(
        self,
        conn: asyncpg.Connection,
        limit: int,
        offset: int,
        imported_by: Optional[UUID] = None,
        facility_ids: Optional[list[UUID]] = None,
        micro_network_id: Optional[UUID] = None,
    ) -> tuple[list[DataImport], int]:
        args = (imported_by, facility_ids, micro_network_id)
        total = await conn.fetchval("SELECT count(*) FROM data_imports i" + WHERE, *args)
        rows = await conn.fetch(SELECT_IMPORT + WHERE + " ORDER BY i.created_at DESC LIMIT $4 OFFSET $5", *args, limit, offset)
        return [from_row(DataImport, row) for row in rows], total

    async def get_by_id(self, conn: asyncpg.Connection, import_id: UUID) -> Optional[DataImport]:
        row = await conn.fetchrow(SELECT_IMPORT + " WHERE i.id = $1", import_id)
        return from_row(DataImport, row) if row else None

    async def create(self, conn: asyncpg.Connection, d: DataImport) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            INSERT INTO data_imports (file_name, total_rows, inserted, updated, failed, errors, imported_by, format,
                                      ip_address, user_agent, health_facility_id, micro_network_id)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8,
                    NULLIF(current_setting('app.ip_address', true), '')::inet,
                    NULLIF(current_setting('app.user_agent', true), ''),
                    audit_setting_uuid('app.health_facility_id'),
                    COALESCE(audit_setting_uuid('app.micro_network_id'),
                             (SELECT micro_network_id FROM health_facilities
                              WHERE id = audit_setting_uuid('app.health_facility_id'))))
            RETURNING id, created_at
            """,
            d.file_name, d.total_rows, d.inserted, d.updated, d.failed, d.errors, d.imported_by, d.format,
        )

    async def set_import(self, conn: asyncpg.Connection, import_id: UUID, pregnancy_ids: list[UUID]) -> None:
        await conn.execute("UPDATE pregnancies SET import_id = $1 WHERE id = ANY($2::uuid[])", import_id, pregnancy_ids)


dataImportRepository = DataImportRepository()
