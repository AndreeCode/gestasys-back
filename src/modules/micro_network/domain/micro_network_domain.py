from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from ....core.db.rows import to_dict


@dataclass
class MicroNetwork:
    id: Optional[UUID]
    code: str
    name: str
    network: str = "Red de Salud Huamanga"
    active: bool = True
    facility_count: int = 0
    pregnancy_count: int = 0
    user_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return to_dict(self)
