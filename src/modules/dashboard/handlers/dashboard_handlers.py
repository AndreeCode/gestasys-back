from ....core.http.success import success
from ....core.security.principal import Principal
from ..services.dashboard_service import dashboardService


class DashboardHandler:
    async def get(self, principal: Principal):
        return success(200, "Resumen obtenido correctamente", await dashboardService.get(principal))


dashboardHandler = DashboardHandler()
