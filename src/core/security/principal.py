from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from typing import TYPE_CHECKING

from fastapi import Request

from ..http.app_error import UnauthorizedError

if TYPE_CHECKING:
    from .facility_scope import Scope


@dataclass
class Principal:
    user_id: UUID
    device_id: UUID
    session_id: UUID
    username: str
    role_id: UUID
    must_change_password: bool
    health_facility_id: Optional[UUID] = None
    micro_network_id: Optional[UUID] = None
    scope: Optional["Scope"] = None


def current_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise UnauthorizedError()
    return principal
