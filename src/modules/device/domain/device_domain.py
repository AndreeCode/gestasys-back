from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from ....core.db.rows import to_dict


@dataclass
class Device:
    id: UUID
    user_id: UUID
    username: str
    full_name: str
    device_hash: str
    user_agent: Optional[str]
    first_seen_at: datetime
    last_seen_at: datetime
    trusted: bool
    blocked_reason: Optional[str]
    blocked_at: Optional[datetime]
    active_sessions: int = 0

    def to_dict(self) -> dict:
        data = to_dict(self, hidden=("device_hash",))
        data["browser_id"] = self.device_hash[:8]
        return data
