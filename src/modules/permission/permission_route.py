from fastapi import APIRouter, Depends

from ...core.security.permission_guard import require_permission
from .handlers.permission_handlers import permissionHandler

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("", dependencies=[Depends(require_permission("permission.get"))])
async def get_all_permissions():
    return await permissionHandler.get_all()
