import argparse
import asyncio
import sys

import asyncpg

from scripts.common import admin_connection, confirm

TRUNCATE_ALL = """
DO $$
DECLARE
    v_tables TEXT;
BEGIN
    SELECT string_agg(format('%I', tablename), ', ') INTO v_tables FROM pg_tables WHERE schemaname = 'public';
    IF v_tables IS NOT NULL THEN
        EXECUTE 'TRUNCATE ' || v_tables || ' RESTART IDENTITY CASCADE';
    END IF;
END;
$$;
"""

DROP_SCHEMA = "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT USAGE ON SCHEMA public TO PUBLIC;"


async def reset(conn: asyncpg.Connection, drop: bool) -> None:
    async with conn.transaction():
        await conn.execute(DROP_SCHEMA if drop else TRUNCATE_ALL)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drop", action="store_true", help="DROP SCHEMA public CASCADE y recrearlo vacio")
    parser.add_argument("--yes", action="store_true", help="no pedir confirmacion")
    args = parser.parse_args()
    if not args.yes and not confirm("BORRA TODOS LOS DATOS"):
        print("Cancelado")
        return 1
    try:
        conn = await admin_connection()
    except Exception as e:
        print(f"No se pudo conectar: {e}")
        return 1
    try:
        await reset(conn, args.drop)
    except Exception as e:
        print(f"  ✗ reset fallido: {e}")
        return 1
    finally:
        await conn.close()
    print("Esquema eliminado y recreado vacio: ejecuta python -m scripts.migrate" if args.drop else "Todas las tablas fueron vaciadas")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
