import re
from typing import Any, Optional
from uuid import UUID

import asyncpg

from ....core.db.connection import connection, transaction
from ....core.http.app_error import BadRequestError, NotFoundError
from ....core.http.validation import Validator, clean
from ....core.http.app_error import ForbiddenError
from ....core.security.facility_scope import Scope, in_scope
from ..domain.health_facility_domain import HealthFacility
from ..repositories.health_facility_repositories import healthFacilityRepository

CODE_RE = re.compile(r"^[A-Z0-9_-]{2,20}$")
FIELDS = ("code", "name", "category", "district", "address", "phone", "micro_network_id", "renaes", "province")


def normalize(f: HealthFacility) -> None:
    f.code = (f.code or "").strip().upper()
    f.name = clean(f.name) or ""
    f.category = clean(f.category)
    f.district = clean(f.district)
    f.address = clean(f.address)
    f.phone = clean(f.phone)
    f.renaes = clean(f.renaes)
    f.province = clean(f.province)


def validate(f: HealthFacility) -> None:
    v = Validator()
    v.check(bool(CODE_RE.match(f.code)), "code debe tener 2-20 caracteres en mayusculas, numeros, - o _")
    v.required("name", f.name)
    v.max_len("name", f.name, 150)
    v.max_len("phone", f.phone, 30)
    v.check(f.renaes is None or bool(re.fullmatch(r"[0-9]{1,20}", f.renaes)), "renaes debe ser el codigo numerico RENAES")
    v.raise_if_errors()


class HealthFacilityService:
    async def get_all(
        self,
        q: Optional[str] = None,
        active: Optional[bool] = None,
        facility_ids: Optional[list[UUID]] = None,
        micro_network_id: Optional[UUID] = None,
    ) -> list[HealthFacility]:
        async with connection() as conn:
            return await healthFacilityRepository.get_all(conn, q, active, facility_ids, micro_network_id)

    async def get_by_id(self, facility_id: UUID) -> HealthFacility:
        async with connection() as conn:
            facility = await healthFacilityRepository.get_by_id(conn, facility_id)
        if facility is None:
            raise NotFoundError("Establecimiento de salud no encontrado")
        return facility

    async def ensure_active(self, conn: asyncpg.Connection, facility_id: UUID) -> None:
        facility = await healthFacilityRepository.get_by_id(conn, facility_id)
        if facility is None:
            raise BadRequestError("El establecimiento de salud indicado no existe")
        if not facility.active:
            raise BadRequestError("El establecimiento de salud indicado esta inactivo")

    def _check_network(self, network_id: Optional[UUID], scope: Optional[Scope]) -> Optional[UUID]:
        if scope is None:
            return network_id
        if scope.health_facility_id is not None or scope.micro_network_id is None:
            raise ForbiddenError("Solo el admin de una microred o el superadmin pueden crear o mover establecimientos")
        if network_id is not None and network_id != scope.micro_network_id:
            raise ForbiddenError("Solo puedes gestionar establecimientos de tu microred")
        return scope.micro_network_id

    async def create(self, data: dict[str, Any], scope: Optional[Scope] = None) -> HealthFacility:
        data = {**data, "micro_network_id": self._check_network(data.get("micro_network_id"), scope)}
        facility = HealthFacility(id=None, **{k: data.get(k) for k in FIELDS}, active=data.get("active") is not False)
        normalize(facility)
        validate(facility)
        async with transaction() as conn:
            facility_id = await healthFacilityRepository.create(conn, facility)
        return await self.get_by_id(facility_id)

    async def update(self, facility_id: UUID, data: dict[str, Any], scope: Optional[Scope] = None) -> HealthFacility:
        facility = await self.get_by_id(facility_id)
        if not in_scope(facility.id, scope):
            raise NotFoundError("Establecimiento de salud no encontrado")
        if scope is not None and "micro_network_id" in data:
            data = {**data, "micro_network_id": self._check_network(data.get("micro_network_id"), scope)}
        for key in FIELDS:
            if key in data and (data[key] is not None or key not in ("code", "name")):
                setattr(facility, key, data[key])
        if data.get("active") is not None:
            facility.active = data["active"]
        normalize(facility)
        validate(facility)
        async with transaction() as conn:
            await healthFacilityRepository.update(conn, facility)
        return await self.get_by_id(facility_id)

    async def delete(self, facility_id: UUID) -> str:
        await self.get_by_id(facility_id)
        async with transaction() as conn:
            if await healthFacilityRepository.is_used(conn, facility_id):
                await healthFacilityRepository.deactivate(conn, facility_id)
                return "logical"
            await healthFacilityRepository.delete(conn, facility_id)
            return "physical"


healthFacilityService = HealthFacilityService()
