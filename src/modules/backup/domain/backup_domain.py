from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from ....core.db.rows import to_dict

PRIORITIES = ("high", "normal", "low")


@dataclass
class Backup:
    id: UUID
    kind: str
    status: str
    file_name: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    tables: list[str] = field(default_factory=list)
    priority: str = "high"
    error: Optional[str] = None
    created_by: Optional[UUID] = None
    created_by_name: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        data = to_dict(self)
        data["duration_ms"] = (
            int((self.finished_at - self.started_at).total_seconds() * 1000)
            if self.finished_at and self.started_at
            else None
        )
        return data
