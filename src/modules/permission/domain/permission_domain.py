from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from .permission_catalog import module_of


@dataclass
class Permission:
    id: UUID
    code: str
    description: Optional[str] = None

    def to_dict(self) -> dict:
        return {"id": self.id, "code": self.code, "module": module_of(self.code), "description": self.description}
