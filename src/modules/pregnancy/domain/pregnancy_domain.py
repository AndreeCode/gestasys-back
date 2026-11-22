from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from ....core.db.rows import to_dict

STATUS_PENDING = "pending"
STATUS_IN_FOLLOWUP = "in_followup"
STATUS_COMPLETED = "completed"
STATUSES = (STATUS_PENDING, STATUS_IN_FOLLOWUP, STATUS_COMPLETED)

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_LEVELS = (RISK_LOW, RISK_MEDIUM, RISK_HIGH)

GESTATION_DAYS = 280


@dataclass
class Pregnancy:
    id: Optional[UUID]
    first_names: str
    last_names: str
    birth_date: Optional[date]
    health_facility_id: Optional[UUID]
    code: Optional[str] = None
    dni: Optional[str] = None
    age: Optional[int] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    health_facility_name: Optional[str] = None
    last_menstrual_period: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    ga_days: Optional[int] = None
    gravida: Optional[int] = None
    parity: Optional[int] = None
    risk_level: str = RISK_LOW
    status: str = STATUS_PENDING
    delivery_date: Optional[date] = None
    notes: Optional[str] = None
    registered_by: Optional[UUID] = None
    active: bool = True
    last_control_date: Optional[date] = None
    controls_count: int = 0
    next_appointment: Optional[date] = None
    last_activity_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def full_name(self) -> str:
        return f"{self.first_names} {self.last_names}"

    def to_dict(self) -> dict:
        data = to_dict(self, hidden=("ga_days",))
        data["full_name"] = self.full_name
        data["gestational_age"] = (
            {"weeks": self.ga_days // 7, "days": self.ga_days % 7} if self.ga_days is not None and self.ga_days >= 0 else None
        )
        return data


@dataclass
class PregnancyFilter:
    q: Optional[str] = None
    health_facility_id: Optional[UUID] = None
    status: Optional[str] = None
    risk_level: Optional[str] = None
    active: Optional[bool] = True
    due_from: Optional[date] = None
    due_to: Optional[date] = None

    def args(self) -> list:
        return [self.q, self.health_facility_id, self.status, self.risk_level, self.active, self.due_from, self.due_to]
