from typing import Optional

from fastapi import APIRouter, Depends

from ...core.security.facility_scope import Scope, facility_scope
from ...core.security.permission_guard import require_permission
from .handlers.micro_network_handlers import MicroNetworkCreateRequest, MicroNetworkUpdateRequest, microNetworkHandler

router = APIRouter(prefix="/micro-networks", tags=["micro-networks"])


@router.get("", dependencies=[Depends(require_permission("micro_network.get"))])
async def get_all_micro_networks(
    q: Optional[str] = None, active: Optional[bool] = None, scope: Optional[Scope] = Depends(facility_scope)
):
    return await microNetworkHandler.get_all(q, active, scope)


@router.post("", dependencies=[Depends(require_permission("micro_network.post"))])
async def create_micro_network(body: MicroNetworkCreateRequest):
    return await microNetworkHandler.create(body)


@router.put("/{micro_network_id}", dependencies=[Depends(require_permission("micro_network.put"))])
async def update_micro_network(micro_network_id: str, body: MicroNetworkUpdateRequest):
    return await microNetworkHandler.update(micro_network_id, body)
