from fastapi import Request

from ...modules.permission.domain.permission_catalog import PERMISSIONS
from ..http.app_error import ForbiddenError
from .permissions import user_has_permission
from .principal import current_principal


def require_permission(code: str):
    if code not in PERMISSIONS:
        raise ValueError(f"Permiso desconocido '{code}': agregalo a permission_catalog.PERMISSIONS")

    async def dependency(request: Request) -> None:
        principal = current_principal(request)
        if not await user_has_permission(principal.user_id, code):
            raise ForbiddenError(f"No tienes permiso para esta accion ({code})")

    return dependency
