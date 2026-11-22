from typing import Optional
from uuid import UUID

from ....core.http.success import success
from ..services.dashboard_service import dashboardService


class DashboardHandler:
    async def get(self, scope: Optional[UUID] = None):
        return success(200, "Resumen obtenido correctamente", await dashboardService.get(scope))


dashboardHandler = DashboardHandler()
