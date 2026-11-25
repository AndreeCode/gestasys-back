from uuid import UUID

import asyncpg

MICRO_NETWORKS = [
    ("MR-BELEN", "Microred Belen"),
    ("MR-SAN-JUAN-BAUTISTA", "Microred San Juan Bautista"),
]

FACILITIES = [
    ("CS-SANMARTIN", "C.S. San Martin", "Centro de Salud", "Ayacucho", "MR-BELEN"),
    ("CS-SANTAROSA", "C.S. Santa Rosa", "Centro de Salud", "Ayacucho", "MR-BELEN"),
    ("PS-ELCARMEN", "P.S. El Carmen", "Puesto de Salud", "Carmen Alto", "MR-BELEN"),
    ("CS-SANJUAN", "C.S. San Juan Bautista", "Centro de Salud", "San Juan Bautista", "MR-SAN-JUAN-BAUTISTA"),
    ("HR-AYACUCHO", "H. Regional de Ayacucho", "Hospital", "Ayacucho", "MR-SAN-JUAN-BAUTISTA"),
]


async def seed_micro_networks(conn: asyncpg.Connection) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for code, name in MICRO_NETWORKS:
        existing = await conn.fetchval("SELECT id FROM micro_networks WHERE code = $1", code)
        if existing is None:
            existing = await conn.fetchval(
                "INSERT INTO micro_networks (code, name) VALUES ($1, $2) RETURNING id", code, name
            )
        ids[code] = existing
    return ids


async def seed_health_facilities(conn: asyncpg.Connection, networks: dict[str, UUID]) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for code, name, category, district, network in FACILITIES:
        existing = await conn.fetchval("SELECT id FROM health_facilities WHERE code = $1", code)
        if existing is None:
            existing = await conn.fetchval(
                """
                INSERT INTO health_facilities (code, name, category, district, province, micro_network_id)
                VALUES ($1, $2, $3, $4, 'Huamanga', $5) RETURNING id
                """,
                code,
                name,
                category,
                district,
                networks[network],
            )
        else:
            await conn.execute(
                "UPDATE health_facilities SET micro_network_id = COALESCE(micro_network_id, $2) WHERE id = $1",
                existing,
                networks[network],
            )
        ids[code] = existing
    return ids
