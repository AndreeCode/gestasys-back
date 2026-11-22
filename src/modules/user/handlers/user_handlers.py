from typing import Optional
from uuid import UUID

from pydantic import Field

from ....core.http.exception_handlers import register_constraints
from ....core.http.list import list_response
from ....core.http.request_models import StrictModel
from ....core.http.success import success
from ....core.http.uuid_param import parse_optional_uuid, parse_uuid
from ..services.user_service import userService

register_constraints(
    {
        "uq_users_username": "Ya existe un usuario con ese nombre de usuario",
        "uq_users_email": "Ya existe un usuario con ese correo",
        "uq_users_dni": "Ya existe un usuario con ese DNI",
        "users_dni_format": "dni debe tener 8 digitos",
        "users_role_id_fkey": "El rol indicado no existe",
    }
)


class UserCreateRequest(StrictModel):
    username: Optional[str] = Field(default=None, max_length=100)
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)
    role_id: UUID
    full_name: str = Field(max_length=200)
    dni: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    active: Optional[bool] = None
    must_change_password: Optional[bool] = None


class UserUpdateRequest(StrictModel):
    username: Optional[str] = Field(default=None, max_length=100)
    email: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=128)
    role_id: Optional[UUID] = None
    full_name: Optional[str] = Field(default=None, max_length=200)
    dni: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    active: Optional[bool] = None
    blocked: Optional[bool] = None
    blocked_reason: Optional[str] = None


class UserHandler:
    async def get_all(self, q: Optional[str], role_id: Optional[str], active: Optional[bool], blocked: Optional[bool]):
        users = await userService.get_all(q or None, parse_optional_uuid(role_id, "role_id"), active, blocked)
        return list_response(200, "Usuarios obtenidos correctamente", [u.to_dict() for u in users], {"total": len(users)})

    async def get_by_id(self, user_id: str):
        user = await userService.get_by_id(parse_uuid(user_id, "user_id"))
        return success(200, "Usuario obtenido correctamente", user.to_dict())

    async def create(self, caller_id: UUID, body: UserCreateRequest):
        user = await userService.create(caller_id, body.model_dump())
        return success(201, "Usuario registrado correctamente", user.to_dict())

    async def update(self, caller_id: UUID, user_id: str, body: UserUpdateRequest):
        user = await userService.update(caller_id, parse_uuid(user_id, "user_id"), body.model_dump(exclude_unset=True))
        return success(200, "Usuario actualizado correctamente", user.to_dict())

    async def delete(self, caller_id: UUID, user_id: str):
        await userService.delete(caller_id, parse_uuid(user_id, "user_id"))
        return success(200, "Usuario desactivado correctamente")


userHandler = UserHandler()
