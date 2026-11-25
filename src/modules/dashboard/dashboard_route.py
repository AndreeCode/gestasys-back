from fastapi import APIRouter, Depends, Request

from ...core.security.permission_guard import require_permission
from ...core.security.principal import current_principal
from .handlers.dashboard_handlers import dashboardHandler

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", dependencies=[Depends(require_permission("dashboard.get"))])
async def get_dashboard(request: Request):
    return await dashboardHandler.get(current_principal(request))
