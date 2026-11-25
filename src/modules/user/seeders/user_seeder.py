from uuid import UUID

import asyncpg

from ....core.config.config import config
from ....core.security.password import generate_password, hash_password

USERS = [
    {
        "username": "superadmin", "email": "superadmin@gestasys.pe", "password": "Gestasys-Red-2026",
        "full_name": "Andrea Morales", "role": "superadmin", "dni": "72451836",
    },
    {
        "username": "admin.belen", "email": "admin.belen@gestasys.pe", "password": "Microred-Belen-2026",
        "full_name": "Carlos Ramirez", "role": "admin", "dni": "73318429", "micro_network": "MR-BELEN",
    },
    {
        "username": "admin.sanjuan", "email": "admin.sanjuan@gestasys.pe", "password": "Microred-SanJuan-2026",
        "full_name": "Rosa Huaman", "role": "admin", "dni": "74126503", "micro_network": "MR-SAN-JUAN-BAUTISTA",
    },
    {
        "username": "registrador.belen", "email": "registrador.belen@gestasys.pe", "password": "Registro-SanMartin-2026",
        "full_name": "Lucia Torres", "role": "registrador", "dni": "75830214", "facility": "CS-SANMARTIN",
    },
    {
        "username": "registrador.sanjuan", "email": "registrador.sanjuan@gestasys.pe", "password": "Registro-SanJuan-2026",
        "full_name": "Miguel Quispe", "role": "registrador", "dni": "76219457", "facility": "CS-SANJUAN",
    },
]


async def seed_users(
    conn: asyncpg.Connection, roles: dict[str, UUID], networks: dict[str, UUID], facilities: dict[str, UUID]
) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for seed in USERS:
        existing = await conn.fetchval("SELECT id FROM users WHERE lower(username) = $1", seed["username"])
        if existing:
            ids[seed["username"]] = existing
            continue
        password = generate_password() if config.is_production else seed["password"]
        ids[seed["username"]] = await conn.fetchval(
            """
            INSERT INTO users (username, email, password_hash, role_id, full_name, dni, password_changed_at,
                               must_change_password, micro_network_id, health_facility_id)
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7, $8, $9)
            RETURNING id
            """,
            seed["username"],
            seed["email"],
            hash_password(password),
            roles[seed["role"]],
            seed["full_name"],
            seed["dni"],
            config.is_production,
            networks.get(seed.get("micro_network", "")),
            facilities.get(seed.get("facility", "")),
        )
        if config.is_production:
            print(f"  usuario {seed['username']}: contrasena temporal {password} (se pide cambiarla al ingresar)")
    return ids
