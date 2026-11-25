import base64
import hashlib
import hmac
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

INSECURE_SECRET = "dev-secret-change-me"
JWT_ALGORITHMS = ("HS256", "HS384", "HS512")
SSL_MODES = ("disable", "prefer", "require", "verify-ca", "verify-full")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


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


def _secret(key: str, default: str = "") -> str:
    path = os.getenv(f"{key}_FILE")
    if path:
        try:
            with open(path, encoding="utf-8") as source:
                return source.read().strip()
        except OSError as err:
            raise RuntimeError(f"No se pudo leer {key}_FILE ({path}): {err}") from err
    return os.getenv(key, default).strip()


class Config:
    app_env: str = os.getenv("APP_ENV", "development").strip().lower()
    dbhost: str = os.getenv("DB_HOST", "127.0.0.1")
    dbport: int = _int("DB_PORT", 5432)
    dbname: str = os.getenv("DB_NAME", "gestasys")
    dbuser: str = os.getenv("DB_USER", "postgres")
    dbpassword: str = _secret("DB_PASSWORD")
    db_admin_user: str = os.getenv("DB_ADMIN_USER", "")
    db_admin_password: str = _secret("DB_ADMIN_PASSWORD")
    db_pool_max: int = _int("DB_POOL_MAX", 10)
    db_sslmode: str = os.getenv("DB_SSLMODE", "prefer").strip().lower()

    jwt_secret: str = _secret("JWT_SECRET")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_minutes: int = _int("JWT_EXPIRE_MINUTES", 60)
    audit_chain_key_env: str = _secret("AUDIT_CHAIN_KEY")

    temp_password_hours: int = _int("TEMP_PASSWORD_HOURS", 72)
    session_idle_minutes: int = _int("SESSION_IDLE_MINUTES", 30)
    mfa_required: bool = _bool("MFA_REQUIRED", os.getenv("APP_ENV", "").strip().lower() == "production")
    mfa_roles: set[str] = set(_list("MFA_ROLES", "superadmin,admin"))
    mfa_issuer: str = os.getenv("MFA_ISSUER", "GestaSys")
    mfa_encryption_key_env: str = _secret("MFA_ENCRYPTION_KEY")

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
    backup_enabled: bool = _bool("BACKUP_ENABLED", True)
    backup_auto: bool = _bool("BACKUP_AUTO", True)
    backup_hour: int = _int("BACKUP_HOUR", 2)
    backup_minute: int = _int("BACKUP_MINUTE", 0)
    backup_keep: int = _int("BACKUP_KEEP", 14)
    pg_dump_path: str = os.getenv("PG_DUMP_PATH", "pg_dump")
    backup_encryption_key: str = _secret("BACKUP_ENCRYPTION_KEY")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def db_is_local(self) -> bool:
        return self.dbhost in LOCAL_HOSTS or self.dbhost.startswith("/")

    def backup_key(self) -> bytes | None:
        if not self.backup_encryption_key:
            return None
        from ..security.backup_crypto import load_key

        return load_key(self.backup_encryption_key)

    @property
    def audit_chain_key(self) -> str:
        if self.audit_chain_key_env:
            return self.audit_chain_key_env
        return hmac.new(self.jwt_secret.encode(), b"audit-chain-v1", hashlib.sha256).hexdigest()

    @property
    def mfa_key(self) -> bytes:
        if self.mfa_encryption_key_env:
            raw = self.mfa_encryption_key_env
            return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        return hmac.new(self.jwt_secret.encode(), b"mfa-secret-box-v1", hashlib.sha256).digest()

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
        if self.jwt_algorithm not in JWT_ALGORITHMS:
            found.append(f"JWT_ALGORITHM debe ser uno de: {', '.join(JWT_ALGORITHMS)}")
        if self.db_sslmode not in SSL_MODES:
            found.append(f"DB_SSLMODE debe ser uno de: {', '.join(SSL_MODES)}")
        elif self.is_production and not self.db_is_local and self.db_sslmode in ("disable", "prefer"):
            found.append("DB_SSLMODE debe ser require, verify-ca o verify-full si la BD esta en otro servidor")
        if self.backup_encryption_key:
            try:
                self.backup_key()
            except ValueError as err:
                found.append(str(err))
        elif self.is_production and self.backup_enabled:
            found.append("BACKUP_ENCRYPTION_KEY es obligatorio en produccion (python -m scripts.backup_key --generate)")
        if self.is_production and "*" in self.cors_origins:
            found.append("CORS_ORIGINS no puede ser '*' en produccion")
        if self.audit_chain_key_env and len(self.audit_chain_key_env) < 32:
            found.append("AUDIT_CHAIN_KEY debe tener al menos 32 caracteres")
        elif self.is_production and not self.audit_chain_key_env:
            found.append("AUDIT_CHAIN_KEY es obligatorio en produccion (clave del HMAC de la cadena de auditoria)")
        if self.mfa_encryption_key_env:
            try:
                if len(self.mfa_key) != 32:
                    found.append("MFA_ENCRYPTION_KEY debe decodificar a 32 bytes (base64)")
            except ValueError:
                found.append("MFA_ENCRYPTION_KEY no es base64 valido")
        elif self.is_production:
            found.append("MFA_ENCRYPTION_KEY es obligatorio en produccion (python -m scripts.backup_key --generate sirve para crearla)")
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
