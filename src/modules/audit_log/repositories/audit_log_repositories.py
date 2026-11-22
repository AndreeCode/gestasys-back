from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.audit_log_domain import AuditLog, AuditLogFilter

SELECT_LOG = """
SELECT a.id, a.user_id, u.full_name AS user_name, a.device_id, a.action, a.affected_table, a.record_id, a.record_key,
       host(a.ip_address) AS ip_address, a.user_agent, a.result::text AS result, a.details, a.created_at
FROM audit_log a
LEFT JOIN users u ON u.id = a.user_id
"""

WHERE = """
WHERE ($1::uuid IS NULL OR a.user_id = $1)
  AND ($2::text IS NULL OR a.affected_table = $2)
  AND ($3::uuid IS NULL OR a.record_id = $3)
  AND ($4::text IS NULL OR a.action = upper($4))
  AND ($5::text IS NULL OR a.result::text = $5)
  AND ($6::date IS NULL OR a.created_at >= $6::date)
  AND ($7::date IS NULL OR a.created_at < $7::date + 1)
"""


class AuditLogRepository:
    async def get_all(self, conn: asyncpg.Connection, f: AuditLogFilter, limit: int, offset: int) -> tuple[list[AuditLog], int]:
        total = await conn.fetchval("SELECT count(*) FROM audit_log a" + WHERE, *f.args())
        rows = await conn.fetch(SELECT_LOG + WHERE + " ORDER BY a.created_at DESC LIMIT $8 OFFSET $9", *f.args(), limit, offset)
        return [from_row(AuditLog, row) for row in rows], total

    async def get_by_id(self, conn: asyncpg.Connection, log_id: UUID) -> Optional[AuditLog]:
        row = await conn.fetchrow(SELECT_LOG + " WHERE a.id = $1", log_id)
        return from_row(AuditLog, row) if row else None


auditLogRepository = AuditLogRepository()
