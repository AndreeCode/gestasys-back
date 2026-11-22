from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.backup_domain import Backup

SELECT_BACKUP = """
SELECT b.id, b.kind::text AS kind, b.status::text AS status, b.file_name, b.size_bytes, b.sha256, b.tables, b.priority,
       b.error, b.created_by, u.full_name AS created_by_name, b.started_at, b.finished_at
FROM backups b
LEFT JOIN users u ON u.id = b.created_by
"""

WHERE = " WHERE ($1::text IS NULL OR b.kind::text = $1) AND ($2::text IS NULL OR b.status::text = $2)"


class BackupRepository:
    async def get_all(self, conn, kind, status, limit: int, offset: int) -> tuple[list[Backup], int]:
        total = await conn.fetchval("SELECT count(*) FROM backups b" + WHERE, kind, status)
        rows = await conn.fetch(SELECT_BACKUP + WHERE + " ORDER BY b.started_at DESC LIMIT $3 OFFSET $4", kind, status, limit, offset)
        return [from_row(Backup, row) for row in rows], total

    async def get_by_id(self, conn: asyncpg.Connection, backup_id: UUID) -> Optional[Backup]:
        row = await conn.fetchrow(SELECT_BACKUP + " WHERE b.id = $1", backup_id)
        return from_row(Backup, row) if row else None

    async def latest(self, conn: asyncpg.Connection, status: str) -> Optional[Backup]:
        row = await conn.fetchrow(SELECT_BACKUP + " WHERE b.status::text = $1 ORDER BY b.started_at DESC LIMIT 1", status)
        return from_row(Backup, row) if row else None

    async def summary(self, conn: asyncpg.Connection) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            SELECT EXISTS (SELECT 1 FROM backups WHERE status = 'running') AS running,
                   COALESCE(sum(size_bytes) FILTER (WHERE status = 'completed'), 0)::bigint AS total_size_bytes
            FROM backups
            """
        )

    async def is_running(self, conn: asyncpg.Connection) -> bool:
        return await conn.fetchval("SELECT EXISTS (SELECT 1 FROM backups WHERE status = 'running')")

    async def tables(self, conn: asyncpg.Connection) -> list[str]:
        rows = await conn.fetch("SELECT tablename::text FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        return [row[0] for row in rows]

    async def create(self, conn, kind: str, tables: list[str], priority: str, created_by: Optional[UUID]) -> UUID:
        return await conn.fetchval(
            """
            INSERT INTO backups (kind, status, tables, priority, created_by)
            VALUES ($1::backup_kind, 'running', $2, $3, $4) RETURNING id
            """,
            kind,
            tables,
            priority,
            created_by,
        )

    async def finish(self, conn, backup_id: UUID, status: str, file_name, size_bytes, error, sha256=None) -> None:
        await conn.execute(
            """
            UPDATE backups SET status = $2::backup_status, file_name = $3, size_bytes = $4, error = $5,
                   sha256 = $6, finished_at = NOW()
            WHERE id = $1
            """,
            backup_id,
            status,
            file_name,
            size_bytes,
            error,
            sha256,
        )

    async def old_automatic(self, conn: asyncpg.Connection, keep: int) -> list[Backup]:
        rows = await conn.fetch(
            SELECT_BACKUP + " WHERE b.kind = 'automatic' AND b.status <> 'running' ORDER BY b.started_at DESC OFFSET $1", keep
        )
        return [from_row(Backup, row) for row in rows]

    async def delete(self, conn: asyncpg.Connection, backup_id: UUID) -> None:
        await conn.execute("DELETE FROM backups WHERE id = $1", backup_id)

    async def mark_interrupted(self, conn: asyncpg.Connection) -> None:
        await conn.execute(
            """
            UPDATE backups SET status = 'failed', error = 'Interrumpido por reinicio del servidor', finished_at = NOW()
            WHERE status = 'running'
            """
        )


backupRepository = BackupRepository()
