from jwt import PyJWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..db.audit_context import set_audit_context
from ..db.connection import fetchrow
from ..http.error import error
from .client_ip import client_ip
from .cookies import ACCESS_TOKEN_COOKIE, clear_auth_cookie
from .jwt import decode_access_token
from .principal import Principal
from .tokens import hash_token

PUBLIC_PATHS = {
    "/api",
    "/api/auth/login",
    "/api/auth/logout",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
}

PASSWORD_CHANGE_PATHS = {"/api/auth/me", "/api/auth/password"}

SESSION_QUERY = """
SELECT s.id, s.user_id, s.device_id, u.username, u.role_id, u.must_change_password
FROM sessions s
JOIN devices d ON d.id = s.device_id
JOIN users u ON u.id = s.user_id
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

        principal = Principal(
            user_id=row["user_id"],
            device_id=row["device_id"],
            session_id=row["id"],
            username=row["username"],
            role_id=row["role_id"],
            must_change_password=row["must_change_password"],
        )

        if principal.must_change_password and request.url.path not in PASSWORD_CHANGE_PATHS:
            return error(403, "Debes cambiar tu contrasena temporal antes de continuar")

        set_audit_context(user_id=str(principal.user_id), device_id=str(principal.device_id))
        request.state.principal = principal
        return await call_next(request)
