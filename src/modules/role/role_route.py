from typing import Optional

from fastapi import APIRouter, Depends, Request

from ...core.security.permission_guard import require_permission
from ...core.security.principal import current_principal
from .handlers.role_handlers import RoleCreateRequest, RoleUpdateRequest, roleHandler

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", dependencies=[Depends(require_permission("role.get"))])
async def get_all_roles(active: Optional[bool] = None):
    return await roleHandler.get_all(active)


@router.get("/assignable", dependencies=[Depends(require_permission("user.post"))])
async def get_assignable_roles(request: Request):
    return await roleHandler.assignable(current_principal(request).user_id)


@router.get("/{role_id}", dependencies=[Depends(require_permission("role.get"))])
async def get_role_by_id(role_id: str):
    return await roleHandler.get_by_id(role_id)


@router.post("", dependencies=[Depends(require_permission("role.post"))])
async def create_role(request: Request, body: RoleCreateRequest):
    return await roleHandler.create(current_principal(request).user_id, body)


@router.put("/{role_id}", dependencies=[Depends(require_permission("role.put"))])
async def update_role(request: Request, role_id: str, body: RoleUpdateRequest):
    return await roleHandler.update(current_principal(request).user_id, role_id, body)


@router.delete("/{role_id}", dependencies=[Depends(require_permission("role.delete"))])
async def delete_role(role_id: str):
    return await roleHandler.delete(role_id)
