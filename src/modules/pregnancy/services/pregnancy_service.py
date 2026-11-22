from datetime import date, timedelta
from typing import Any, Optional
from uuid import UUID

import asyncpg

from ....core.db.connection import connection, transaction
from ....core.http.app_error import ConflictError, ForbiddenError, NotFoundError
from ....core.http.validation import Validator, age_on, clean
from ....core.security.facility_scope import in_scope
from ...health_facility.services.health_facility_service import healthFacilityService
from ..domain.pregnancy_domain import (
    GESTATION_DAYS,
    RISK_LEVELS,
    RISK_LOW,
    STATUS_COMPLETED,
    STATUS_PENDING,
    STATUSES,
    Pregnancy,
    PregnancyFilter,
)
from ..repositories.pregnancy_repositories import pregnancyRepository

FIELDS = (
    "dni", "first_names", "last_names", "birth_date", "phone", "address", "health_facility_id",
    "last_menstrual_period", "expected_delivery_date", "gravida", "parity", "risk_level", "status",
    "delivery_date", "notes",
)


def normalize(p: Pregnancy) -> None:
    p.dni = clean(p.dni)
    p.first_names = clean(p.first_names) or ""
    p.last_names = clean(p.last_names) or ""
    p.phone = clean(p.phone)
    p.address = clean(p.address)
    p.notes = clean(p.notes)
    p.risk_level = (p.risk_level or RISK_LOW).strip().lower()
    p.status = (p.status or STATUS_PENDING).strip().lower()


def validate(p: Pregnancy) -> None:
    v = Validator()
    v.dni("dni", p.dni)
    v.required("first_names", p.first_names)
    v.max_len("first_names", p.first_names, 120)
    v.required("last_names", p.last_names)
    v.max_len("last_names", p.last_names, 120)
    v.check(p.birth_date is not None, "birth_date es obligatorio")
    v.check(p.health_facility_id is not None, "health_facility_id es obligatorio")
    v.one_of("risk_level", p.risk_level, RISK_LEVELS)
    v.one_of("status", p.status, STATUSES)
    v.max_len("phone", p.phone, 30)
    v.raise_if_errors()

    today = date.today()
    v.check(p.birth_date <= today, "birth_date no puede estar en el futuro")
    v.check(9 <= age_on(p.birth_date, today) <= 60, "La edad de la gestante debe estar entre 9 y 60 anos")

    lmp = p.last_menstrual_period
    if lmp is not None:
        v.check(lmp <= today, "last_menstrual_period (FUM) no puede estar en el futuro")
        v.check(lmp > p.birth_date, "last_menstrual_period (FUM) debe ser posterior a la fecha de nacimiento")
        if p.status != STATUS_COMPLETED:
            v.check(
                (today - lmp).days <= 45 * 7,
                "La FUM indica mas de 45 semanas de gestacion: verifica la fecha o marca el registro como completado",
            )
        if p.expected_delivery_date is None:
            p.expected_delivery_date = lmp + timedelta(days=GESTATION_DAYS)
        v.check(p.expected_delivery_date > lmp, "expected_delivery_date (FPP) debe ser posterior a la FUM")

    if p.delivery_date is not None:
        v.check(p.status == STATUS_COMPLETED, "delivery_date solo se registra cuando el estado es completed")
        v.check(p.delivery_date <= today, "delivery_date no puede estar en el futuro")
        if lmp is not None:
            v.check(p.delivery_date > lmp, "delivery_date debe ser posterior a la FUM")

    v.between("gravida", p.gravida, 1, 30)
    v.between("parity", p.parity, 0, 30)
    if p.gravida is not None and p.parity is not None:
        v.check(p.parity < p.gravida, "parity (partos) debe ser menor que gravida (gestaciones, incluida la actual)")
    v.raise_if_errors()


async def ensure_no_open_duplicate(conn: asyncpg.Connection, p: Pregnancy, scope: Optional[UUID] = None) -> None:
    if not p.dni or not p.active or p.status == STATUS_COMPLETED:
        return
    other = await pregnancyRepository.get_open_by_dni(conn, p.dni)
    if other is not None and other.id != p.id:
        if not in_scope(other.health_facility_id, scope):
            raise ConflictError(f"El DNI {p.dni} ya tiene un registro abierto en otro establecimiento")
        raise ConflictError(f"Ya existe un registro abierto para el DNI {p.dni} ({other.code})")


def ensure_scope(p: Pregnancy, scope: Optional[UUID]) -> None:
    if scope is None:
        return
    if p.health_facility_id is None:
        p.health_facility_id = scope
    elif p.health_facility_id != scope:
        raise ForbiddenError("Solo puedes registrar gestantes en tu establecimiento")


class PregnancyService:
    async def get_all(self, f: PregnancyFilter, limit: int, offset: int) -> tuple[list[Pregnancy], int]:
        async with connection() as conn:
            return await pregnancyRepository.get_all(conn, f, limit, offset)

    async def get_by_id(self, pregnancy_id: UUID, scope: Optional[UUID] = None) -> Pregnancy:
        async with connection() as conn:
            p = await pregnancyRepository.get_by_id(conn, pregnancy_id)
        if p is None or not in_scope(p.health_facility_id, scope):
            raise NotFoundError("Registro de gestante no encontrado")
        return p

    async def stats(self, facility_id: Optional[UUID] = None) -> dict:
        async with connection() as conn:
            return await pregnancyRepository.stats(conn, facility_id)

    async def create_in(self, conn: asyncpg.Connection, p: Pregnancy, scope: Optional[UUID] = None) -> UUID:
        ensure_scope(p, scope)
        normalize(p)
        validate(p)
        await healthFacilityService.ensure_active(conn, p.health_facility_id)
        await ensure_no_open_duplicate(conn, p, scope)
        return await pregnancyRepository.create(conn, p)

    async def update_in(
        self, conn: asyncpg.Connection, p: Pregnancy, facility_changed: bool, scope: Optional[UUID] = None
    ) -> None:
        ensure_scope(p, scope)
        normalize(p)
        validate(p)
        if facility_changed:
            await healthFacilityService.ensure_active(conn, p.health_facility_id)
        await ensure_no_open_duplicate(conn, p, scope)
        await pregnancyRepository.update(conn, p)

    async def create(self, registered_by: UUID, data: dict[str, Any], scope: Optional[UUID] = None) -> Pregnancy:
        p = Pregnancy(id=None, **{k: data.get(k) for k in FIELDS}, registered_by=registered_by)
        async with transaction() as conn:
            pregnancy_id = await self.create_in(conn, p, scope)
        return await self.get_by_id(pregnancy_id)

    async def update(self, pregnancy_id: UUID, data: dict[str, Any], scope: Optional[UUID] = None) -> Pregnancy:
        p = await self.get_by_id(pregnancy_id, scope)
        required = ("first_names", "last_names", "birth_date", "health_facility_id", "risk_level", "status")
        facility_changed = data.get("health_facility_id") is not None and data["health_facility_id"] != p.health_facility_id
        for key in FIELDS:
            if key in data and (data[key] is not None or key not in required):
                setattr(p, key, data[key])
        if "last_menstrual_period" in data and "expected_delivery_date" not in data:
            p.expected_delivery_date = None
        if data.get("status") and data["status"] != STATUS_COMPLETED and "delivery_date" not in data:
            p.delivery_date = None
        if data.get("active") is not None:
            p.active = data["active"]
        async with transaction() as conn:
            await self.update_in(conn, p, facility_changed, scope)
        return await self.get_by_id(pregnancy_id)

    async def delete(self, pregnancy_id: UUID, scope: Optional[UUID] = None) -> None:
        p = await self.get_by_id(pregnancy_id, scope)
        if not p.active:
            raise ConflictError("El registro ya estaba eliminado")
        async with transaction() as conn:
            await pregnancyRepository.deactivate(conn, pregnancy_id)


pregnancyService = PregnancyService()
