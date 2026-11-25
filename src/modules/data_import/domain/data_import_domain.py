from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from ....core.db.rows import to_dict


@dataclass
class DataImport:
    id: Optional[UUID]
    file_name: str
    total_rows: int = 0
    inserted: int = 0
    updated: int = 0
    failed: int = 0
    errors: list[dict] = field(default_factory=list)
    dry_run: bool = False
    imported_by: Optional[UUID] = None
    imported_by_name: Optional[str] = None
    format: str = "csv"
    controls: int = 0
    warnings: int = 0
    created_facilities: list[str] = field(default_factory=list)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    health_facility_name: Optional[str] = None
    micro_network_name: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return to_dict(self)
