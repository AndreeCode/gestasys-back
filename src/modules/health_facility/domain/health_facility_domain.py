from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from ....core.db.rows import to_dict


@dataclass
class HealthFacility:
    id: Optional[UUID]
    code: str
    name: str
    category: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    micro_network_id: Optional[UUID] = None
    micro_network_name: Optional[str] = None
    renaes: Optional[str] = None
    province: Optional[str] = None
    active: bool = True
    pregnancy_count: int = 0
    user_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return to_dict(self)
