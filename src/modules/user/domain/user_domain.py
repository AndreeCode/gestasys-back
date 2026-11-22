from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from ....core.db.rows import to_dict


@dataclass
class User:
    id: Optional[UUID]
    username: str
    email: str
    password_hash: str
    role_id: UUID
    full_name: str
    role: Optional[str] = None
    dni: Optional[str] = None
    phone: Optional[str] = None
    health_facility_id: Optional[UUID] = None
    health_facility_name: Optional[str] = None
    active: bool = True
    blocked: bool = False
    blocked_reason: Optional[str] = None
    must_change_password: bool = False
    mfa_enabled: bool = False
    password_changed_at: Optional[datetime] = None
    failed_attempts: int = 0
    locked_until: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return to_dict(self, hidden=("password_hash", "failed_attempts"))
