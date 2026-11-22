import argparse
import asyncio
import sys

from scripts.common import admin_connection, confirm
from scripts.migrate import apply
from scripts.reset import reset
from scripts.seed import run


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true", help="ejecutar el seed despues de migrar")
    parser.add_argument("--no-demo", action="store_true", help="con --seed: solo datos base")
    parser.add_argument("--yes", action="store_true", help="no pedir confirmacion")
    args = parser.parse_args()
    if not args.yes and not confirm("ELIMINA EL ESQUEMA COMPLETO"):
        print("Cancelado")
        return 1
    try:
        conn = await admin_connection()
    except Exception as e:
        print(f"No se pudo conectar: {e}")
        return 1
    try:
        await reset(conn, drop=True)
        print("  ✓ reset --drop")
        if await apply(conn) != 0:
            return 1
        if args.seed:
            await run(conn, not args.no_demo)
    except Exception as e:
        print(f"  ✗ fresh fallido: {e}")
        return 1
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
