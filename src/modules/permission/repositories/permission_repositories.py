from ....core.db.connection import fetch
from ....core.db.rows import from_row
from ..domain.permission_domain import Permission


class PermissionRepository:
    async def get_all(self) -> list[Permission]:
        rows = await fetch("SELECT id, code, description FROM permissions ORDER BY code")
        return [from_row(Permission, row) for row in rows]


permissionRepository = PermissionRepository()
