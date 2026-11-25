from typing import Optional

from fastapi import APIRouter, Depends

from ...core.security.facility_scope import Scope, facility_scope
from ...core.security.permission_guard import require_permission
from .handlers.report_handlers import reportHandler

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary", dependencies=[Depends(require_permission("report.get"))])
async def get_report_summary(
    micro_network_id: Optional[str] = None,
    health_facility_id: Optional[str] = None,
    scope: Optional[Scope] = Depends(facility_scope),
):
    return await reportHandler.summary(scope, micro_network_id, health_facility_id)
