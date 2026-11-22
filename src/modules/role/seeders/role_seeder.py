from uuid import UUID

import asyncpg

from ...permission.domain.permission_catalog import SYSTEM_ROLES


async def seed_roles(conn: asyncpg.Connection) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for seed in SYSTEM_ROLES:
        role_id = await conn.fetchval(
            """
            INSERT INTO roles (name, description, is_system, is_active) VALUES ($1, $2, TRUE, TRUE)
            ON CONFLICT (name) DO UPDATE SET is_system = TRUE
            RETURNING id
            """,
            seed["name"],
            seed["description"],
        )
        ids[seed["name"]] = role_id
        await conn.execute(
            """
            INSERT INTO role_permission (role_id, permission_id)
            SELECT $1::uuid, id FROM permissions WHERE code = ANY($2::text[])
            ON CONFLICT DO NOTHING
            """,
            role_id,
            seed["codes"],
        )
    return ids
