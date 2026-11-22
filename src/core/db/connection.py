import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

import asyncpg

from ..config.config import config
from .audit_context import KEYS, get_audit_context

_pool: Optional[asyncpg.Pool] = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    for name in ("json", "jsonb"):
        await conn.set_type_codec(name, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=config.dbhost,
            port=config.dbport,
            database=config.dbname,
            user=config.dbuser,
            password=config.dbpassword,
            ssl=config.db_sslmode,
            min_size=1,
            max_size=max(config.db_pool_max, 2),
            init=_init_connection,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("El pool de base de datos no esta inicializado")
    return _pool


async def connect_admin() -> asyncpg.Connection:
    user, password = config.admin_credentials()
    conn = await asyncpg.connect(
        host=config.dbhost, port=config.dbport, database=config.dbname, user=user, password=password,
        ssl=config.db_sslmode,
    )
    await _init_connection(conn)
    return conn


async def apply_audit_context(conn: asyncpg.Connection) -> None:
    audit = get_audit_context()
    await conn.execute(
        "SELECT set_config($1, $5, true), set_config($2, $6, true), set_config($3, $7, true), set_config($4, $8, true)",
        *KEYS,
        *(audit.get(key, "") for key in KEYS),
    )


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await apply_audit_context(conn)
            yield conn


@asynccontextmanager
async def connection() -> AsyncIterator[asyncpg.Connection]:
    async with get_pool().acquire() as conn:
        yield conn


async def fetch(sql: str, *args: Any) -> list[asyncpg.Record]:
    return await get_pool().fetch(sql, *args)


async def fetchrow(sql: str, *args: Any) -> Optional[asyncpg.Record]:
    return await get_pool().fetchrow(sql, *args)


async def fetchval(sql: str, *args: Any) -> Any:
    return await get_pool().fetchval(sql, *args)


async def ping() -> bool:
    try:
        return await get_pool().fetchval("SELECT 1") == 1
    except Exception:
        return False
