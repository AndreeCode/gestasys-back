from typing import Optional

from ....core.http.success import success
from ....core.http.uuid_param import parse_optional_uuid
from ....core.security.facility_scope import Scope
from ..services.report_service import reportService


class ReportHandler:
    async def summary(self, scope: Optional[Scope], micro_network_id: Optional[str], health_facility_id: Optional[str]):
        data = await reportService.summary(
            scope,
            parse_optional_uuid(micro_network_id, "micro_network_id"),
            parse_optional_uuid(health_facility_id, "health_facility_id"),
        )
        return success(200, "Estadisticas obtenidas correctamente", data)


reportHandler = ReportHandler()
