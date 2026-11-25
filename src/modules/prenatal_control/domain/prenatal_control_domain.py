from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from ....core.db.rows import to_dict


@dataclass
class PrenatalControl:
    id: Optional[UUID]
    pregnancy_id: UUID
    control_date: date
    pregnancy_code: Optional[str] = None
    pregnant_name: Optional[str] = None
    gestational_weeks: Optional[float] = None
    weight_kg: Optional[float] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    fetal_heart_rate: Optional[int] = None
    uterine_height_cm: Optional[float] = None
    hemoglobin: Optional[float] = None
    next_appointment: Optional[date] = None
    notes: Optional[str] = None
    control_number: Optional[int] = None
    supplementation: Optional[str] = None
    risk_factor: Optional[str] = None
    performed_at: Optional[str] = None
    registered_by: Optional[UUID] = None
    registered_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def alerts(self) -> list[str]:
        out = []
        if (self.systolic_bp or 0) >= 140 or (self.diastolic_bp or 0) >= 90:
            out.append("Presion arterial elevada (>= 140/90)")
        if self.hemoglobin is not None and self.hemoglobin < 11:
            out.append("Hemoglobina baja: posible anemia (< 11 g/dL)")
        if self.fetal_heart_rate is not None and not 110 <= self.fetal_heart_rate <= 160:
            out.append("Frecuencia cardiaca fetal fuera de rango (110-160 lpm)")
        return out

    def to_dict(self) -> dict:
        data = to_dict(self)
        data["alerts"] = self.alerts()
        return data
