from uuid import UUID

from ..db.connection import fetch, fetchval


async def user_has_permission(user_id: UUID, code: str) -> bool:
    return bool(
        await fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM users u
                JOIN roles r ON r.id = u.role_id
                JOIN role_permission rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE u.id = $1 AND u.active AND NOT u.blocked AND r.is_active AND p.code = $2
            )
            """,
            user_id,
            code,
        )
    )


async def user_permissions(user_id: UUID) -> list[str]:
    rows = await fetch(
        """
        SELECT p.code
        FROM users u
        JOIN roles r ON r.id = u.role_id AND r.is_active
        JOIN role_permission rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE u.id = $1
        ORDER BY p.code
        """,
        user_id,
    )
    return [row["code"] for row in rows]
