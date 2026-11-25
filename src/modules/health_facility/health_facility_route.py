from typing import Optional

from fastapi import APIRouter, Depends

from ...core.security.facility_scope import Scope, facility_scope
from ...core.security.permission_guard import require_permission
from .handlers.health_facility_handlers import (
    HealthFacilityCreateRequest,
    HealthFacilityUpdateRequest,
    healthFacilityHandler,
)

router = APIRouter(prefix="/health-facilities", tags=["health-facilities"])


@router.get("", dependencies=[Depends(require_permission("health_facility.get"))])
async def get_all_health_facilities(
    q: Optional[str] = None,
    active: Optional[bool] = None,
    micro_network_id: Optional[str] = None,
    scope: Optional[Scope] = Depends(facility_scope),
):
    return await healthFacilityHandler.get_all(q, active, micro_network_id, scope)


@router.get("/{health_facility_id}", dependencies=[Depends(require_permission("health_facility.get"))])
async def get_health_facility_by_id(health_facility_id: str):
    return await healthFacilityHandler.get_by_id(health_facility_id)


@router.post("", dependencies=[Depends(require_permission("health_facility.post"))])
async def create_health_facility(body: HealthFacilityCreateRequest, scope: Optional[Scope] = Depends(facility_scope)):
    return await healthFacilityHandler.create(body, scope)


@router.put("/{health_facility_id}", dependencies=[Depends(require_permission("health_facility.put"))])
async def update_health_facility(
    health_facility_id: str, body: HealthFacilityUpdateRequest, scope: Optional[Scope] = Depends(facility_scope)
):
    return await healthFacilityHandler.update(health_facility_id, body, scope)


@router.delete("/{health_facility_id}", dependencies=[Depends(require_permission("health_facility.delete"))])
async def delete_health_facility(health_facility_id: str):
    return await healthFacilityHandler.delete(health_facility_id)
