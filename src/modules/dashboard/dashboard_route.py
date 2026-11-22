from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends

from ...core.security.facility_scope import facility_scope
from ...core.security.permission_guard import require_permission
from .handlers.dashboard_handlers import dashboardHandler

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", dependencies=[Depends(require_permission("dashboard.get"))])
async def get_dashboard(scope: Optional[UUID] = Depends(facility_scope)):
    return await dashboardHandler.get(scope)
