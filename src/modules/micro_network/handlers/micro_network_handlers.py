from typing import Optional

from pydantic import Field

from ....core.http.exception_handlers import register_constraints
from ....core.http.list import list_response
from ....core.http.request_models import StrictModel
from ....core.http.success import success
from ....core.http.uuid_param import parse_uuid
from ....core.security.facility_scope import Scope
from ..services.micro_network_service import microNetworkService

register_constraints(
    {
        "micro_networks_code_key": "Ya existe una microred con ese codigo",
        "uq_micro_networks_name": "Ya existe una microred con ese nombre",
    }
)


class MicroNetworkCreateRequest(StrictModel):
    code: Optional[str] = Field(default=None, max_length=20)
    name: str = Field(max_length=150)
    network: Optional[str] = Field(default=None, max_length=150)
    active: Optional[bool] = None


class MicroNetworkUpdateRequest(StrictModel):
    code: Optional[str] = Field(default=None, max_length=20)
    name: Optional[str] = Field(default=None, max_length=150)
    network: Optional[str] = Field(default=None, max_length=150)
    active: Optional[bool] = None


class MicroNetworkHandler:
    async def get_all(self, q: Optional[str], active: Optional[bool], scope: Optional[Scope]):
        items = await microNetworkService.get_all(q or None, active, scope)
        return list_response(200, "Microredes obtenidas correctamente", [m.to_dict() for m in items], {"total": len(items)})

    async def create(self, body: MicroNetworkCreateRequest):
        m = await microNetworkService.create(body.model_dump())
        return success(201, "Microred creada correctamente", m.to_dict())

    async def update(self, network_id: str, body: MicroNetworkUpdateRequest):
        m = await microNetworkService.update(parse_uuid(network_id, "micro_network_id"), body.model_dump(exclude_unset=True))
        return success(200, "Microred actualizada correctamente", m.to_dict())


microNetworkHandler = MicroNetworkHandler()
