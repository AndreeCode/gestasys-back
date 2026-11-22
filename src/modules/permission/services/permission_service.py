from ..domain.permission_domain import Permission
from ..repositories.permission_repositories import permissionRepository


class PermissionService:
    async def get_all(self) -> list[Permission]:
        return await permissionRepository.get_all()


permissionService = PermissionService()
