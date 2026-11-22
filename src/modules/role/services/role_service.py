import re
import unicodedata
from typing import Any, Optional
from uuid import UUID

from ....core.db.connection import connection, transaction
from ....core.http.app_error import BadRequestError, ForbiddenError, NotFoundError
from ....core.http.validation import Validator
from ....core.security.permissions import user_permissions
from ...permission.domain.permission_catalog import ADMIN_ROLE
from ..domain.role_domain import Role
from ..repositories.role_repositories import roleRepository

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,59}$")


def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name.strip().lower())
    name = "".join(c for c in name if not unicodedata.combining(c))
    return re.sub(r"[\s\-]+", "_", name)


def is_subset(codes: list[str], of: list[str]) -> bool:
    return set(codes) <= set(of)


def validate_fields(role: Role) -> None:
    v = Validator()
    v.check(bool(NAME_RE.match(role.name)), "name debe empezar con letra y usar solo minusculas, numeros o guion bajo (2-60)")
    v.max_len("description", role.description, 300)
    v.raise_if_errors()


class RoleService:
    async def get_all(self, active: Optional[bool] = None) -> list[Role]:
        async with connection() as conn:
            return await roleRepository.get_all(conn, active)

    async def get_by_id(self, role_id: UUID) -> Role:
        async with connection() as conn:
            role = await roleRepository.get_by_id(conn, role_id)
        if role is None:
            raise NotFoundError("Rol no encontrado")
        return role

    async def assignable(self, caller_id: UUID) -> list[Role]:
        mine = await user_permissions(caller_id)
        return [role for role in await self.get_all(True) if is_subset(role.permissions, mine)]

    async def ensure_can_assign(self, caller_id: UUID, role: Role) -> None:
        if not is_subset(role.permissions, await user_permissions(caller_id)):
            raise ForbiddenError(f"No puedes asignar el rol '{role.name}' porque tiene permisos que tu no tienes")

    async def _validate_permissions(self, conn, caller_id: UUID, permission_ids: list[UUID]) -> list[UUID]:
        permission_ids = list(dict.fromkeys(permission_ids))
        codes = await roleRepository.permission_codes(conn, permission_ids)
        if len(codes) != len(permission_ids):
            raise BadRequestError("Uno o mas permission_ids no existen")
        if not is_subset(codes, await user_permissions(caller_id)):
            raise ForbiddenError("No puedes otorgar permisos que tu no tienes")
        return permission_ids

    async def create(self, caller_id: UUID, data: dict[str, Any]) -> Role:
        role = Role(
            id=None,
            name=normalize_name(data["name"]),
            description=data.get("description") or None,
            is_active=data.get("is_active", True) is not False,
        )
        validate_fields(role)
        async with transaction() as conn:
            permission_ids = await self._validate_permissions(conn, caller_id, data.get("permission_ids") or [])
            role_id = await roleRepository.create(conn, role)
            await roleRepository.set_permissions(conn, role_id, permission_ids)
        return await self.get_by_id(role_id)

    async def update(self, caller_id: UUID, role_id: UUID, data: dict[str, Any]) -> Role:
        role = await self.get_by_id(role_id)

        if data.get("name") is not None:
            name = normalize_name(data["name"])
            if role.is_system and name != role.name:
                raise ForbiddenError("No se puede renombrar un rol del sistema")
            role.name = name
        if "description" in data:
            role.description = data["description"] or None
        if data.get("is_active") is not None:
            if role.name == ADMIN_ROLE and not data["is_active"]:
                raise ForbiddenError("El rol admin no se puede desactivar")
            role.is_active = data["is_active"]
        if "permission_ids" in data and role.name == ADMIN_ROLE:
            raise ForbiddenError("Los permisos del rol admin son fijos (acceso total)")
        validate_fields(role)

        async with transaction() as conn:
            await roleRepository.update(conn, role)
            if "permission_ids" in data:
                permission_ids = await self._validate_permissions(conn, caller_id, data["permission_ids"] or [])
                await roleRepository.set_permissions(conn, role_id, permission_ids)
        return await self.get_by_id(role_id)

    async def delete(self, role_id: UUID) -> str:
        role = await self.get_by_id(role_id)
        if role.is_system:
            raise ForbiddenError("Los roles del sistema no se pueden eliminar")
        async with transaction() as conn:
            if await roleRepository.has_users(conn, role_id):
                role.is_active = False
                await roleRepository.update(conn, role)
                return "logical"
            await roleRepository.delete(conn, role_id)
            return "physical"


roleService = RoleService()
