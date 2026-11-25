from typing import Optional
from uuid import UUID

import asyncpg

SECTIONS = {
    "exams": "%examenes auxiliares%",
    "ultrasound": "%ecograf%",
    "dental": "%odontol%",
    "vif": "%tamizaje vif%",
    "vaccines": "%vacuna%",
    "birth_plan": "%plan de parto%",
}

BASE = """
WITH base AS (
    SELECT p.id, p.health_facility_id, p.status::text AS status, p.risk_level::text AS risk_level,
           date_part('year', age(p.birth_date))::int AS age, p.clinical_data, p.created_at,
           COALESCE(c.total, 0) AS total, c.first_weeks, c.last_next, COALESCE(c.supp, 0) AS supp
    FROM pregnancies p
    LEFT JOIN LATERAL (
        SELECT count(*) AS total,
               (array_agg(COALESCE(pc.gestational_weeks::float8,
                                   (pc.control_date - p.last_menstrual_period) / 7.0)
                          ORDER BY pc.control_date))[1] AS first_weeks,
               (array_agg(pc.next_appointment ORDER BY pc.control_date DESC, pc.created_at DESC))[1] AS last_next,
               count(*) FILTER (WHERE pc.supplementation IS NOT NULL) AS supp
        FROM prenatal_controls pc WHERE pc.pregnancy_id = p.id
    ) c ON TRUE
    WHERE p.active AND ($1::uuid[] IS NULL OR p.health_facility_id = ANY($1))
)
"""


def has_section(pattern_param: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM jsonb_array_elements(base.clinical_data) s "
        f"WHERE s ->> 'section' ILIKE {pattern_param} AND jsonb_array_length(COALESCE(s -> 'items', '[]'::jsonb)) > 0)"
    )


METRICS = f"""
    count(*)::int AS total,
    count(*) FILTER (WHERE total > 0)::int AS with_controls,
    count(*) FILTER (WHERE total > 0 AND first_weeks < 14)::int AS early_capture,
    count(*) FILTER (WHERE total >= 6)::int AS six_apn,
    count(*) FILTER (WHERE status = 'completed')::int AS completed,
    count(*) FILTER (WHERE status = 'completed' AND total >= 6)::int AS completed_six_apn,
    count(*) FILTER (WHERE status <> 'completed')::int AS active,
    count(*) FILTER (WHERE status <> 'completed' AND last_next < CURRENT_DATE)::int AS missed,
    count(*) FILTER (WHERE supp > 0)::int AS supplemented,
    count(*) FILTER (WHERE {has_section('$2')})::int AS exams,
    count(*) FILTER (WHERE {has_section('$3')})::int AS ultrasound,
    count(*) FILTER (WHERE {has_section('$4')})::int AS dental,
    count(*) FILTER (WHERE {has_section('$5')})::int AS vif,
    count(*) FILTER (WHERE {has_section('$6')})::int AS vaccines,
    count(*) FILTER (WHERE {has_section('$7')})::int AS birth_plan,
    count(*) FILTER (WHERE risk_level = 'high')::int AS risk_high,
    count(*) FILTER (WHERE risk_level = 'medium')::int AS risk_medium,
    count(*) FILTER (WHERE risk_level = 'low')::int AS risk_low,
    count(*) FILTER (WHERE status = 'pending')::int AS status_pending,
    count(*) FILTER (WHERE status = 'in_followup')::int AS status_followup,
    count(*) FILTER (WHERE age < 18)::int AS age_teen,
    count(*) FILTER (WHERE age BETWEEN 18 AND 35)::int AS age_adult,
    count(*) FILTER (WHERE age > 35)::int AS age_older,
    COALESCE(round(avg(total)::numeric, 1), 0)::float8 AS avg_controls
"""


class ReportRepository:
    def _args(self, facility_ids: Optional[list[UUID]]) -> list:
        return [facility_ids, *SECTIONS.values()]

    async def summary(self, conn: asyncpg.Connection, facility_ids: Optional[list[UUID]]) -> dict:
        row = await conn.fetchrow(BASE + f"SELECT {METRICS} FROM base", *self._args(facility_ids))
        return dict(row)

    async def by_facility(self, conn: asyncpg.Connection, facility_ids: Optional[list[UUID]]) -> list[dict]:
        rows = await conn.fetch(
            BASE
            + f"""
            SELECT f.id AS health_facility_id, f.name AS health_facility_name, mn.name AS micro_network_name, {METRICS}
            FROM base
            JOIN health_facilities f ON f.id = base.health_facility_id
            LEFT JOIN micro_networks mn ON mn.id = f.micro_network_id
            GROUP BY f.id, f.name, mn.name
            ORDER BY count(*) DESC, f.name
            """,
            *self._args(facility_ids),
        )
        return [dict(r) for r in rows]

    async def facilities_of_network(self, conn: asyncpg.Connection, network_id: UUID) -> list[UUID]:
        return [r["id"] for r in await conn.fetch("SELECT id FROM health_facilities WHERE micro_network_id = $1", network_id)]

    async def options(self, conn: asyncpg.Connection, facility_ids: Optional[list[UUID]]) -> dict:
        facilities = await conn.fetch(
            """
            SELECT f.id, f.name, f.micro_network_id FROM health_facilities f
            WHERE f.active AND ($1::uuid[] IS NULL OR f.id = ANY($1)) ORDER BY f.name
            """,
            facility_ids,
        )
        networks = await conn.fetch(
            """
            SELECT DISTINCT m.id, m.name FROM micro_networks m JOIN health_facilities f ON f.micro_network_id = m.id
            WHERE m.active AND ($1::uuid[] IS NULL OR f.id = ANY($1)) ORDER BY m.name
            """,
            facility_ids,
        )
        return {"networks": [dict(n) for n in networks], "facilities": [dict(f) for f in facilities]}


reportRepository = ReportRepository()
