from typing import Optional

from fastapi import APIRouter, Depends, Request

from ...core.security.permission_guard import require_permission
from ...core.security.principal import current_principal
from .handlers.user_handlers import UserCreateRequest, UserUpdateRequest, userHandler

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", dependencies=[Depends(require_permission("user.get"))])
async def get_all_users(
    q: Optional[str] = None, role_id: Optional[str] = None, active: Optional[bool] = None, blocked: Optional[bool] = None
):
    return await userHandler.get_all(q, role_id, active, blocked)


@router.get("/{user_id}", dependencies=[Depends(require_permission("user.get"))])
async def get_user_by_id(user_id: str):
    return await userHandler.get_by_id(user_id)


@router.post("", dependencies=[Depends(require_permission("user.post"))])
async def create_user(request: Request, body: UserCreateRequest):
    return await userHandler.create(current_principal(request).user_id, body)


@router.put("/{user_id}", dependencies=[Depends(require_permission("user.put"))])
async def update_user(request: Request, user_id: str, body: UserUpdateRequest):
    return await userHandler.update(current_principal(request).user_id, user_id, body)


@router.delete("/{user_id}", dependencies=[Depends(require_permission("user.delete"))])
async def delete_user(request: Request, user_id: str):
    return await userHandler.delete(current_principal(request).user_id, user_id)
