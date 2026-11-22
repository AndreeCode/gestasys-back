from uuid import UUID

import asyncpg

FACILITIES = [
    ("CS-SANMARTIN", "C.S. San Martin", "Centro de Salud", "Ayacucho"),
    ("CS-SANTAROSA", "C.S. Santa Rosa", "Centro de Salud", "Ayacucho"),
    ("PS-ELCARMEN", "P.S. El Carmen", "Puesto de Salud", "Carmen Alto"),
    ("CS-SANJUAN", "C.S. San Juan Bautista", "Centro de Salud", "San Juan Bautista"),
    ("HR-AYACUCHO", "H. Regional de Ayacucho", "Hospital", "Ayacucho"),
]


async def seed_health_facilities(conn: asyncpg.Connection) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for code, name, category, district in FACILITIES:
        existing = await conn.fetchval("SELECT id FROM health_facilities WHERE code = $1", code)
        if existing is None:
            existing = await conn.fetchval(
                "INSERT INTO health_facilities (code, name, category, district) VALUES ($1, $2, $3, $4) RETURNING id",
                code,
                name,
                category,
                district,
            )
        ids[code] = existing
    return ids
