from datetime import date
from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.pregnancy_domain import Pregnancy, PregnancyFilter

SELECT_PREGNANCY = """
SELECT p.id, p.code, p.dni, p.first_names, p.last_names, p.birth_date,
       date_part('year', age(p.birth_date))::int AS age,
       p.phone, p.address, p.health_facility_id, f.name AS health_facility_name,
       f.micro_network_id, mn.name AS micro_network_name,
       p.clinical_record, p.insurance, p.province, p.district, p.locality, p.obstetric_formula,
       p.birth_date_estimated, p.clinical_data, p.row_color, p.cell_marks, p.source, p.import_id, ru.full_name AS registered_by_name,
       p.last_menstrual_period, p.expected_delivery_date,
       CASE WHEN p.last_menstrual_period IS NOT NULL AND p.status <> 'completed'
            THEN (CURRENT_DATE - p.last_menstrual_period) END AS ga_days,
       p.gravida, p.parity, p.risk_level::text AS risk_level, p.status::text AS status, p.delivery_date,
       p.notes, p.registered_by, p.active,
       c.last_control AS last_control_date, COALESCE(c.total, 0)::int AS controls_count,
       c.next_appointment, GREATEST(p.updated_at, COALESCE(c.last_change, p.updated_at)) AS last_activity_at,
       p.created_at, p.updated_at
FROM pregnancies p
JOIN health_facilities f ON f.id = p.health_facility_id
LEFT JOIN micro_networks mn ON mn.id = f.micro_network_id
LEFT JOIN users ru ON ru.id = p.registered_by
LEFT JOIN LATERAL (
    SELECT max(pc.control_date) AS last_control, count(*) AS total,
           min(pc.next_appointment) FILTER (WHERE pc.next_appointment >= CURRENT_DATE) AS next_appointment,
           max(pc.updated_at) AS last_change
    FROM prenatal_controls pc WHERE pc.pregnancy_id = p.id
) c ON TRUE
"""

FILTER_WHERE = """
WHERE ($1::text IS NULL OR p.code ILIKE '%' || $1 || '%' OR p.dni = $1
       OR (p.first_names || ' ' || p.last_names) ILIKE '%' || $1 || '%'
       OR (p.last_names || ' ' || p.first_names) ILIKE '%' || $1 || '%')
  AND ($2::uuid[] IS NULL OR p.health_facility_id = ANY($2))
  AND ($3::text IS NULL OR p.status::text = $3)
  AND ($4::text IS NULL OR p.risk_level::text = $4)
  AND ($5::bool IS NULL OR p.active = $5)
  AND ($6::date IS NULL OR p.expected_delivery_date >= $6)
  AND ($7::date IS NULL OR p.expected_delivery_date <= $7)
  AND ($8::text IS NULL OR ($8 = 'none' AND p.row_color IS NULL) OR ($8 = 'any' AND p.row_color IS NOT NULL)
       OR p.row_color = upper($8))
"""


def pct(part: int, total: int) -> float:
    return round(part * 100 / total, 1) if total else 0.0


class PregnancyRepository:
    async def get_all(self, conn: asyncpg.Connection, f: PregnancyFilter, limit: int, offset: int) -> tuple[list[Pregnancy], int]:
        total = await conn.fetchval("SELECT count(*) FROM pregnancies p" + FILTER_WHERE, *f.args())
        rows = await conn.fetch(
            SELECT_PREGNANCY + FILTER_WHERE + " ORDER BY p.created_at DESC, p.code DESC LIMIT $9 OFFSET $10",
            *f.args(),
            limit,
            offset,
        )
        return [from_row(Pregnancy, row) for row in rows], total

    async def get_all_unpaged(self, conn: asyncpg.Connection, f: PregnancyFilter) -> list[Pregnancy]:
        rows = await conn.fetch(SELECT_PREGNANCY + FILTER_WHERE + " ORDER BY p.code", *f.args())
        return [from_row(Pregnancy, row) for row in rows]

    async def get_by_id(self, conn: asyncpg.Connection, pregnancy_id: UUID) -> Optional[Pregnancy]:
        row = await conn.fetchrow(SELECT_PREGNANCY + " WHERE p.id = $1", pregnancy_id)
        return from_row(Pregnancy, row) if row else None

    async def get_by_code(self, conn: asyncpg.Connection, code: str) -> Optional[Pregnancy]:
        row = await conn.fetchrow(SELECT_PREGNANCY + " WHERE upper(p.code) = upper($1)", code)
        return from_row(Pregnancy, row) if row else None

    async def get_open_by_dni(self, conn: asyncpg.Connection, dni: str) -> Optional[Pregnancy]:
        row = await conn.fetchrow(
            SELECT_PREGNANCY + " WHERE p.dni = $1 AND p.active AND p.status <> 'completed'", dni
        )
        return from_row(Pregnancy, row) if row else None

    async def next_code(self, conn: asyncpg.Connection, year: int) -> str:
        n = await conn.fetchval(
            """
            INSERT INTO record_counters (year, last_value) VALUES ($1, 1)
            ON CONFLICT (year) DO UPDATE SET last_value = record_counters.last_value + 1
            RETURNING last_value
            """,
            year,
        )
        return f"EMB-{year}-{n:05d}"

    async def create(self, conn: asyncpg.Connection, p: Pregnancy) -> UUID:
        p.code = await self.next_code(conn, date.today().year)
        return await conn.fetchval(
            """
            INSERT INTO pregnancies (code, dni, first_names, last_names, birth_date, phone, address, health_facility_id,
                                     last_menstrual_period, expected_delivery_date, gravida, parity, risk_level, status,
                                     delivery_date, notes, registered_by, clinical_record, insurance, province, district,
                                     locality, obstetric_formula, birth_date_estimated, clinical_data, row_color,
                                     cell_marks, source, import_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::risk_level, $14::pregnancy_status,
                    $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25::jsonb, $26, $27::jsonb, $28, $29)
            RETURNING id
            """,
            p.code, p.dni, p.first_names, p.last_names, p.birth_date, p.phone, p.address, p.health_facility_id,
            p.last_menstrual_period, p.expected_delivery_date, p.gravida, p.parity, p.risk_level, p.status,
            p.delivery_date, p.notes, p.registered_by, *self._extra(p), p.source, p.import_id,
        )

    def _extra(self, p: Pregnancy) -> list:
        return [
            p.clinical_record, p.insurance, p.province, p.district, p.locality, p.obstetric_formula,
            p.birth_date_estimated, p.clinical_data if p.clinical_data is not None else [],
            p.row_color, p.cell_marks if p.cell_marks is not None else {},
        ]

    async def update(self, conn: asyncpg.Connection, p: Pregnancy) -> None:
        await conn.execute(
            """
            UPDATE pregnancies SET dni = $2, first_names = $3, last_names = $4, birth_date = $5, phone = $6,
                   address = $7, health_facility_id = $8, last_menstrual_period = $9, expected_delivery_date = $10,
                   gravida = $11, parity = $12, risk_level = $13::risk_level, status = $14::pregnancy_status,
                   delivery_date = $15, notes = $16, active = $17, clinical_record = $18, insurance = $19,
                   province = $20, district = $21, locality = $22, obstetric_formula = $23,
                   birth_date_estimated = $24, clinical_data = $25::jsonb, row_color = $26, cell_marks = $27::jsonb,
                   import_id = COALESCE($28, import_id)
            WHERE id = $1
            """,
            p.id, p.dni, p.first_names, p.last_names, p.birth_date, p.phone, p.address, p.health_facility_id,
            p.last_menstrual_period, p.expected_delivery_date, p.gravida, p.parity, p.risk_level, p.status,
            p.delivery_date, p.notes, p.active, *self._extra(p), p.import_id,
        )

    async def set_status(self, conn: asyncpg.Connection, pregnancy_id: UUID, status: str) -> None:
        await conn.execute("UPDATE pregnancies SET status = $2::pregnancy_status WHERE id = $1", pregnancy_id, status)

    async def deactivate(self, conn: asyncpg.Connection, pregnancy_id: UUID) -> None:
        await conn.execute("UPDATE pregnancies SET active = FALSE WHERE id = $1", pregnancy_id)

    async def stats(
        self, conn: asyncpg.Connection, facility_ids: Optional[list[UUID]], registered_by: Optional[UUID] = None
    ) -> dict:
        row = await conn.fetchrow(
            """
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE status = 'in_followup') AS in_followup,
                   count(*) FILTER (WHERE status = 'pending') AS pending,
                   count(*) FILTER (WHERE status = 'completed') AS completed,
                   count(*) FILTER (WHERE risk_level = 'high' AND status <> 'completed') AS high_risk,
                   count(*) FILTER (WHERE created_at >= date_trunc('month', NOW())) AS new_this_month,
                   count(*) FILTER (WHERE created_at >= date_trunc('month', NOW()) - INTERVAL '1 month'
                                      AND created_at < date_trunc('month', NOW())) AS new_last_month,
                   count(*) FILTER (WHERE created_at < date_trunc('month', NOW())) AS total_prev_month,
                   count(*) FILTER (WHERE status = 'pending' AND created_at >= NOW() - INTERVAL '7 days') AS new_pending_week,
                   count(*) FILTER (WHERE status <> 'completed'
                                      AND expected_delivery_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 30) AS due_next_30_days
            FROM pregnancies
            WHERE active AND ($1::uuid[] IS NULL OR health_facility_id = ANY($1))
              AND ($2::uuid IS NULL OR registered_by = $2)
            """,
            facility_ids,
            registered_by,
        )
        s = dict(row)
        prev = s["total_prev_month"]
        s["growth_percent"] = pct(s["total"] - prev, prev) if prev else 0.0
        s["in_followup_percent"] = pct(s["in_followup"], s["total"])
        s["completed_percent"] = pct(s["completed"], s["total"])
        s["pending_percent"] = pct(s["pending"], s["total"])
        return s

    async def by_facility(self, conn: asyncpg.Connection, facility_ids: Optional[list[UUID]] = None) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT f.id AS health_facility_id, f.name AS health_facility_name, mn.name AS micro_network_name,
                   count(p.id)::int AS total,
                   count(p.id) FILTER (WHERE p.risk_level = 'high' AND p.status <> 'completed')::int AS high_risk,
                   count(p.id) FILTER (WHERE p.status = 'in_followup')::int AS in_followup,
                   count(p.id) FILTER (WHERE p.status = 'pending')::int AS pending,
                   count(p.id) FILTER (WHERE p.status = 'completed')::int AS completed
            FROM health_facilities f
            LEFT JOIN micro_networks mn ON mn.id = f.micro_network_id
            LEFT JOIN pregnancies p ON p.health_facility_id = f.id AND p.active
            WHERE f.active AND ($1::uuid[] IS NULL OR f.id = ANY($1))
            GROUP BY f.id, f.name, mn.name
            ORDER BY count(p.id) DESC, f.name
            """,
            facility_ids,
        )
        return [dict(row) for row in rows]

    async def by_micro_network(self, conn: asyncpg.Connection) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT mn.id AS micro_network_id, COALESCE(mn.name, 'Sin microred') AS micro_network_name,
                   count(DISTINCT f.id)::int AS facilities,
                   count(p.id)::int AS total,
                   count(p.id) FILTER (WHERE p.status = 'in_followup')::int AS in_followup,
                   count(p.id) FILTER (WHERE p.status = 'pending')::int AS pending,
                   count(p.id) FILTER (WHERE p.status = 'completed')::int AS completed,
                   count(p.id) FILTER (WHERE p.risk_level = 'high' AND p.status <> 'completed')::int AS high_risk
            FROM health_facilities f
            LEFT JOIN micro_networks mn ON mn.id = f.micro_network_id
            LEFT JOIN pregnancies p ON p.health_facility_id = f.id AND p.active
            WHERE f.active
            GROUP BY mn.id, mn.name
            ORDER BY count(p.id) DESC, mn.name
            """
        )
        return [dict(row) for row in rows]

    async def by_registrar(self, conn: asyncpg.Connection, facility_ids: Optional[list[UUID]], limit: int = 10) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT u.id AS user_id, u.full_name, r.name AS role, f.name AS health_facility_name,
                   count(p.id)::int AS total,
                   count(p.id) FILTER (WHERE p.created_at >= date_trunc('month', NOW()))::int AS this_month,
                   (SELECT count(*) FROM prenatal_controls c
                    JOIN pregnancies cp ON cp.id = c.pregnancy_id
                    WHERE c.registered_by = u.id AND cp.active
                      AND ($1::uuid[] IS NULL OR cp.health_facility_id = ANY($1)))::int AS controls
            FROM pregnancies p
            JOIN users u ON u.id = p.registered_by
            JOIN roles r ON r.id = u.role_id
            LEFT JOIN health_facilities f ON f.id = u.health_facility_id
            WHERE p.active AND ($1::uuid[] IS NULL OR p.health_facility_id = ANY($1))
            GROUP BY u.id, u.full_name, r.name, f.name
            ORDER BY count(p.id) DESC
            LIMIT $2
            """,
            facility_ids,
            limit,
        )
        return [dict(row) for row in rows]

    async def by_month(self, conn: asyncpg.Connection, facility_ids: Optional[list[UUID]], months: int = 6) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT to_char(m, 'YYYY-MM') AS month,
                   (SELECT count(*) FROM pregnancies p
                    WHERE p.active AND date_trunc('month', p.created_at) = m
                      AND ($1::uuid[] IS NULL OR p.health_facility_id = ANY($1)))::int AS registered,
                   (SELECT count(*) FROM prenatal_controls c JOIN pregnancies p ON p.id = c.pregnancy_id
                    WHERE p.active AND date_trunc('month', c.control_date) = m
                      AND ($1::uuid[] IS NULL OR p.health_facility_id = ANY($1)))::int AS controls
            FROM generate_series(date_trunc('month', NOW()) - make_interval(months => $2 - 1),
                                 date_trunc('month', NOW()), INTERVAL '1 month') AS m
            ORDER BY m
            """,
            facility_ids,
            months,
        )
        return [dict(row) for row in rows]

    async def find_for_import(
        self, conn: asyncpg.Connection, dni: Optional[str], facility_id: UUID, clinical_record: Optional[str],
        first_names: str, last_names: str,
    ) -> Optional[Pregnancy]:
        if dni:
            row = await conn.fetchrow(
                SELECT_PREGNANCY + " WHERE p.dni = $1 AND p.active ORDER BY p.created_at DESC LIMIT 1", dni
            )
            if row:
                return from_row(Pregnancy, row)
        if clinical_record:
            row = await conn.fetchrow(
                SELECT_PREGNANCY
                + " WHERE p.health_facility_id = $1 AND p.clinical_record = $2 AND p.active ORDER BY p.created_at DESC LIMIT 1",
                facility_id,
                clinical_record,
            )
            if row:
                return from_row(Pregnancy, row)
        row = await conn.fetchrow(
            SELECT_PREGNANCY
            + """
            WHERE p.health_facility_id = $1 AND lower(p.first_names) = lower($2) AND lower(p.last_names) = lower($3)
              AND p.active
            ORDER BY p.created_at DESC LIMIT 1
            """,
            facility_id,
            first_names,
            last_names,
        )
        return from_row(Pregnancy, row) if row else None


pregnancyRepository = PregnancyRepository()
