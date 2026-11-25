from datetime import date
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import Field

from ....core.http.exception_handlers import register_constraints
from ....core.http.list import list_response
from ....core.http.request_models import StrictModel
from ....core.http.success import success
from ....core.http.uuid_param import parse_optional_uuid, parse_uuid
from ....core.security.facility_scope import Scope, restrict_facility
from ...audit_log.services.audit_log_service import auditLogService
from ..domain.pregnancy_domain import PregnancyFilter
from ..services.pregnancy_service import pregnancyService

register_constraints(
    {
        "pregnancies_code_key": "Ya existe un registro con ese codigo",
        "uq_pregnancies_open_dni": "Ya existe un registro abierto para ese DNI",
        "pregnancies_dni_format": "dni debe tener 8 digitos",
        "pregnancies_edd_after_lmp": "La FPP debe ser posterior a la FUM",
        "pregnancies_lmp_after_birth": "La FUM debe ser posterior a la fecha de nacimiento",
        "pregnancies_health_facility_id_fkey": "El establecimiento de salud indicado no existe",
    }
)

Status = Literal["pending", "in_followup", "completed"]
Risk = Literal["low", "medium", "high"]


class PregnancyCreateRequest(StrictModel):
    dni: Optional[str] = None
    first_names: str = Field(max_length=120)
    last_names: str = Field(max_length=120)
    birth_date: date
    phone: Optional[str] = Field(default=None, max_length=30)
    address: Optional[str] = None
    health_facility_id: Optional[UUID] = None
    clinical_record: Optional[str] = Field(default=None, max_length=30)
    insurance: Optional[str] = Field(default=None, max_length=60)
    province: Optional[str] = Field(default=None, max_length=100)
    district: Optional[str] = Field(default=None, max_length=100)
    locality: Optional[str] = Field(default=None, max_length=150)
    last_menstrual_period: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    gravida: Optional[int] = None
    parity: Optional[int] = None
    risk_level: Optional[Risk] = None
    status: Optional[Status] = None
    delivery_date: Optional[date] = None
    notes: Optional[str] = None


class PregnancyUpdateRequest(StrictModel):
    dni: Optional[str] = None
    first_names: Optional[str] = Field(default=None, max_length=120)
    last_names: Optional[str] = Field(default=None, max_length=120)
    birth_date: Optional[date] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    address: Optional[str] = None
    health_facility_id: Optional[UUID] = None
    clinical_record: Optional[str] = Field(default=None, max_length=30)
    insurance: Optional[str] = Field(default=None, max_length=60)
    province: Optional[str] = Field(default=None, max_length=100)
    district: Optional[str] = Field(default=None, max_length=100)
    locality: Optional[str] = Field(default=None, max_length=150)
    last_menstrual_period: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    gravida: Optional[int] = None
    parity: Optional[int] = None
    risk_level: Optional[Risk] = None
    status: Optional[Status] = None
    delivery_date: Optional[date] = None
    notes: Optional[str] = None
    active: Optional[bool] = None


class MinsaCellsRequest(StrictModel):
    cells: dict[Annotated[str, Field(max_length=40, pattern=r"^(f|c|apn):[a-z0-9_:]+$")], Annotated[str, Field(max_length=1000)]] = Field(
        min_length=1, max_length=300
    )


class PregnancySearchRequest(StrictModel):
    q: Optional[str] = Field(default=None, max_length=120)
    health_facility_id: Optional[str] = None
    status: Optional[Status] = None
    risk_level: Optional[Risk] = None
    active: Optional[bool] = None
    due_from: Optional[date] = None
    due_to: Optional[date] = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    delimiter: Optional[str] = None
    mark: Optional[Annotated[str, Field(pattern=r"^(any|none|[0-9A-Fa-f]{6})$")]] = None
    micro_network_id: Optional[UUID] = None
    age_group: Optional[Literal["teen", "adult", "older"]] = None
    insurance: Optional[str] = Field(default=None, max_length=40)
    controls: Optional[Literal["none", "lt6", "gte6"]] = None
    missed: Optional[bool] = None
    created_from: Optional[date] = None
    created_to: Optional[date] = None
    sections: Optional[list[Annotated[str, Field(max_length=40, pattern=r"^[a-z0-9-]+$")]]] = Field(default=None, max_length=40)


def build_filter(
    q: Optional[str],
    health_facility_id: Optional[str],
    status: Optional[Status],
    risk_level: Optional[Risk],
    active: Optional[bool],
    due_from: Optional[date],
    due_to: Optional[date],
    scope: Optional[Scope] = None,
    mark: Optional[str] = None,
    extra: Optional[dict] = None,
) -> PregnancyFilter:
    return PregnancyFilter(
        q=(q or "").strip() or None,
        health_facility_ids=restrict_facility(parse_optional_uuid(health_facility_id, "health_facility_id"), scope),
        status=status,
        risk_level=risk_level,
        active=True if active is None else active,
        due_from=due_from,
        due_to=due_to,
        mark=(mark or "").strip().upper() or None if mark not in ("any", "none") else mark,
        **{k: v for k, v in (extra or {}).items() if v not in (None, "")},
    )


class PregnancyHandler:
    async def get_all(self, f: PregnancyFilter, limit: int, offset: int):
        items, total = await pregnancyService.get_all(f, limit, offset)
        return list_response(
            200,
            "Registros obtenidos correctamente",
            [p.to_dict() for p in items],
            {"total": total, "limit": limit, "offset": offset},
        )

    async def stats(self, health_facility_id: Optional[str], scope: Optional[Scope] = None):
        facility = restrict_facility(parse_optional_uuid(health_facility_id, "health_facility_id"), scope)
        stats = await pregnancyService.stats(facility)
        return success(200, "Estadisticas obtenidas correctamente", stats)

    async def get_by_id(self, pregnancy_id: str, scope: Optional[Scope] = None):
        p = await pregnancyService.get_by_id(parse_uuid(pregnancy_id, "pregnancy_id"), scope)
        return success(200, "Registro obtenido correctamente", p.to_dict())

    async def history(self, pregnancy_id: str, scope: Optional[Scope] = None):
        p = await pregnancyService.get_by_id(parse_uuid(pregnancy_id, "pregnancy_id"), scope)
        logs = await auditLogService.record_history(p.id)
        return list_response(
            200, "Historial obtenido correctamente", [log.to_dict() for log in logs], {"total": len(logs)}
        )

    async def create(self, registered_by: UUID, scope: Optional[Scope], body: PregnancyCreateRequest):
        p = await pregnancyService.create(registered_by, body.model_dump(), scope)
        return success(201, f"Registro {p.code} creado correctamente", p.to_dict())

    async def update(self, pregnancy_id: str, body: PregnancyUpdateRequest, scope: Optional[Scope] = None):
        p = await pregnancyService.update(
            parse_uuid(pregnancy_id, "pregnancy_id"), body.model_dump(exclude_unset=True), scope
        )
        return success(200, f"Registro {p.code} actualizado correctamente", p.to_dict())

    async def delete(self, pregnancy_id: str, scope: Optional[Scope] = None):
        await pregnancyService.delete(parse_uuid(pregnancy_id, "pregnancy_id"), scope)
        return success(200, "Registro eliminado correctamente")


pregnancyHandler = PregnancyHandler()
