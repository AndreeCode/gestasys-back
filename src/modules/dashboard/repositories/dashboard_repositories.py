from typing import Optional
from uuid import UUID

import asyncpg

TRACKED_TABLES = ["pregnancies", "prenatal_controls", "data_imports", "backups", "users"]


class DashboardRepository:
    async def recent_changes(
        self, conn: asyncpg.Connection, limit: int, facility_ids: Optional[list[UUID]] = None
    ) -> list[asyncpg.Record]:
        return await conn.fetch(
            """
            SELECT a.id, a.affected_table, a.action, a.record_id, u.full_name AS user_name, a.created_at,
                   COALESCE(a.details -> 'new', a.details -> 'old') AS row, f.name AS health_facility_name,
                   host(a.ip_address) AS ip_address
            FROM audit_log a
            LEFT JOIN users u ON u.id = a.user_id
            LEFT JOIN health_facilities f ON f.id = a.scope_health_facility_id
            WHERE a.affected_table = ANY($1::text[]) AND a.action IN ('INSERT', 'UPDATE', 'DELETE')
              AND ($3::uuid[] IS NULL OR a.scope_health_facility_id = ANY($3))
            ORDER BY a.created_at DESC
            LIMIT $2
            """,
            TRACKED_TABLES,
            limit,
            facility_ids,
        )

    async def pregnancy_codes(self, conn: asyncpg.Connection, ids: list[str]) -> dict[str, str]:
        rows = await conn.fetch("SELECT id::text, code FROM pregnancies WHERE id = ANY($1::uuid[])", ids)
        return {row["id"]: row["code"] for row in rows}

    async def upcoming_appointments(
        self, conn: asyncpg.Connection, days: int, limit: int, facility_ids: Optional[list[UUID]] = None
    ) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT p.id AS pregnancy_id, p.code, p.first_names || ' ' || p.last_names AS full_name,
                   f.name AS health_facility_name, n.next_appointment AS date, p.risk_level::text AS risk_level
            FROM pregnancies p
            JOIN health_facilities f ON f.id = p.health_facility_id
            JOIN LATERAL (
                SELECT c.next_appointment FROM prenatal_controls c
                WHERE c.pregnancy_id = p.id ORDER BY c.control_date DESC, c.created_at DESC LIMIT 1
            ) n ON TRUE
            WHERE p.active AND p.status <> 'completed'
              AND n.next_appointment BETWEEN CURRENT_DATE AND CURRENT_DATE + $1::int
              AND ($3::uuid[] IS NULL OR p.health_facility_id = ANY($3))
            ORDER BY n.next_appointment, p.code
            LIMIT $2
            """,
            days,
            limit,
            facility_ids,
        )
        return [dict(row) for row in rows]

    async def due_soon(
        self, conn: asyncpg.Connection, days: int, limit: int, facility_ids: Optional[list[UUID]] = None
    ) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT p.id AS pregnancy_id, p.code, p.first_names || ' ' || p.last_names AS full_name,
                   f.name AS health_facility_name, p.expected_delivery_date AS date, p.risk_level::text AS risk_level
            FROM pregnancies p
            JOIN health_facilities f ON f.id = p.health_facility_id
            WHERE p.active AND p.status <> 'completed'
              AND p.expected_delivery_date BETWEEN CURRENT_DATE AND CURRENT_DATE + $1::int
              AND ($3::uuid[] IS NULL OR p.health_facility_id = ANY($3))
            ORDER BY p.expected_delivery_date, p.code
            LIMIT $2
            """,
            days,
            limit,
            facility_ids,
        )
        return [dict(row) for row in rows]


    async def scope_names(self, conn: asyncpg.Connection, facility_id: Optional[UUID], network_id: Optional[UUID]) -> dict:
        row = await conn.fetchrow(
            """
            SELECT (SELECT name FROM health_facilities WHERE id = $1) AS health_facility_name,
                   (SELECT name FROM micro_networks
                    WHERE id = COALESCE($2, (SELECT micro_network_id FROM health_facilities WHERE id = $1)))
                       AS micro_network_name,
                   (SELECT count(*) FROM users WHERE active AND (
                        ($1::uuid IS NULL AND $2::uuid IS NULL)
                        OR health_facility_id = $1
                        OR ($2::uuid IS NOT NULL AND (micro_network_id = $2 OR health_facility_id IN (
                            SELECT id FROM health_facilities WHERE micro_network_id = $2)))
                   ))::int AS active_users
            """,
            facility_id,
            network_id,
        )
        return dict(row)

    async def auth_summary(self, conn: asyncpg.Connection) -> dict:
        row = await conn.fetchrow(
            """
            SELECT
                (SELECT count(*) FROM audit_log
                 WHERE action = 'LOGIN_FAILED' AND created_at >= NOW() - INTERVAL '24 hours') AS failed_logins_24h,
                (SELECT count(*) FROM users WHERE locked_until > NOW()) AS locked_accounts
            """
        )
        return dict(row)


dashboardRepository = DashboardRepository()
