from typing import Optional
from uuid import UUID

from ....core.config.config import config
from ....core.db.connection import connection, transaction
from ....core.http.app_error import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from ....core.security import totp
from ....core.security.password import verify_password
from ....core.security.principal import Principal
from ....core.security.secret_box import open_sealed, seal
from ...user.domain.user_domain import User
from ...user.repositories.user_repositories import userRepository
from ...user.services.user_service import userService


def context(user_id) -> str:
    return f"mfa:{user_id}"


def required_for(role: Optional[str]) -> bool:
    return config.mfa_required and (role or "") in config.mfa_roles


def setup_required(user: User) -> bool:
    return required_for(user.role) and not user.mfa_enabled


class MfaService:
    async def status(self, user: User) -> dict:
        async with connection() as conn:
            row = await userRepository.get_mfa(conn, user.id)
        return {
            "enabled": bool(row and row["mfa_enabled"]),
            "required": required_for(user.role),
            "setup_pending": bool(row and row["mfa_pending_secret"]),
            "recovery_codes_left": len(row["mfa_recovery_codes"]) if row and row["mfa_enabled"] else 0,
            "enabled_at": row["mfa_enabled_at"] if row else None,
        }

    async def setup(self, user: User) -> dict:
        async with connection() as conn:
            row = await userRepository.get_mfa(conn, user.id)
        if row and row["mfa_enabled"]:
            raise ConflictError("La verificacion en dos pasos ya esta activa")
        secret = totp.new_secret()
        async with transaction() as conn:
            await userRepository.set_mfa_pending(conn, user.id, seal(config.mfa_key, secret, context(user.id)))
        return {"secret": secret, "otpauth_uri": totp.provisioning_uri(secret, user.username, config.mfa_issuer)}

    async def enable(self, principal: Principal, code: str) -> list[str]:
        async with connection() as conn:
            row = await userRepository.get_mfa(conn, principal.user_id)
        if row is None or not row["mfa_pending_secret"]:
            raise BadRequestError("Primero genera la clave con 'Configurar verificacion en dos pasos'")
        if row["mfa_enabled"]:
            raise ConflictError("La verificacion en dos pasos ya esta activa")
        secret = open_sealed(config.mfa_key, row["mfa_pending_secret"], context(principal.user_id))
        step = totp.verify(secret, code)
        if step is None:
            raise BadRequestError("El codigo no es valido. Revisa que la hora del celular sea automatica e intenta de nuevo")
        codes = totp.new_recovery_codes()
        async with transaction() as conn:
            await userRepository.enable_mfa(
                conn, principal.user_id, row["mfa_pending_secret"], step, [totp.hash_recovery_code(c) for c in codes]
            )
            await userRepository.revoke_sessions(conn, principal.user_id, "mfa_enabled", principal.session_id)
            await userRepository.log_auth_event(conn, "MFA_ENABLED", principal.user_id, "successful", None)
        return codes

    async def disable(self, principal: Principal, password: str, code: str) -> None:
        user = await userService.get_by_id(principal.user_id)
        if required_for(user.role):
            raise ForbiddenError("Tu rol exige la verificacion en dos pasos: no se puede desactivar")
        if not verify_password(password, (await self._password_hash(user.id))):
            raise BadRequestError("La contrasena es incorrecta")
        if not await self.verify_code(user.id, code):
            raise BadRequestError("El codigo no es valido")
        async with transaction() as conn:
            await userRepository.clear_mfa(conn, user.id)
            await userRepository.log_auth_event(conn, "MFA_DISABLED", user.id, "successful", None)

    async def reset(self, caller_id: UUID, user_id: UUID, scope: Optional[UUID]) -> None:
        if caller_id == user_id:
            raise ForbiddenError("Para tu propia cuenta usa Configuracion > Verificacion en dos pasos")
        target = await userService.get_by_id(user_id, scope)
        await userService.ensure_can_manage(caller_id, target)
        async with transaction() as conn:
            await userRepository.clear_mfa(conn, user_id)
            await userRepository.revoke_sessions(conn, user_id, "mfa_reset")
            await userRepository.log_auth_event(conn, "MFA_RESET", user_id, "successful", {"by": str(caller_id)})

    async def verify_code(self, user_id: UUID, code: str) -> bool:
        async with connection() as conn:
            row = await userRepository.get_mfa(conn, user_id)
        if row is None or not row["mfa_enabled"] or not row["mfa_secret"]:
            return False
        secret = open_sealed(config.mfa_key, row["mfa_secret"], context(user_id))
        step = totp.verify(secret, code, row["mfa_last_step"])
        async with transaction() as conn:
            if step is not None:
                return await userRepository.set_mfa_step(conn, user_id, step)
            if await userRepository.consume_recovery_code(conn, user_id, totp.hash_recovery_code(code)):
                await userRepository.log_auth_event(conn, "LOGIN", user_id, "successful", {"mfa": "recovery_code"})
                return True
        return False

    async def _password_hash(self, user_id: UUID) -> str:
        async with connection() as conn:
            value = await conn.fetchval("SELECT password_hash FROM users WHERE id = $1", user_id)
        if value is None:
            raise NotFoundError("Usuario no encontrado")
        return value


mfaService = MfaService()
