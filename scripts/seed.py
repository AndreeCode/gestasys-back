import argparse
import asyncio
import sys

import asyncpg

from scripts.common import admin_connection
from src.modules.health_facility.seeders.health_facility_seeder import seed_health_facilities
from src.modules.permission.seeders.permission_seeder import seed_permissions
from src.modules.pregnancy.seeders.pregnancy_seeder import seed_demo_pregnancies
from src.modules.role.seeders.role_seeder import seed_roles
from src.modules.user.seeders.user_seeder import seed_users


async def run(conn: asyncpg.Connection, demo: bool) -> None:
    async with conn.transaction():
        permissions = await seed_permissions(conn)
        roles = await seed_roles(conn)
        users = await seed_users(conn, roles)
        facilities = await seed_health_facilities(conn)
        print(f"  ✓ base: {len(permissions)} permisos, {len(roles)} roles, {len(users)} usuarios, {len(facilities)} establecimientos")
        if demo:
            created = await seed_demo_pregnancies(conn, users["coordinador"], facilities)
            if created:
                print(f"  ✓ demo: {created} registros de gestantes con sus controles")
            else:
                print("  - demo omitida: ya existen registros de gestantes")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-demo", action="store_true", help="solo permisos, roles, usuarios y establecimientos")
    args = parser.parse_args()
    try:
        conn = await admin_connection()
    except Exception as e:
        print(f"No se pudo conectar: {e}")
        return 1
    try:
        await run(conn, not args.no_demo)
    except Exception as e:
        print(f"  ✗ seed fallido, no se guardo nada: {e}")
        return 1
    finally:
        await conn.close()
    print("Seed completado")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
