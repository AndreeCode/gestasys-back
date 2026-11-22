import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Request
from jwt import PyJWTError
from pydantic import Field

from ....core.config.config import config
from ....core.db.audit_context import set_audit_context, valid_ip
from ....core.db.connection import transaction
from ....core.http.error import error
from ....core.http.request_models import StrictModel
from ....core.http.success import success
from ....core.logger.logger import logger
from ....core.security.client_ip import client_ip
from ....core.security.cookies import (
    ACCESS_TOKEN_COOKIE,
    DEVICE_TOKEN_COOKIE,
    clear_auth_cookie,
    set_auth_cookie,
    set_device_cookie,
)
from ....core.security.jwt import create_access_token, decode_access_token
from ....core.security.password import burn_password_check, hash_password, needs_rehash, verify_password
from ....core.security.permissions import user_permissions
from ....core.security.principal import Principal
from ....core.security.tokens import generate_token, hash_token
from ...device.services.device_service import deviceService
from ...session.repositories.session_repositories import sessionRepository
from ...session.services.session_service import sessionService
from ...user.repositories.user_repositories import userRepository
from ...user.services.user_service import userService
from .login_rate_limiter import allow_login_attempt, register_unknown_login_failure, unknown_login_locked_until


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


def lock_message(until: datetime) -> str:
    minutes = max(1, math.ceil((until - datetime.now(timezone.utc)).total_seconds() / 60))
    return f"La cuenta esta bloqueada temporalmente por intentos fallidos. Intenta nuevamente en {minutes} minuto(s)"


async def build_profile(user_id, session: dict) -> dict:
    user = await userService.get_by_id(user_id)
    return {**user.to_dict(), "permissions": await user_permissions(user_id), "session": session}


class AuthHandler:
    async def login(self, request: Request, body: LoginRequest):
        ip = client_ip(request)
        if not allow_login_attempt(ip):
            return error(429, "Demasiados intentos de inicio de sesion, espera un minuto")

        user = await userService.get_by_login(body.username)
        if user is None:
            locked_until = unknown_login_locked_until(body.username)
            if locked_until is not None:
                await userService.log_auth_event("LOGIN_FAILED", None, "blocked", {"username": body.username, "reason": "locked"})
                return error(429, lock_message(locked_until))
            burn_password_check(body.password)
            locked_until = register_unknown_login_failure(body.username)
            await userService.log_auth_event("LOGIN_FAILED", None, "failed", {"username": body.username, "reason": "unknown_user"})
            if locked_until is not None:
                return error(429, lock_message(locked_until))
            return error(401, "Usuario o contrasena incorrectos")

        if user.is_locked():
            await userService.log_auth_event("LOGIN_FAILED", user.id, "blocked", {"reason": "locked"})
            return error(429, lock_message(user.locked_until))

        if not verify_password(body.password, user.password_hash):
            row = await userService.register_failure(user.id)
            await userService.log_auth_event(
                "LOGIN_FAILED", user.id, "failed", {"reason": "bad_password", "attempts": row["failed_attempts"]}
            )
            if row["locked_until"] is not None:
                return error(429, lock_message(row["locked_until"]))
            return error(401, "Usuario o contrasena incorrectos")

        if not user.active:
            await userService.log_auth_event("LOGIN_FAILED", user.id, "blocked", {"reason": "inactive"})
            return error(403, "El usuario esta inactivo")

        if user.blocked:
            await userService.log_auth_event("LOGIN_FAILED", user.id, "blocked", {"reason": "blocked"})
            reason = f": {user.blocked_reason}" if user.blocked_reason else ""
            return error(403, f"La cuenta esta bloqueada{reason}")

        user_agent = request.headers.get("user-agent")
        set_audit_context(user_id=str(user.id), ip=ip, user_agent=user_agent)

        device_token = request.cookies.get(DEVICE_TOKEN_COOKIE)
        if not device_token or len(device_token) < 32:
            device_token = generate_token()
        device = await deviceService.register(user.id, hash_token(device_token), user_agent)
        set_audit_context(device_id=str(device.id))

        if not device.trusted:
            await userService.log_auth_event("LOGIN_FAILED", user.id, "blocked", {"reason": "device_blocked"})
            reason = f": {device.blocked_reason}" if device.blocked_reason else ""
            response = error(403, f"Este dispositivo esta bloqueado para la cuenta{reason}")
            set_device_cookie(response, device_token)
            return response

        session_id = uuid4()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.jwt_expire_minutes)
        token = create_access_token(
            {
                "sub": str(user.id),
                "username": user.username,
                "role_id": str(user.role_id),
                "sid": str(session_id),
                "did": str(device.id),
            },
            expires_at,
        )

        async with transaction() as conn:
            await sessionRepository.create(
                conn, session_id, user.id, device.id, hash_token(token), valid_ip(ip), user_agent, expires_at
            )
            await userRepository.register_login(conn, user.id)
            if needs_rehash(user.password_hash):
                await userRepository.rehash_password(conn, user.id, hash_password(body.password))
            await userRepository.log_auth_event(conn, "LOGIN", user.id, "successful", {"session_id": str(session_id)})

        profile = await build_profile(
            user.id, {"session_id": session_id, "device_id": device.id, "expires_at": expires_at}
        )
        msg = "Inicio de sesion exitoso"
        if profile["must_change_password"]:
            msg = "Inicio de sesion exitoso: debes cambiar tu contrasena temporal"
        response = success(200, msg, profile)
        set_auth_cookie(response, token)
        set_device_cookie(response, device_token)
        return response

    async def logout(self, request: Request):
        token = request.cookies.get(ACCESS_TOKEN_COOKIE)
        if token is not None:
            try:
                payload = decode_access_token(token)
                set_audit_context(
                    user_id=payload.get("sub"),
                    device_id=payload.get("did"),
                    ip=client_ip(request),
                    user_agent=request.headers.get("user-agent"),
                )
                await sessionService.revoke_by_token(hash_token(token), "logout")
                await userService.log_auth_event("LOGOUT", payload.get("sub"), "successful")
            except PyJWTError:
                pass
            except Exception as err:
                logger.error(f"No se pudo cerrar la sesion en la base de datos: {err}")

        response = success(200, "Sesion cerrada correctamente")
        clear_auth_cookie(response)
        return response

    async def me(self, principal: Principal):
        profile = await build_profile(
            principal.user_id, {"session_id": principal.session_id, "device_id": principal.device_id}
        )
        return success(200, "Usuario actual obtenido correctamente", profile)

    async def change_password(self, principal: Principal, body: ChangePasswordRequest):
        await userService.change_own_password(principal, body.current_password, body.new_password)
        return success(200, "Contrasena actualizada correctamente. Se cerraron tus otras sesiones")


authHandler = AuthHandler()
