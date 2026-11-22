from ....core.http.success import success
from ..services.dashboard_service import dashboardService


class DashboardHandler:
    async def get(self):
        return success(200, "Resumen obtenido correctamente", await dashboardService.get())


dashboardHandler = DashboardHandler()
