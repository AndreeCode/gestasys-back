from datetime import datetime
from typing import Optional
from uuid import UUID

from ....core.db import audit_chain
from ....core.db.connection import connection, ping
from ....core.security.facility_scope import Scope, ids
from ....core.security.principal import Principal
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
    async def recent_activity(self, conn, limit: int = 10, facility_ids: Optional[list[UUID]] = None) -> list[dict]:
        changes = await dashboardRepository.recent_changes(conn, limit * 3, facility_ids)
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
                    "health_facility_name": c["health_facility_name"],
                    "ip_address": c["ip_address"],
                    "created_at": c["created_at"],
                }
            )
            if len(out) == limit:
                break
        return out

    async def get(self, principal: Principal) -> dict:
        scope: Optional[Scope] = principal.scope
        facility_ids = ids(scope)
        async with connection() as conn:
            names = await dashboardRepository.scope_names(conn, principal.health_facility_id, principal.micro_network_id)
            data = {
                "scope": {
                    "level": "network" if scope is None else scope.level,
                    "health_facility_name": names["health_facility_name"],
                    "micro_network_name": names["micro_network_name"],
                    "facilities": None if scope is None else len(scope.facility_ids),
                    "active_users": names["active_users"],
                },
                "stats": await pregnancyRepository.stats(conn, facility_ids),
                "mine": await pregnancyRepository.stats(conn, facility_ids, principal.user_id),
                "by_facility": await pregnancyRepository.by_facility(conn, facility_ids),
                "by_micro_network": await pregnancyRepository.by_micro_network(conn) if scope is None else [],
                "by_registrar": await pregnancyRepository.by_registrar(conn, facility_ids),
                "by_month": await pregnancyRepository.by_month(conn, facility_ids),
                "recent_activity": await self.recent_activity(conn, facility_ids=facility_ids),
                "upcoming_appointments": await dashboardRepository.upcoming_appointments(conn, 7, 10, facility_ids),
                "due_soon": await dashboardRepository.due_soon(conn, 30, 10, facility_ids),
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
            "backup_enabled": backup["enabled"],
            "backup_auto": backup["auto_enabled"],
            "backup_schedule": backup["schedule"],
            "pg_dump_available": backup["pg_dump_available"],
            "last_backup_at": last["finished_at"] if last else None,
            "last_backup_ok": last_ok,
            "server_time": datetime.now().astimezone(),
        }
        if scope is None:
            async with connection() as conn:
                data["system"].update(await dashboardRepository.auth_summary(conn))
            check = audit_chain.last_check
            data["system"]["audit_chain_ok"] = check.get("ok")
            data["system"]["audit_chain_checked_at"] = check.get("checked_at")
            data["system"]["audit_chain_records"] = check.get("checked")
        return data


dashboardService = DashboardService()
