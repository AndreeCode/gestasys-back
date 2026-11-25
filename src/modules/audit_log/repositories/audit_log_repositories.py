from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.audit_log_domain import AuditLog, AuditLogFilter

SELECT_LOG = """
SELECT a.id, a.user_id, u.full_name AS user_name, r.name AS user_role, a.device_id, a.action, a.affected_table,
       a.record_id, a.record_key, host(a.ip_address) AS ip_address, a.user_agent, a.result::text AS result, a.details,
       a.created_at,
       COALESCE(a.details -> 'new' ->> 'code', a.details -> 'old' ->> 'code',
                a.details -> 'new' ->> 'file_name', a.details -> 'new' ->> 'full_name',
                a.details -> 'old' ->> 'full_name', a.details -> 'new' ->> 'name', a.details -> 'old' ->> 'name',
                to_char((COALESCE(a.details -> 'new', a.details -> 'old') ->> 'control_date')::date, 'DD/MM/YYYY'))
           AS record_label,
       a.scope_health_facility_id AS health_facility_id, f.name AS health_facility_name,
       a.scope_micro_network_id AS micro_network_id, mn.name AS micro_network_name,
       af.name AS actor_health_facility_name
FROM audit_log a
LEFT JOIN users u ON u.id = a.user_id
LEFT JOIN roles r ON r.id = u.role_id
LEFT JOIN health_facilities f ON f.id = a.scope_health_facility_id
LEFT JOIN micro_networks mn ON mn.id = a.scope_micro_network_id
LEFT JOIN health_facilities af ON af.id = audit_jsonb_uuid(a.details, 'actor_health_facility_id')
"""

WHERE = """
WHERE ($1::uuid IS NULL OR a.user_id = $1)
  AND ($2::text IS NULL OR a.affected_table = $2)
  AND ($3::uuid IS NULL OR a.record_id = $3)
  AND ($4::text IS NULL OR a.action = upper($4))
  AND ($5::text IS NULL OR a.result::text = $5)
  AND ($6::date IS NULL OR a.created_at >= $6::date)
  AND ($7::date IS NULL OR a.created_at < $7::date + 1)
  AND ($8::text IS NULL OR host(a.ip_address) = $8
       OR a.user_id IN (SELECT id FROM users WHERE full_name ILIKE '%' || $8 || '%' OR username ILIKE '%' || $8 || '%')
       OR a.details -> 'new' ->> 'code' ILIKE '%' || $8 || '%' OR a.details -> 'old' ->> 'code' ILIKE '%' || $8 || '%')
  AND (($9::uuid[] IS NULL AND $10::uuid IS NULL)
       OR a.scope_health_facility_id = ANY($9)
       OR ($10::uuid IS NOT NULL AND a.scope_micro_network_id = $10))
"""

HISTORY = """
WHERE (a.affected_table = 'pregnancies' AND a.record_id = $1)
   OR (a.affected_table = 'prenatal_controls'
       AND COALESCE(a.details -> 'new', a.details -> 'old') ->> 'pregnancy_id' = $1::text)
ORDER BY a.created_at DESC
LIMIT 200
"""


class AuditLogRepository:
    async def get_all(self, conn: asyncpg.Connection, f: AuditLogFilter, limit: int, offset: int) -> tuple[list[AuditLog], int]:
        total = await conn.fetchval("SELECT count(*) FROM audit_log a" + WHERE, *f.args())
        rows = await conn.fetch(SELECT_LOG + WHERE + " ORDER BY a.created_at DESC LIMIT $11 OFFSET $12", *f.args(), limit, offset)
        return [from_row(AuditLog, row) for row in rows], total

    async def get_by_id(self, conn: asyncpg.Connection, log_id: UUID) -> Optional[AuditLog]:
        row = await conn.fetchrow(SELECT_LOG + " WHERE a.id = $1", log_id)
        return from_row(AuditLog, row) if row else None

    async def record_history(self, conn: asyncpg.Connection, pregnancy_id: UUID) -> list[AuditLog]:
        rows = await conn.fetch(SELECT_LOG + HISTORY, pregnancy_id)
        return [from_row(AuditLog, row) for row in rows]


auditLogRepository = AuditLogRepository()
