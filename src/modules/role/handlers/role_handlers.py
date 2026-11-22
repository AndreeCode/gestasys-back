from typing import Optional
from uuid import UUID

from pydantic import Field

from ....core.http.exception_handlers import register_constraints
from ....core.http.list import list_response
from ....core.http.request_models import StrictModel
from ....core.http.success import success
from ....core.http.uuid_param import parse_uuid
from ..services.role_service import roleService

register_constraints(
    {
        "roles_name_key": "Ya existe un rol con ese nombre",
        "roles_name_format": "El nombre del rol no tiene un formato valido",
    }
)


class RoleCreateRequest(StrictModel):
    name: str = Field(min_length=2, max_length=60)
    description: Optional[str] = Field(default=None, max_length=300)
    is_active: Optional[bool] = None
    permission_ids: list[UUID] = Field(default_factory=list)


class RoleUpdateRequest(StrictModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=60)
    description: Optional[str] = Field(default=None, max_length=300)
    is_active: Optional[bool] = None
    permission_ids: Optional[list[UUID]] = None


class RoleHandler:
    async def get_all(self, active: Optional[bool]):
        roles = await roleService.get_all(active)
        return list_response(200, "Roles obtenidos correctamente", [r.to_dict() for r in roles], {"total": len(roles)})

    async def assignable(self, caller_id: UUID):
        roles = await roleService.assignable(caller_id)
        return list_response(
            200, "Roles asignables obtenidos correctamente", [r.to_dict() for r in roles], {"total": len(roles)}
        )

    async def get_by_id(self, role_id: str):
        role = await roleService.get_by_id(parse_uuid(role_id, "role_id"))
        return success(200, "Rol obtenido correctamente", role.to_dict())

    async def create(self, caller_id: UUID, body: RoleCreateRequest):
        role = await roleService.create(caller_id, body.model_dump())
        return success(201, "Rol creado correctamente", role.to_dict())

    async def update(self, caller_id: UUID, role_id: str, body: RoleUpdateRequest):
        role = await roleService.update(caller_id, parse_uuid(role_id, "role_id"), body.model_dump(exclude_unset=True))
        return success(200, "Rol actualizado correctamente", role.to_dict())

    async def delete(self, role_id: str):
        mode = await roleService.delete(parse_uuid(role_id, "role_id"))
        if mode == "logical":
            return success(200, "El rol tiene usuarios asignados: se desactivo en lugar de eliminarse")
        return success(200, "Rol eliminado correctamente")


roleHandler = RoleHandler()
