from datetime import date
from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.prenatal_control_domain import PrenatalControl

SELECT_CONTROL = """
SELECT c.id, c.pregnancy_id, p.code AS pregnancy_code, p.first_names || ' ' || p.last_names AS pregnant_name,
       c.control_date, c.gestational_weeks::float8 AS gestational_weeks, c.weight_kg::float8 AS weight_kg,
       c.systolic_bp, c.diastolic_bp, c.fetal_heart_rate, c.uterine_height_cm::float8 AS uterine_height_cm,
       c.hemoglobin::float8 AS hemoglobin, c.next_appointment, c.notes, c.registered_by, c.created_at, c.updated_at
FROM prenatal_controls c
JOIN pregnancies p ON p.id = c.pregnancy_id
"""

VALUES = (
    "control_date", "gestational_weeks", "weight_kg", "systolic_bp", "diastolic_bp", "fetal_heart_rate",
    "uterine_height_cm", "hemoglobin", "next_appointment", "notes",
)


class PrenatalControlRepository:
    async def get_all(
        self, conn: asyncpg.Connection, pregnancy_id: Optional[UUID], date_from: Optional[date], date_to: Optional[date]
    ) -> list[PrenatalControl]:
        rows = await conn.fetch(
            SELECT_CONTROL
            + """
            WHERE p.active AND ($1::uuid IS NULL OR c.pregnancy_id = $1)
              AND ($2::date IS NULL OR c.control_date >= $2) AND ($3::date IS NULL OR c.control_date <= $3)
            ORDER BY c.control_date DESC, c.created_at DESC
            """,
            pregnancy_id,
            date_from,
            date_to,
        )
        return [from_row(PrenatalControl, row) for row in rows]

    async def get_by_id(self, conn: asyncpg.Connection, control_id: UUID) -> Optional[PrenatalControl]:
        row = await conn.fetchrow(SELECT_CONTROL + " WHERE c.id = $1", control_id)
        return from_row(PrenatalControl, row) if row else None

    async def create(self, conn: asyncpg.Connection, c: PrenatalControl) -> UUID:
        return await conn.fetchval(
            """
            INSERT INTO prenatal_controls (pregnancy_id, control_date, gestational_weeks, weight_kg, systolic_bp,
                                           diastolic_bp, fetal_heart_rate, uterine_height_cm, hemoglobin,
                                           next_appointment, notes, registered_by)
            VALUES ($1, $2, $3::float8, $4::float8, $5, $6, $7, $8::float8, $9::float8, $10, $11, $12) RETURNING id
            """,
            c.pregnancy_id,
            *(getattr(c, key) for key in VALUES),
            c.registered_by,
        )

    async def update(self, conn: asyncpg.Connection, c: PrenatalControl) -> None:
        await conn.execute(
            """
            UPDATE prenatal_controls SET control_date = $2, gestational_weeks = $3::float8, weight_kg = $4::float8, systolic_bp = $5,
                   diastolic_bp = $6, fetal_heart_rate = $7, uterine_height_cm = $8::float8, hemoglobin = $9::float8,
                   next_appointment = $10, notes = $11
            WHERE id = $1
            """,
            c.id,
            *(getattr(c, key) for key in VALUES),
        )

    async def delete(self, conn: asyncpg.Connection, control_id: UUID) -> None:
        await conn.execute("DELETE FROM prenatal_controls WHERE id = $1", control_id)


prenatalControlRepository = PrenatalControlRepository()
