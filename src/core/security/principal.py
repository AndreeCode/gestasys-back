from dataclasses import dataclass
from uuid import UUID

from fastapi import Request

from ..http.app_error import UnauthorizedError


@dataclass
class Principal:
    user_id: UUID
    device_id: UUID
    session_id: UUID
    username: str
    role_id: UUID
    must_change_password: bool


def current_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise UnauthorizedError()
    return principal
