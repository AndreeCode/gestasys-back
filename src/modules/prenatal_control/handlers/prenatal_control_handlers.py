from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import Field

from ....core.http.list import list_response
from ....core.http.request_models import StrictModel
from ....core.http.success import success
from ....core.http.uuid_param import parse_optional_uuid, parse_uuid
from ..services.prenatal_control_service import prenatalControlService


class PrenatalControlCreateRequest(StrictModel):
    pregnancy_id: UUID
    control_date: date
    gestational_weeks: Optional[float] = None
    weight_kg: Optional[float] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    fetal_heart_rate: Optional[int] = None
    uterine_height_cm: Optional[float] = None
    hemoglobin: Optional[float] = None
    next_appointment: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class PrenatalControlUpdateRequest(StrictModel):
    control_date: Optional[date] = None
    gestational_weeks: Optional[float] = None
    weight_kg: Optional[float] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    fetal_heart_rate: Optional[int] = None
    uterine_height_cm: Optional[float] = None
    hemoglobin: Optional[float] = None
    next_appointment: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class PrenatalControlHandler:
    async def get_all(self, pregnancy_id: Optional[str], date_from: Optional[date], date_to: Optional[date]):
        items = await prenatalControlService.get_all(parse_optional_uuid(pregnancy_id, "pregnancy_id"), date_from, date_to)
        return list_response(200, "Controles obtenidos correctamente", [c.to_dict() for c in items], {"total": len(items)})

    async def get_by_id(self, control_id: str):
        c = await prenatalControlService.get_by_id(parse_uuid(control_id, "prenatal_control_id"))
        return success(200, "Control obtenido correctamente", c.to_dict())

    async def create(self, registered_by: UUID, body: PrenatalControlCreateRequest):
        c = await prenatalControlService.create(registered_by, body.model_dump())
        return success(201, "Control registrado correctamente", c.to_dict())

    async def update(self, control_id: str, body: PrenatalControlUpdateRequest):
        c = await prenatalControlService.update(parse_uuid(control_id, "prenatal_control_id"), body.model_dump(exclude_unset=True))
        return success(200, "Control actualizado correctamente", c.to_dict())

    async def delete(self, control_id: str):
        await prenatalControlService.delete(parse_uuid(control_id, "prenatal_control_id"))
        return success(200, "Control eliminado correctamente")


prenatalControlHandler = PrenatalControlHandler()
