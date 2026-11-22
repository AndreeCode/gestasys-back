import asyncio
import sys
from pathlib import Path

import asyncpg

from scripts.common import admin_connection

SQL_DIR = Path(__file__).resolve().parent.parent / "src" / "core" / "db" / "sql"


def sql_files() -> list[Path]:
    files = [SQL_DIR / "init.sql"]
    migrations = SQL_DIR / "migrations"
    if migrations.is_dir():
        files += sorted(migrations.glob("*.sql"))
    return files


async def apply(conn: asyncpg.Connection) -> int:
    for path in sql_files():
        name = path.relative_to(SQL_DIR).as_posix()
        try:
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
        except asyncpg.exceptions.InsufficientPrivilegeError:
            print(f"  ✗ {name}: el usuario no tiene privilegios. Usa el dueño del esquema (DB_ADMIN_USER / DB_ADMIN_PASSWORD).")
            return 1
        except Exception as e:
            first = str(e).splitlines()[0] if str(e) else type(e).__name__
            print(f"  ✗ {name}: {first}")
            print("    No se aplico ningun cambio de este archivo (se revirtio la transaccion).")
            return 1
        print(f"  ✓ {name}: aplicado")
    return 0


async def main() -> int:
    try:
        conn = await admin_connection()
    except Exception as e:
        print(f"No se pudo conectar: {e}")
        return 1
    try:
        return await apply(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
