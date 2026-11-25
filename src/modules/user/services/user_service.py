from typing import Any, Optional
from uuid import UUID

from ....core.config.config import config
from ....core.db.connection import connection, transaction
from ....core.http.app_error import BadRequestError, ForbiddenError, NotFoundError
from ....core.http.validation import Validator, clean
from ....core.logger.logger import logger
from ....core.security.password import hash_password, verify_password
from ....core.security.permissions import user_permissions
from ....core.security.facility_scope import Scope, ids, user_in_scope
from ....core.security.principal import Principal
from ...health_facility.services.health_facility_service import healthFacilityService
from ...role.services.role_service import is_subset, roleService
from ..domain.user_domain import User
from ..repositories.user_repositories import userRepository


def validate(user: User) -> None:
    v = Validator()
    v.required("username", user.username)
    v.max_len("username", user.username, 100)
    v.check(" " not in (user.username or ""), "username no debe contener espacios")
    v.required("email", user.email)
    v.email("email", user.email)
    v.required("full_name", user.full_name)
    v.max_len("full_name", user.full_name, 200)
    v.dni("dni", user.dni)
    v.max_len("phone", user.phone, 30)
    if user.blocked:
        v.check(bool(user.blocked_reason), "blocked_reason es obligatorio al bloquear un usuario")
    v.raise_if_errors()


class UserService:
    async def get_all(
        self, q=None, role_id=None, active=None, blocked=None, facility_ids=None, scope: Optional[Scope] = None
    ) -> list[User]:
        network = scope.micro_network_id if scope is not None and facility_ids == ids(scope) else None
        async with connection() as conn:
            return await userRepository.get_all(conn, q, role_id, active, blocked, facility_ids, network)

    async def get_by_id(self, user_id: UUID, scope: Optional[Scope] = None) -> User:
        async with connection() as conn:
            user = await userRepository.get_by_id(conn, user_id)
        if user is None or not user_in_scope(user.health_facility_id, user.micro_network_id, scope):
            raise NotFoundError("Usuario no encontrado")
        return user

    def _assignable_scope(
        self, facility_id: Optional[UUID], network_id: Optional[UUID], scope: Optional[Scope]
    ) -> tuple[Optional[UUID], Optional[UUID]]:
        if facility_id is not None and network_id is not None:
            raise BadRequestError("Asigna una microred o un establecimiento, no ambos")
        if scope is None:
            return facility_id, network_id
        if facility_id is None and network_id is None:
            if scope.health_facility_id is not None:
                return scope.health_facility_id, None
            return None, scope.micro_network_id
        if facility_id is not None and facility_id not in scope.facility_ids:
            raise ForbiddenError("Solo puedes asignar usuarios a los establecimientos a tu cargo")
        if network_id is not None and (scope.health_facility_id is not None or network_id != scope.micro_network_id):
            raise ForbiddenError("Solo puedes asignar usuarios a tu propia microred")
        return facility_id, network_id

    async def _ensure_network_active(self, conn, network_id: Optional[UUID]) -> None:
        if network_id is None:
            return
        active = await conn.fetchval("SELECT active FROM micro_networks WHERE id = $1", network_id)
        if active is None:
            raise BadRequestError("La microred indicada no existe")
        if not active:
            raise BadRequestError("La microred indicada esta inactiva")

    async def get_by_login(self, login: str) -> Optional[User]:
        async with connection() as conn:
            return await userRepository.get_by_login(conn, login.strip())

    async def _assignable_role(self, caller_id: UUID, role_id: UUID) -> None:
        try:
            role = await roleService.get_by_id(role_id)
        except NotFoundError:
            raise BadRequestError("El rol indicado no existe")
        if not role.is_active:
            raise BadRequestError("El rol indicado esta inactivo")
        await roleService.ensure_can_assign(caller_id, role)

    async def ensure_can_manage(self, caller_id: UUID, target: User) -> None:
        await self._ensure_can_manage(caller_id, target)

    async def _ensure_can_manage(self, caller_id: UUID, target: User) -> None:
        if caller_id == target.id:
            return
        role = await roleService.get_by_id(target.role_id)
        if not is_subset(role.permissions, await user_permissions(caller_id)):
            raise ForbiddenError("No puedes modificar a un usuario con mas permisos que tu")

    async def create(self, caller_id: UUID, data: dict[str, Any], scope: Optional[Scope] = None) -> User:
        email = (data.get("email") or "").strip().lower()
        username = (data.get("username") or "").strip().lower() or email
        user = User(
            id=None,
            username=username,
            email=email,
            password_hash="",
            role_id=data["role_id"],
            full_name=clean(data.get("full_name")) or "",
            dni=clean(data.get("dni")),
            phone=clean(data.get("phone")),
            active=data.get("active") is not False,
            must_change_password=data.get("must_change_password") is not False,
            created_by=caller_id,
        )
        user.health_facility_id, user.micro_network_id = self._assignable_scope(
            data.get("health_facility_id"), data.get("micro_network_id"), scope
        )
        v = Validator()
        v.password("password", data.get("password"), (user.username, user.email, user.full_name, user.dni))
        v.raise_if_errors()
        validate(user)
        await self._assignable_role(caller_id, user.role_id)
        user.password_hash = hash_password(data["password"])
        async with transaction() as conn:
            if user.health_facility_id is not None:
                await healthFacilityService.ensure_active(conn, user.health_facility_id)
            await self._ensure_network_active(conn, user.micro_network_id)
            user_id = await userRepository.create(conn, user)
        return await self.get_by_id(user_id)

    async def update(self, caller_id: UUID, user_id: UUID, data: dict[str, Any], scope: Optional[Scope] = None) -> User:
        user = await self.get_by_id(user_id, scope)
        await self._ensure_can_manage(caller_id, user)
        is_self = caller_id == user_id

        scope_changed = ("health_facility_id" in data or "micro_network_id" in data) and (
            data.get("health_facility_id") != user.health_facility_id
            or data.get("micro_network_id") != user.micro_network_id
        )
        if scope_changed:
            if is_self:
                raise ForbiddenError("No puedes cambiar tu propio ambito (microred o establecimiento)")
            if scope is not None and data.get("health_facility_id") is None and data.get("micro_network_id") is None:
                raise ForbiddenError("Solo el superadmin puede dar acceso a toda la red")
            user.health_facility_id, user.micro_network_id = self._assignable_scope(
                data.get("health_facility_id"), data.get("micro_network_id"), scope
            )
        facility_changed = scope_changed

        if data.get("username") is not None:
            user.username = data["username"].strip().lower()
        if data.get("email") is not None:
            user.email = data["email"].strip().lower()
        if data.get("full_name") is not None:
            user.full_name = clean(data["full_name"]) or ""
        if "dni" in data:
            user.dni = clean(data["dni"])
        if "phone" in data:
            user.phone = clean(data["phone"])

        if data.get("role_id") is not None and data["role_id"] != user.role_id:
            if is_self:
                raise ForbiddenError("No puedes cambiar tu propio rol")
            await self._assignable_role(caller_id, data["role_id"])
            user.role_id = data["role_id"]

        was_blocked = user.blocked
        if data.get("active") is not None:
            if is_self and not data["active"]:
                raise ForbiddenError("No puedes desactivar tu propia cuenta")
            user.active = data["active"]
        if data.get("blocked") is not None:
            if is_self and data["blocked"]:
                raise ForbiddenError("No puedes bloquear tu propia cuenta")
            user.blocked = data["blocked"]
        if "blocked_reason" in data:
            user.blocked_reason = clean(data["blocked_reason"])
        if not user.blocked:
            user.blocked_reason = None

        validate(user)

        new_hash = None
        if data.get("password"):
            v = Validator()
            v.password("password", data["password"], (user.username, user.email, user.full_name, user.dni))
            v.raise_if_errors()
            new_hash = hash_password(data["password"])

        async with transaction() as conn:
            if facility_changed and user.health_facility_id is not None:
                await healthFacilityService.ensure_active(conn, user.health_facility_id)
            if facility_changed:
                await self._ensure_network_active(conn, user.micro_network_id)
            await userRepository.update(conn, user)
            if was_blocked and not user.blocked:
                await userRepository.unlock(conn, user_id)
            if new_hash:
                await userRepository.set_password(conn, user_id, new_hash, not is_self)
                if not is_self:
                    await userRepository.revoke_sessions(conn, user_id, "password_reset")
        return await self.get_by_id(user_id)

    async def delete(self, caller_id: UUID, user_id: UUID, scope: Optional[Scope] = None) -> None:
        if caller_id == user_id:
            raise ForbiddenError("No puedes desactivar tu propia cuenta")
        user = await self.get_by_id(user_id, scope)
        await self._ensure_can_manage(caller_id, user)
        user.active = False
        async with transaction() as conn:
            await userRepository.update(conn, user)

    async def change_own_password(self, principal: Principal, current: str, new: str) -> None:
        user = await self.get_by_id(principal.user_id)
        if not verify_password(current, user.password_hash):
            raise BadRequestError("La contrasena actual es incorrecta")
        v = Validator()
        v.password("new_password", new, (user.username, user.email, user.full_name, user.dni))
        v.check(new != current, "La nueva contrasena debe ser distinta a la actual")
        v.raise_if_errors()
        async with transaction() as conn:
            await userRepository.set_password(conn, user.id, hash_password(new), False)
            await userRepository.revoke_sessions(conn, user.id, "password_changed", principal.session_id)
            await userRepository.log_auth_event(conn, "PASSWORD_CHANGED", user.id, "successful", None)

    async def register_failure(self, user_id: UUID):
        async with transaction() as conn:
            return await userRepository.register_failure(
                conn, user_id, config.login_max_attempts, config.login_lock_minutes * 60
            )

    async def log_auth_event(self, action: str, user_id: Optional[UUID], result: str, details: Optional[dict] = None):
        try:
            async with transaction() as conn:
                await userRepository.log_auth_event(conn, action, user_id, result, details)
        except Exception as err:
            logger.error(f"No se pudo registrar el evento {action}: {err}")


userService = UserService()
