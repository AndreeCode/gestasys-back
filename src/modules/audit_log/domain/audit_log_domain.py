from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from ....core.db.rows import to_dict


@dataclass
class AuditLog:
    id: UUID
    user_id: Optional[UUID]
    user_name: Optional[str]
    device_id: Optional[UUID]
    action: str
    affected_table: Optional[str]
    record_id: Optional[UUID]
    record_key: Any
    ip_address: Optional[str]
    user_agent: Optional[str]
    result: str
    details: Any
    created_at: datetime
    user_role: Optional[str] = None
    record_label: Optional[str] = None
    health_facility_id: Optional[UUID] = None
    health_facility_name: Optional[str] = None
    micro_network_id: Optional[UUID] = None
    micro_network_name: Optional[str] = None
    actor_health_facility_name: Optional[str] = None

    def to_dict(self) -> dict:
        return to_dict(self)


@dataclass
class AuditLogFilter:
    user_id: Optional[UUID] = None
    affected_table: Optional[str] = None
    record_id: Optional[UUID] = None
    action: Optional[str] = None
    result: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    q: Optional[str] = None
    health_facility_ids: Optional[list[UUID]] = None
    micro_network_id: Optional[UUID] = None

    def args(self) -> list:
        return [
            self.user_id, self.affected_table, self.record_id, self.action, self.result, self.date_from, self.date_to,
            self.q, self.health_facility_ids, self.micro_network_id,
        ]
