import json
from datetime import datetime, timedelta, timezone

from jwt import PyJWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..config.config import config
from ..db.audit_context import set_audit_context
from ..db.connection import fetchrow, get_pool, transaction
from ..http.error import error
from .client_ip import client_ip
from .cookies import ACCESS_TOKEN_COOKIE, clear_auth_cookie
from .jwt import decode_access_token
from .principal import Principal
from .tokens import hash_token

PUBLIC_PATHS = {"/api", "/api/auth/login", "/api/auth/login/mfa", "/api/auth/logout"}
if not config.is_production:
    PUBLIC_PATHS |= {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}

PASSWORD_CHANGE_PATHS = {"/api/auth/me", "/api/auth/password"}
MFA_SETUP_PATHS = {"/api/auth/me", "/api/auth/password", "/api/auth/mfa", "/api/auth/mfa/setup", "/api/auth/mfa/enable"}
TOUCH_EVERY = timedelta(seconds=60)

SESSION_QUERY = """
SELECT s.id, s.user_id, s.device_id, s.last_activity_at, u.username, u.role_id, u.must_change_password,
       u.health_facility_id, u.mfa_enabled, r.name AS role_name
FROM sessions s
JOIN devices d ON d.id = s.device_id
JOIN users u ON u.id = s.user_id
JOIN roles r ON r.id = u.role_id
WHERE s.token_hash = $1
  AND NOT s.revoked
  AND s.expires_at > NOW()
  AND d.trusted
  AND u.active
  AND NOT u.blocked
"""


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        set_audit_context(ip=client_ip(request), user_agent=request.headers.get("user-agent"))

        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        token = request.cookies.get(ACCESS_TOKEN_COOKIE)
        if token is None:
            return error(401, "No autenticado")

        try:
            payload = decode_access_token(token)
        except PyJWTError as err:
            return error(401, "Token invalido o expirado", err)

        try:
            row = await fetchrow(SESSION_QUERY, hash_token(token))
        except Exception as err:
            return error(500, "Error al validar la sesion", err)

        if row is None or str(row["user_id"]) != payload.get("sub"):
            response = error(401, "La sesion fue cerrada o ya no es valida")
            clear_auth_cookie(response)
            return response

        now = datetime.now(timezone.utc)
        if config.session_idle_minutes > 0 and row["last_activity_at"] < now - timedelta(minutes=config.session_idle_minutes):
            async with transaction() as conn:
                await conn.execute(
                    "UPDATE sessions SET revoked = TRUE, revoked_reason = 'idle_timeout', revoked_at = NOW() WHERE id = $1",
                    row["id"],
                )
                await conn.execute(
                    "SELECT log_auth_event('SESSION_IDLE', $1, 'successful', $2::jsonb)",
                    row["user_id"],
                    json.dumps({"session_id": str(row["id"]), "idle_minutes": config.session_idle_minutes}),
                )
            response = error(401, "Tu sesion se cerro por inactividad, vuelve a ingresar")
            clear_auth_cookie(response)
            return response
        if row["last_activity_at"] < now - TOUCH_EVERY:
            async with get_pool().acquire() as conn:
                await conn.execute("UPDATE sessions SET last_activity_at = NOW() WHERE id = $1", row["id"])

        principal = Principal(
            user_id=row["user_id"],
            device_id=row["device_id"],
            session_id=row["id"],
            username=row["username"],
            role_id=row["role_id"],
            must_change_password=row["must_change_password"],
            health_facility_id=row["health_facility_id"],
        )

        if principal.must_change_password and request.url.path not in PASSWORD_CHANGE_PATHS:
            return error(403, "Debes cambiar tu contrasena temporal antes de continuar")

        if (
            config.mfa_required
            and row["role_name"] in config.mfa_roles
            and not row["mfa_enabled"]
            and request.url.path not in MFA_SETUP_PATHS
        ):
            return error(403, "Tu rol exige la verificacion en dos pasos: activala para continuar")

        set_audit_context(user_id=str(principal.user_id), device_id=str(principal.device_id))
        request.state.principal = principal
        return await call_next(request)
