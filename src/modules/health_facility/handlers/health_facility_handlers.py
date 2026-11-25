from typing import Optional
from uuid import UUID

from pydantic import Field

from ....core.http.exception_handlers import register_constraints
from ....core.http.list import list_response
from ....core.http.request_models import StrictModel
from ....core.http.success import success
from ....core.http.uuid_param import parse_uuid
from ....core.http.uuid_param import parse_optional_uuid
from ....core.security.facility_scope import Scope, ids
from ..services.health_facility_service import healthFacilityService

register_constraints(
    {
        "health_facilities_code_key": "Ya existe un establecimiento con ese codigo",
        "uq_health_facilities_name": "Ya existe un establecimiento con ese nombre",
        "uq_health_facilities_renaes": "Ya existe un establecimiento con ese codigo RENAES",
        "health_facilities_micro_network_id_fkey": "La microred indicada no existe",
    }
)


class HealthFacilityCreateRequest(StrictModel):
    code: str = Field(max_length=20)
    name: str = Field(max_length=150)
    category: Optional[str] = Field(default=None, max_length=60)
    district: Optional[str] = Field(default=None, max_length=100)
    address: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    micro_network_id: Optional[UUID] = None
    renaes: Optional[str] = Field(default=None, max_length=20)
    province: Optional[str] = Field(default=None, max_length=100)
    active: Optional[bool] = None


class HealthFacilityUpdateRequest(StrictModel):
    code: Optional[str] = Field(default=None, max_length=20)
    name: Optional[str] = Field(default=None, max_length=150)
    category: Optional[str] = Field(default=None, max_length=60)
    district: Optional[str] = Field(default=None, max_length=100)
    address: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    micro_network_id: Optional[UUID] = None
    renaes: Optional[str] = Field(default=None, max_length=20)
    province: Optional[str] = Field(default=None, max_length=100)
    active: Optional[bool] = None


class HealthFacilityHandler:
    async def get_all(
        self, q: Optional[str], active: Optional[bool], micro_network_id: Optional[str], scope: Optional[Scope]
    ):
        items = await healthFacilityService.get_all(
            q or None, active, ids(scope), parse_optional_uuid(micro_network_id, "micro_network_id")
        )
        return list_response(
            200, "Establecimientos obtenidos correctamente", [f.to_dict() for f in items], {"total": len(items)}
        )

    async def get_by_id(self, facility_id: str):
        facility = await healthFacilityService.get_by_id(parse_uuid(facility_id, "health_facility_id"))
        return success(200, "Establecimiento obtenido correctamente", facility.to_dict())

    async def create(self, body: HealthFacilityCreateRequest):
        facility = await healthFacilityService.create(body.model_dump())
        return success(201, "Establecimiento creado correctamente", facility.to_dict())

    async def update(self, facility_id: str, body: HealthFacilityUpdateRequest):
        facility = await healthFacilityService.update(
            parse_uuid(facility_id, "health_facility_id"), body.model_dump(exclude_unset=True)
        )
        return success(200, "Establecimiento actualizado correctamente", facility.to_dict())

    async def delete(self, facility_id: str):
        mode = await healthFacilityService.delete(parse_uuid(facility_id, "health_facility_id"))
        if mode == "logical":
            return success(200, "El establecimiento tiene registros: se desactivo en lugar de eliminarse")
        return success(200, "Establecimiento eliminado correctamente")


healthFacilityHandler = HealthFacilityHandler()
