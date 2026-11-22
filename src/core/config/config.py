import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

INSECURE_SECRET = "dev-secret-change-me"


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "si")


def _list(key: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(key, default).split(",") if item.strip()]


class Config:
    app_env: str = os.getenv("APP_ENV", "development").strip().lower()
    dbhost: str = os.getenv("DB_HOST", "127.0.0.1")
    dbport: int = _int("DB_PORT", 5432)
    dbname: str = os.getenv("DB_NAME", "gestasys")
    dbuser: str = os.getenv("DB_USER", "postgres")
    dbpassword: str = os.getenv("DB_PASSWORD", "")
    db_admin_user: str = os.getenv("DB_ADMIN_USER", "")
    db_admin_password: str = os.getenv("DB_ADMIN_PASSWORD", "")
    db_pool_max: int = _int("DB_POOL_MAX", 10)

    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_minutes: int = _int("JWT_EXPIRE_MINUTES", 60)

    cookie_secure: bool = _bool("COOKIE_SECURE", False) or os.getenv("APP_ENV", "").strip().lower() == "production"
    cookie_samesite: str = os.getenv("COOKIE_SAMESITE", "lax").lower()
    cookie_domain: str | None = os.getenv("COOKIE_DOMAIN") or None

    cors_origins: list[str] = _list("CORS_ORIGINS", "http://localhost:3000")
    trusted_proxies: set[str] = set(_list("TRUSTED_PROXIES", "127.0.0.1,::1"))

    login_max_attempts: int = _int("LOGIN_MAX_ATTEMPTS", 5)
    login_lock_minutes: int = _int("LOGIN_LOCK_MINUTES", 15)
    login_rate_limit: int = _int("LOGIN_RATE_LIMIT", 10)

    import_max_bytes: int = _int("IMPORT_MAX_MB", 10) * 1024 * 1024

    backup_dir: str = os.getenv("BACKUP_DIR", "backups")
    backup_auto: bool = _bool("BACKUP_AUTO", True)
    backup_hour: int = _int("BACKUP_HOUR", 2)
    backup_minute: int = _int("BACKUP_MINUTE", 0)
    backup_keep: int = _int("BACKUP_KEEP", 14)
    pg_dump_path: str = os.getenv("PG_DUMP_PATH", "pg_dump")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def problems(self) -> list[str]:
        found = []
        if self.app_env not in ("development", "production"):
            found.append("APP_ENV debe ser 'development' o 'production'")
        if not self.jwt_secret or self.jwt_secret in (INSECURE_SECRET, "cambia-esto-por-una-clave-larga-y-aleatoria"):
            found.append("JWT_SECRET no esta configurado")
        elif len(self.jwt_secret) < 32:
            found.append("JWT_SECRET debe tener al menos 32 caracteres")
        if not self.dbpassword:
            found.append("DB_PASSWORD no esta configurado")
        if self.is_production and "*" in self.cors_origins:
            found.append("CORS_ORIGINS no puede ser '*' en produccion")
        return found

    def ensure_valid(self) -> None:
        found = self.problems()
        if found:
            raise RuntimeError("Configuracion insegura o incompleta en el .env: " + "; ".join(found))

    def admin_credentials(self) -> tuple[str, str]:
        if self.db_admin_user:
            return self.db_admin_user, self.db_admin_password
        return self.dbuser, self.dbpassword


config = Config()

logger.info(
    "Variables de configuracion obtenidas: env=%s dbhost=%s dbname=%s dbuser=%s cors=%s",
    config.app_env,
    config.dbhost,
    config.dbname,
    config.dbuser,
    config.cors_origins,
)
