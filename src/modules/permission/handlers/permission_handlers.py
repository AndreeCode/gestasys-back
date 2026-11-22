from ....core.http.list import list_response
from ..services.permission_service import permissionService


class PermissionHandler:
    async def get_all(self):
        permissions = await permissionService.get_all()
        return list_response(
            200, "Permisos obtenidos correctamente", [p.to_dict() for p in permissions], {"total": len(permissions)}
        )


permissionHandler = PermissionHandler()
