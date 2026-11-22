from datetime import date
from typing import Any, Optional
from uuid import UUID

import asyncpg

from ....core.db.connection import connection, transaction
from ....core.http.app_error import BadRequestError, ConflictError, NotFoundError
from ....core.http.validation import Validator, clean
from ...pregnancy.domain.pregnancy_domain import STATUS_COMPLETED, STATUS_IN_FOLLOWUP, STATUS_PENDING, Pregnancy
from ...pregnancy.repositories.pregnancy_repositories import pregnancyRepository
from ..domain.prenatal_control_domain import PrenatalControl
from ..repositories.prenatal_control_repositories import VALUES, prenatalControlRepository


def validate(c: PrenatalControl, p: Pregnancy) -> None:
    v = Validator()
    v.between("gestational_weeks", c.gestational_weeks, 0, 45)
    v.between("weight_kg", c.weight_kg, 25, 250)
    v.between("systolic_bp", c.systolic_bp, 50, 260)
    v.between("diastolic_bp", c.diastolic_bp, 30, 180)
    v.between("fetal_heart_rate", c.fetal_heart_rate, 60, 220)
    v.between("uterine_height_cm", c.uterine_height_cm, 0, 60)
    v.between("hemoglobin", c.hemoglobin, 3, 25)
    if c.systolic_bp is not None and c.diastolic_bp is not None:
        v.check(c.systolic_bp > c.diastolic_bp, "systolic_bp debe ser mayor que diastolic_bp")
    v.check(c.control_date <= date.today(), "control_date no puede estar en el futuro")
    lmp = p.last_menstrual_period
    if lmp is not None:
        v.check(c.control_date >= lmp, f"control_date no puede ser anterior a la FUM ({lmp.isoformat()})")
        if c.gestational_weeks is None and c.control_date >= lmp:
            c.gestational_weeks = round((c.control_date - lmp).days / 7, 1)
    if c.next_appointment is not None:
        v.check(c.next_appointment >= c.control_date, "next_appointment debe ser igual o posterior a control_date")
    v.raise_if_errors()


async def load_pregnancy(conn: asyncpg.Connection, pregnancy_id: UUID) -> Pregnancy:
    p = await pregnancyRepository.get_by_id(conn, pregnancy_id)
    if p is None or not p.active:
        raise BadRequestError("El registro de gestante indicado no existe")
    return p


class PrenatalControlService:
    async def get_all(self, pregnancy_id=None, date_from=None, date_to=None) -> list[PrenatalControl]:
        async with connection() as conn:
            return await prenatalControlRepository.get_all(conn, pregnancy_id, date_from, date_to)

    async def get_by_id(self, control_id: UUID) -> PrenatalControl:
        async with connection() as conn:
            c = await prenatalControlRepository.get_by_id(conn, control_id)
        if c is None:
            raise NotFoundError("Control prenatal no encontrado")
        return c

    async def create(self, registered_by: UUID, data: dict[str, Any]) -> PrenatalControl:
        c = PrenatalControl(
            id=None,
            pregnancy_id=data["pregnancy_id"],
            **{key: data.get(key) for key in VALUES},
            registered_by=registered_by,
        )
        c.notes = clean(c.notes)
        async with transaction() as conn:
            p = await load_pregnancy(conn, c.pregnancy_id)
            if p.status == STATUS_COMPLETED:
                raise ConflictError(f"El registro {p.code} esta completado: no admite nuevos controles")
            validate(c, p)
            control_id = await prenatalControlRepository.create(conn, c)
            if p.status == STATUS_PENDING:
                await pregnancyRepository.set_status(conn, p.id, STATUS_IN_FOLLOWUP)
        return await self.get_by_id(control_id)

    async def update(self, control_id: UUID, data: dict[str, Any]) -> PrenatalControl:
        c = await self.get_by_id(control_id)
        date_changed = data.get("control_date") is not None and data["control_date"] != c.control_date
        for key in VALUES:
            if key in data and (data[key] is not None or key != "control_date"):
                setattr(c, key, data[key])
        if date_changed and "gestational_weeks" not in data:
            c.gestational_weeks = None
        c.notes = clean(c.notes)
        async with transaction() as conn:
            validate(c, await load_pregnancy(conn, c.pregnancy_id))
            await prenatalControlRepository.update(conn, c)
        return await self.get_by_id(control_id)

    async def delete(self, control_id: UUID) -> None:
        await self.get_by_id(control_id)
        async with transaction() as conn:
            await prenatalControlRepository.delete(conn, control_id)


prenatalControlService = PrenatalControlService()
