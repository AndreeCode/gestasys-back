from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.role_domain import Role

SELECT_ROLE = """
SELECT r.id, r.name, r.description, r.is_system, r.is_active,
       ARRAY(SELECT rp.permission_id FROM role_permission rp JOIN permissions p ON p.id = rp.permission_id
             WHERE rp.role_id = r.id ORDER BY p.code) AS permission_ids,
       ARRAY(SELECT p.code FROM role_permission rp JOIN permissions p ON p.id = rp.permission_id
             WHERE rp.role_id = r.id ORDER BY p.code) AS permissions,
       (SELECT count(*) FROM users u WHERE u.role_id = r.id AND u.active)::int AS user_count,
       r.created_at, r.updated_at
FROM roles r
"""


class RoleRepository:
    async def get_all(self, conn: asyncpg.Connection, active: Optional[bool]) -> list[Role]:
        rows = await conn.fetch(
            SELECT_ROLE + " WHERE ($1::bool IS NULL OR r.is_active = $1) ORDER BY r.is_system DESC, r.name", active
        )
        return [from_row(Role, row) for row in rows]

    async def get_by_id(self, conn: asyncpg.Connection, role_id: UUID) -> Optional[Role]:
        row = await conn.fetchrow(SELECT_ROLE + " WHERE r.id = $1", role_id)
        return from_row(Role, row) if row else None

    async def create(self, conn: asyncpg.Connection, role: Role) -> UUID:
        return await conn.fetchval(
            "INSERT INTO roles (name, description, is_system, is_active) VALUES ($1, $2, $3, $4) RETURNING id",
            role.name,
            role.description,
            role.is_system,
            role.is_active,
        )

    async def update(self, conn: asyncpg.Connection, role: Role) -> None:
        await conn.execute(
            "UPDATE roles SET name = $2, description = $3, is_active = $4 WHERE id = $1",
            role.id,
            role.name,
            role.description,
            role.is_active,
        )

    async def set_permissions(self, conn: asyncpg.Connection, role_id: UUID, permission_ids: list[UUID]) -> None:
        await conn.execute(
            "DELETE FROM role_permission WHERE role_id = $1 AND NOT (permission_id = ANY($2::uuid[]))",
            role_id,
            permission_ids,
        )
        await conn.execute(
            "INSERT INTO role_permission (role_id, permission_id) SELECT $1::uuid, unnest($2::uuid[]) ON CONFLICT DO NOTHING",
            role_id,
            permission_ids,
        )

    async def delete(self, conn: asyncpg.Connection, role_id: UUID) -> None:
        await conn.execute("DELETE FROM roles WHERE id = $1", role_id)

    async def has_users(self, conn: asyncpg.Connection, role_id: UUID) -> bool:
        return await conn.fetchval("SELECT EXISTS (SELECT 1 FROM users WHERE role_id = $1)", role_id)

    async def permission_codes(self, conn: asyncpg.Connection, permission_ids: list[UUID]) -> list[str]:
        rows = await conn.fetch("SELECT code FROM permissions WHERE id = ANY($1::uuid[]) ORDER BY code", permission_ids)
        return [row["code"] for row in rows]


roleRepository = RoleRepository()
