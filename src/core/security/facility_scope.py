from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import Request

from ..http.app_error import ForbiddenError
from .principal import current_principal


@dataclass(frozen=True)
class Scope:
    facility_ids: tuple[UUID, ...]
    micro_network_id: Optional[UUID] = None
    health_facility_id: Optional[UUID] = None

    @property
    def level(self) -> str:
        return "health_facility" if self.health_facility_id else "micro_network"


def facility_scope(request: Request) -> Optional[Scope]:
    return current_principal(request).scope


def ids(scope: Optional[Scope]) -> Optional[list[UUID]]:
    return None if scope is None else list(scope.facility_ids)


def restrict_facility(requested: Optional[UUID], scope: Optional[Scope]) -> Optional[list[UUID]]:
    if requested is not None:
        if scope is not None and requested not in scope.facility_ids:
            raise ForbiddenError("Solo puedes consultar los establecimientos a tu cargo")
        return [requested]
    return ids(scope)


def in_scope(facility_id: Optional[UUID], scope: Optional[Scope]) -> bool:
    return scope is None or facility_id in scope.facility_ids


def user_in_scope(health_facility_id: Optional[UUID], micro_network_id: Optional[UUID], scope: Optional[Scope]) -> bool:
    if scope is None:
        return True
    if health_facility_id is not None:
        return health_facility_id in scope.facility_ids
    return scope.micro_network_id is not None and micro_network_id == scope.micro_network_id
