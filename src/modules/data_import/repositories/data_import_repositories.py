from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.data_import_domain import DataImport

SELECT_IMPORT = """
SELECT i.id, i.file_name, i.total_rows, i.inserted, i.updated, i.failed, i.errors, i.imported_by,
       u.full_name AS imported_by_name, i.created_at
FROM data_imports i
LEFT JOIN users u ON u.id = i.imported_by
"""


class DataImportRepository:
    async def get_all(self, conn: asyncpg.Connection, limit: int, offset: int) -> tuple[list[DataImport], int]:
        total = await conn.fetchval("SELECT count(*) FROM data_imports")
        rows = await conn.fetch(SELECT_IMPORT + " ORDER BY i.created_at DESC LIMIT $1 OFFSET $2", limit, offset)
        return [from_row(DataImport, row) for row in rows], total

    async def get_by_id(self, conn: asyncpg.Connection, import_id: UUID) -> Optional[DataImport]:
        row = await conn.fetchrow(SELECT_IMPORT + " WHERE i.id = $1", import_id)
        return from_row(DataImport, row) if row else None

    async def create(self, conn: asyncpg.Connection, d: DataImport) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            INSERT INTO data_imports (file_name, total_rows, inserted, updated, failed, errors, imported_by)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7) RETURNING id, created_at
            """,
            d.file_name, d.total_rows, d.inserted, d.updated, d.failed, d.errors, d.imported_by,
        )


dataImportRepository = DataImportRepository()
