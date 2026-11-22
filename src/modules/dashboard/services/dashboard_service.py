from datetime import datetime
from typing import Optional

from ....core.db.connection import connection, ping
from ...backup.services.backup_service import backupService
from ...pregnancy.repositories.pregnancy_repositories import pregnancyRepository
from ..repositories.dashboard_repositories import dashboardRepository


def describe(table: str, action: str, row: dict, codes: dict[str, str]) -> Optional[str]:
    row = row or {}
    if table == "pregnancies":
        if action == "INSERT":
            return f"Nuevo registro {row.get('code', '')}"
        if action == "UPDATE":
            if row.get("active") is False:
                return f"Registro {row.get('code', '')} eliminado"
            return f"Registro {row.get('code', '')} actualizado"
    if table == "prenatal_controls":
        code = codes.get(str(row.get("pregnancy_id")), "")
        return {
            "INSERT": f"Control prenatal registrado para {code}",
            "UPDATE": f"Control prenatal de {code} actualizado",
            "DELETE": f"Control prenatal de {code} eliminado",
        }.get(action)
    if table == "data_imports" and action == "INSERT":
        return f"Importacion de {int(row.get('inserted', 0)) + int(row.get('updated', 0))} registros"
    if table == "backups" and action == "UPDATE":
        kind = "automatico" if row.get("kind") == "automatic" else "manual"
        if row.get("status") == "completed":
            return f"Backup {kind} completado"
        if row.get("status") == "failed":
            return f"Backup {kind} fallido"
    if table == "users" and action == "INSERT":
        return f"Nuevo usuario {row.get('full_name', '')}"
    return None


class DashboardService:
    async def recent_activity(self, conn, limit: int = 10) -> list[dict]:
        changes = await dashboardRepository.recent_changes(conn, limit * 3)
        ids = [
            str(c["row"].get("pregnancy_id"))
            for c in changes
            if c["affected_table"] == "prenatal_controls" and c["row"] and c["row"].get("pregnancy_id")
        ]
        codes = await dashboardRepository.pregnancy_codes(conn, ids) if ids else {}
        out = []
        for c in changes:
            description = describe(c["affected_table"], c["action"], c["row"], codes)
            if description is None:
                continue
            out.append(
                {
                    "id": c["id"],
                    "table": c["affected_table"],
                    "action": c["action"],
                    "record_id": c["record_id"],
                    "description": description,
                    "user_name": c["user_name"],
                    "created_at": c["created_at"],
                }
            )
            if len(out) == limit:
                break
        return out

    async def get(self) -> dict:
        async with connection() as conn:
            data = {
                "stats": await pregnancyRepository.stats(conn, None),
                "by_facility": await pregnancyRepository.by_facility(conn),
                "recent_activity": await self.recent_activity(conn),
                "upcoming_appointments": await dashboardRepository.upcoming_appointments(conn, 7, 10),
                "due_soon": await dashboardRepository.due_soon(conn, 30, 10),
            }
        backup = await backupService.status()
        last, failure = backup["last_backup"], backup["last_failure"]
        last_ok = None
        if last:
            last_ok = failure is None or failure["started_at"] < last["started_at"]
        elif failure:
            last_ok = False
        data["system"] = {
            "database": "ok" if await ping() else "error",
            "backup_auto": backup["auto_enabled"],
            "backup_schedule": backup["schedule"],
            "pg_dump_available": backup["pg_dump_available"],
            "last_backup_at": last["finished_at"] if last else None,
            "last_backup_ok": last_ok,
            "server_time": datetime.now().astimezone(),
        }
        return data


dashboardService = DashboardService()
