from typing import Optional
from uuid import UUID

import asyncpg

TRACKED_TABLES = ["pregnancies", "prenatal_controls", "data_imports", "backups", "users"]


class DashboardRepository:
    async def recent_changes(
        self, conn: asyncpg.Connection, limit: int, facility_id: Optional[UUID] = None
    ) -> list[asyncpg.Record]:
        return await conn.fetch(
            """
            SELECT a.id, a.affected_table, a.action, a.record_id, u.full_name AS user_name, a.created_at,
                   COALESCE(a.details -> 'new', a.details -> 'old') AS row
            FROM audit_log a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE a.affected_table = ANY($1::text[]) AND a.action IN ('INSERT', 'UPDATE', 'DELETE')
              AND (
                  $3::uuid IS NULL
                  OR (a.affected_table = 'pregnancies'
                      AND COALESCE(a.details -> 'new', a.details -> 'old') ->> 'health_facility_id' = $3::text)
                  OR (a.affected_table = 'prenatal_controls'
                      AND EXISTS (
                          SELECT 1 FROM pregnancies p
                          WHERE p.id::text = COALESCE(a.details -> 'new', a.details -> 'old') ->> 'pregnancy_id'
                            AND p.health_facility_id = $3
                      ))
              )
            ORDER BY a.created_at DESC
            LIMIT $2
            """,
            TRACKED_TABLES,
            limit,
            facility_id,
        )

    async def pregnancy_codes(self, conn: asyncpg.Connection, ids: list[str]) -> dict[str, str]:
        rows = await conn.fetch("SELECT id::text, code FROM pregnancies WHERE id = ANY($1::uuid[])", ids)
        return {row["id"]: row["code"] for row in rows}

    async def upcoming_appointments(
        self, conn: asyncpg.Connection, days: int, limit: int, facility_id: Optional[UUID] = None
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
              AND ($3::uuid IS NULL OR p.health_facility_id = $3)
            ORDER BY n.next_appointment, p.code
            LIMIT $2
            """,
            days,
            limit,
            facility_id,
        )
        return [dict(row) for row in rows]

    async def due_soon(
        self, conn: asyncpg.Connection, days: int, limit: int, facility_id: Optional[UUID] = None
    ) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT p.id AS pregnancy_id, p.code, p.first_names || ' ' || p.last_names AS full_name,
                   f.name AS health_facility_name, p.expected_delivery_date AS date, p.risk_level::text AS risk_level
            FROM pregnancies p
            JOIN health_facilities f ON f.id = p.health_facility_id
            WHERE p.active AND p.status <> 'completed'
              AND p.expected_delivery_date BETWEEN CURRENT_DATE AND CURRENT_DATE + $1::int
              AND ($3::uuid IS NULL OR p.health_facility_id = $3)
            ORDER BY p.expected_delivery_date, p.code
            LIMIT $2
            """,
            days,
            limit,
            facility_id,
        )
        return [dict(row) for row in rows]


dashboardRepository = DashboardRepository()
