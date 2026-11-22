from fastapi import APIRouter, Depends

from ...core.security.permission_guard import require_permission
from .handlers.dashboard_handlers import dashboardHandler

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", dependencies=[Depends(require_permission("dashboard.get"))])
async def get_dashboard():
    return await dashboardHandler.get()
