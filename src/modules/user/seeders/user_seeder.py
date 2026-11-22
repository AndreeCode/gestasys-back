from uuid import UUID

import asyncpg

from ....core.security.password import hash_password

USERS = [
    {"username": "admin", "email": "admin@gestasys.pe", "password": "Admin123!", "full_name": "Andrea Morales", "role": "admin", "dni": "45871236"},
    {"username": "coordinador", "email": "coordinador@gestasys.pe", "password": "Coord123!", "full_name": "Carlos Ramirez", "role": "coordinador", "dni": "41239875"},
    {"username": "consulta", "email": "consulta@gestasys.pe", "password": "Consulta123!", "full_name": "Lucia Torres", "role": "consulta", "dni": "47125836"},
]


async def seed_users(conn: asyncpg.Connection, roles: dict[str, UUID]) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for seed in USERS:
        existing = await conn.fetchval("SELECT id FROM users WHERE lower(username) = $1", seed["username"])
        if existing:
            ids[seed["username"]] = existing
            continue
        ids[seed["username"]] = await conn.fetchval(
            """
            INSERT INTO users (username, email, password_hash, role_id, full_name, dni, password_changed_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            RETURNING id
            """,
            seed["username"],
            seed["email"],
            hash_password(seed["password"]),
            roles[seed["role"]],
            seed["full_name"],
            seed["dni"],
        )
    return ids
