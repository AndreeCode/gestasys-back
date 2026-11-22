import sys

from src.core.config.config import config
from src.core.db.connection import connect_admin


def confirm(action: str) -> bool:
    if not sys.stdin.isatty():
        print("Sin terminal interactiva: usa --yes para confirmar")
        return False
    answer = input(f"Esto {action} de la base '{config.dbname}'. Escribe el nombre de la base para confirmar: ")
    return answer.strip() == config.dbname


async def admin_connection():
    user, _ = config.admin_credentials()
    print(f"Conectando a {config.dbname} en {config.dbhost}:{config.dbport} como {user}")
    return await connect_admin()
