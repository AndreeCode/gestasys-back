from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from ...core.security.facility_scope import facility_scope
from ...core.security.permission_guard import require_permission
from ...core.security.principal import current_principal
from .handlers.user_handlers import UserCreateRequest, UserUpdateRequest, userHandler

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", dependencies=[Depends(require_permission("user.get"))])
async def get_all_users(
    q: Optional[str] = None,
    role_id: Optional[str] = None,
    active: Optional[bool] = None,
    blocked: Optional[bool] = None,
    health_facility_id: Optional[str] = None,
    scope: Optional[UUID] = Depends(facility_scope),
):
    return await userHandler.get_all(q, role_id, active, blocked, health_facility_id, scope)


@router.get("/{user_id}", dependencies=[Depends(require_permission("user.get"))])
async def get_user_by_id(user_id: str, scope: Optional[UUID] = Depends(facility_scope)):
    return await userHandler.get_by_id(user_id, scope)


@router.post("", dependencies=[Depends(require_permission("user.post"))])
async def create_user(request: Request, body: UserCreateRequest):
    principal = current_principal(request)
    return await userHandler.create(principal.user_id, principal.health_facility_id, body)


@router.put("/{user_id}", dependencies=[Depends(require_permission("user.put"))])
async def update_user(request: Request, user_id: str, body: UserUpdateRequest):
    principal = current_principal(request)
    return await userHandler.update(principal.user_id, principal.health_facility_id, user_id, body)


@router.delete("/{user_id}", dependencies=[Depends(require_permission("user.delete"))])
async def delete_user(request: Request, user_id: str):
    principal = current_principal(request)
    return await userHandler.delete(principal.user_id, principal.health_facility_id, user_id)
