import asyncpg

from ..domain.permission_catalog import PERMISSIONS


async def seed_permissions(conn: asyncpg.Connection) -> dict[str, object]:
    await conn.execute(
        """
        INSERT INTO permissions (code, description)
        SELECT code, description FROM unnest($1::text[], $2::text[]) AS t(code, description)
        ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description
        WHERE permissions.description IS DISTINCT FROM EXCLUDED.description
        """,
        list(PERMISSIONS.keys()),
        list(PERMISSIONS.values()),
    )
    rows = await conn.fetch("SELECT id, code FROM permissions")
    return {row["code"]: row["id"] for row in rows}
