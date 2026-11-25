from typing import Optional
from uuid import UUID

from ....core.db.connection import connection
from ....core.http.app_error import ForbiddenError
from ....core.security.facility_scope import Scope, ids, restrict_facility
from ...pregnancy.repositories.pregnancy_repositories import pregnancyRepository
from ..repositories.report_repositories import reportRepository


def pct(part: int, total: int) -> Optional[float]:
    return round(part * 100 / total, 1) if total else None


def indicators(m: dict) -> list[dict]:
    rows = [
        ("early_capture", "Captación precoz", "1ª APN antes de las 14 semanas", m["early_capture"], m["with_controls"]),
        ("six_apn", "Gestantes con 6 o más APN", "Sobre todas las gestantes", m["six_apn"], m["total"]),
        ("completed_six_apn", "Partos con 6 o más APN", "Sobre las gestantes que ya terminaron", m["completed_six_apn"], m["completed"]),
        ("supplemented", "Suplementación (AF / SOF)", "Al menos una APN con suplemento", m["supplemented"], m["with_controls"]),
        ("exams", "Exámenes auxiliares", "Tiene datos de laboratorio en la ficha", m["exams"], m["total"]),
        ("ultrasound", "Ecografía obstétrica", "Tiene ecografía registrada", m["ultrasound"], m["total"]),
        ("dental", "Control odontológico", "Tiene control odontológico", m["dental"], m["total"]),
        ("vif", "Tamizaje de violencia (VIF)", "Tiene tamizaje VIF", m["vif"], m["total"]),
        ("vaccines", "Vacunas", "Tiene alguna vacuna registrada", m["vaccines"], m["total"]),
        ("birth_plan", "Plan de parto", "Tiene plan de parto", m["birth_plan"], m["total"]),
    ]
    out = [{"id": i, "label": label, "detail": detail, "value": v, "base": b, "percent": pct(v, b)} for i, label, detail, v, b in rows]
    out.append(
        {
            "id": "missed",
            "label": "Inasistentes",
            "detail": "Cita vencida sin control posterior (sobre las activas)",
            "value": m["missed"],
            "base": m["active"],
            "percent": pct(m["missed"], m["active"]),
            "inverse": True,
        }
    )
    return out


class ReportService:
    async def summary(
        self, scope: Optional[Scope], micro_network_id: Optional[UUID], health_facility_id: Optional[UUID]
    ) -> dict:
        async with connection() as conn:
            if health_facility_id is not None:
                facility_ids = restrict_facility(health_facility_id, scope)
            elif micro_network_id is not None:
                network = await reportRepository.facilities_of_network(conn, micro_network_id)
                if scope is not None and not set(network) <= set(scope.facility_ids):
                    raise ForbiddenError("Solo puedes ver las estadisticas de tu microred")
                facility_ids = network
            else:
                facility_ids = ids(scope)
            summary = await reportRepository.summary(conn, facility_ids)
            by_facility = await reportRepository.by_facility(conn, facility_ids)
            options = await reportRepository.options(conn, ids(scope))
            months = await pregnancyRepository.by_month(conn, facility_ids, 12)
            registrars = await pregnancyRepository.by_registrar(conn, facility_ids, 15)
        return {
            "summary": summary,
            "indicators": indicators(summary),
            "by_facility": [
                {
                    "health_facility_id": f["health_facility_id"],
                    "health_facility_name": f["health_facility_name"],
                    "micro_network_name": f["micro_network_name"],
                    "total": f["total"],
                    "active": f["active"],
                    "completed": f["completed"],
                    "risk_high": f["risk_high"],
                    "missed": f["missed"],
                    "avg_controls": f["avg_controls"],
                    "early_capture": pct(f["early_capture"], f["with_controls"]),
                    "six_apn": pct(f["six_apn"], f["total"]),
                    "completed_six_apn": pct(f["completed_six_apn"], f["completed"]),
                }
                for f in by_facility
            ],
            "by_month": months,
            "by_registrar": registrars,
            "options": options,
            "can_choose_network": scope is None,
        }


reportService = ReportService()
