from typing import Optional
from uuid import UUID

from fastapi import Request

from ..http.app_error import ForbiddenError
from .principal import current_principal


def facility_scope(request: Request) -> Optional[UUID]:
    return current_principal(request).health_facility_id


def restrict_facility(requested: Optional[UUID], scope: Optional[UUID]) -> Optional[UUID]:
    if scope is None:
        return requested
    if requested is not None and requested != scope:
        raise ForbiddenError("Solo puedes consultar los registros de tu establecimiento")
    return scope


def in_scope(facility_id: Optional[UUID], scope: Optional[UUID]) -> bool:
    return scope is None or facility_id == scope
