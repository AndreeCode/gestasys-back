from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from ....core.db.rows import to_dict


@dataclass
class Session:
    id: UUID
    user_id: UUID
    username: str
    full_name: str
    device_id: UUID
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    expires_at: datetime
    revoked: bool
    revoked_reason: Optional[str]
    revoked_at: Optional[datetime]
    active: bool
    current: bool = False

    def to_dict(self) -> dict:
        return to_dict(self)
