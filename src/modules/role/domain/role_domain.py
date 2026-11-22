from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from ....core.db.rows import to_dict


@dataclass
class Role:
    id: Optional[UUID]
    name: str
    description: Optional[str] = None
    is_system: bool = False
    is_active: bool = True
    permission_ids: list[UUID] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    user_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return to_dict(self)
