from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.rows import from_row
from ..domain.user_domain import User

SELECT_USER = """
SELECT u.id, u.username, u.email, u.password_hash, u.role_id, r.name AS role, u.full_name, u.dni, u.phone,
       u.health_facility_id, f.name AS health_facility_name, u.active, u.blocked, u.blocked_reason, u.must_change_password, u.password_changed_at,
       u.failed_attempts, u.locked_until, u.last_login_at, u.created_by, u.created_at, u.updated_at
FROM users u
JOIN roles r ON r.id = u.role_id
LEFT JOIN health_facilities f ON f.id = u.health_facility_id
"""


class UserRepository:
    async def get_all(
        self,
        conn: asyncpg.Connection,
        q: Optional[str],
        role_id: Optional[UUID],
        active: Optional[bool],
        blocked: Optional[bool],
        facility_id: Optional[UUID] = None,
    ) -> list[User]:
        rows = await conn.fetch(
            SELECT_USER
            + """
            WHERE ($1::text IS NULL OR u.full_name ILIKE '%' || $1 || '%' OR u.username ILIKE '%' || $1 || '%'
                   OR u.email ILIKE '%' || $1 || '%' OR u.dni = $1)
              AND ($2::uuid IS NULL OR u.role_id = $2)
              AND ($3::bool IS NULL OR u.active = $3)
              AND ($4::bool IS NULL OR u.blocked = $4)
              AND ($5::uuid IS NULL OR u.health_facility_id = $5)
            ORDER BY u.full_name
            """,
            q,
            role_id,
            active,
            blocked,
            facility_id,
        )
        return [from_row(User, row) for row in rows]

    async def get_by_id(self, conn: asyncpg.Connection, user_id: UUID) -> Optional[User]:
        row = await conn.fetchrow(SELECT_USER + " WHERE u.id = $1", user_id)
        return from_row(User, row) if row else None

    async def get_by_login(self, conn: asyncpg.Connection, login: str) -> Optional[User]:
        row = await conn.fetchrow(
            SELECT_USER
            + """
            WHERE lower(u.username) = lower($1) OR lower(u.email) = lower($1)
            ORDER BY (lower(u.username) = lower($1)) DESC
            LIMIT 1
            """,
            login,
        )
        return from_row(User, row) if row else None

    async def create(self, conn: asyncpg.Connection, user: User) -> UUID:
        return await conn.fetchval(
            """
            INSERT INTO users (username, email, password_hash, role_id, full_name, dni, phone, active,
                               must_change_password, password_changed_at, created_by, health_facility_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), $10, $11)
            RETURNING id
            """,
            user.username,
            user.email,
            user.password_hash,
            user.role_id,
            user.full_name,
            user.dni,
            user.phone,
            user.active,
            user.must_change_password,
            user.created_by,
            user.health_facility_id,
        )

    async def update(self, conn: asyncpg.Connection, user: User) -> None:
        await conn.execute(
            """
            UPDATE users SET username = $2, email = $3, role_id = $4, full_name = $5, dni = $6, phone = $7,
                   active = $8, blocked = $9, blocked_reason = $10, health_facility_id = $11
            WHERE id = $1
            """,
            user.id,
            user.username,
            user.email,
            user.role_id,
            user.full_name,
            user.dni,
            user.phone,
            user.active,
            user.blocked,
            user.blocked_reason,
            user.health_facility_id,
        )

    async def set_password(self, conn: asyncpg.Connection, user_id: UUID, password_hash: str, must_change: bool) -> None:
        await conn.execute(
            """
            UPDATE users SET password_hash = $2, must_change_password = $3, password_changed_at = NOW(),
                   failed_attempts = 0, locked_until = NULL
            WHERE id = $1
            """,
            user_id,
            password_hash,
            must_change,
        )

    async def unlock(self, conn: asyncpg.Connection, user_id: UUID) -> None:
        await conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = $1", user_id)

    async def register_failure(self, conn: asyncpg.Connection, user_id: UUID, max_attempts: int, lock_seconds: float):
        return await conn.fetchrow(
            """
            WITH n AS (
                SELECT CASE WHEN locked_until IS NOT NULL AND locked_until <= NOW() THEN 1
                            ELSE failed_attempts + 1 END AS attempts
                FROM users WHERE id = $1
            )
            UPDATE users SET
                failed_attempts = n.attempts,
                locked_until = CASE WHEN n.attempts >= $2 THEN NOW() + make_interval(secs => $3) ELSE NULL END
            FROM n
            WHERE users.id = $1
            RETURNING users.failed_attempts, users.locked_until
            """,
            user_id,
            max_attempts,
            float(lock_seconds),
        )

    async def register_login(self, conn: asyncpg.Connection, user_id: UUID) -> None:
        await conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = NOW() WHERE id = $1", user_id
        )

    async def revoke_sessions(
        self, conn: asyncpg.Connection, user_id: UUID, reason: str, except_session: Optional[UUID] = None
    ) -> None:
        await conn.execute(
            """
            UPDATE sessions SET revoked = TRUE, revoked_reason = $2, revoked_at = NOW()
            WHERE user_id = $1 AND NOT revoked AND ($3::uuid IS NULL OR id <> $3)
            """,
            user_id,
            reason,
            except_session,
        )

    async def log_auth_event(
        self, conn: asyncpg.Connection, action: str, user_id: Optional[UUID], result: str, details: Optional[dict]
    ) -> None:
        await conn.execute(
            "SELECT log_auth_event($1::text, $2::uuid, $3::result_type, $4::jsonb)", action, user_id, result, details
        )


userRepository = UserRepository()
