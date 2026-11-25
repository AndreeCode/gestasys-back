import re
import unicodedata
from typing import Any, Optional
from uuid import UUID

import asyncpg

from ....core.db.connection import connection, transaction
from ....core.http.app_error import NotFoundError
from ....core.http.validation import Validator, clean
from ....core.security.facility_scope import Scope
from ..domain.micro_network_domain import MicroNetwork
from ..repositories.micro_network_repositories import microNetworkRepository

CODE_RE = re.compile(r"^[A-Z0-9_-]{2,20}$")


def code_from_name(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c)).upper()
    folded = re.sub(r"^(MICRO\s*RED|MR\.?)\s*(DE\s+SALUD\s+)?", "", folded.strip())
    return ("MR-" + re.sub(r"[^A-Z0-9]+", "-", folded).strip("-"))[:20]


def validate(m: MicroNetwork) -> None:
    v = Validator()
    v.check(bool(CODE_RE.match(m.code)), "code debe tener 2-20 caracteres en mayusculas, numeros, - o _")
    v.required("name", m.name)
    v.max_len("name", m.name, 150)
    v.required("network", m.network)
    v.max_len("network", m.network, 150)
    v.raise_if_errors()


class MicroNetworkService:
    async def get_all(self, q=None, active=None, scope: Optional[Scope] = None) -> list[MicroNetwork]:
        only = None
        if scope is not None:
            only = scope.micro_network_id
            if only is None:
                return []
        async with connection() as conn:
            return await microNetworkRepository.get_all(conn, q, active, only)

    async def get_by_id(self, network_id: UUID) -> MicroNetwork:
        async with connection() as conn:
            m = await microNetworkRepository.get_by_id(conn, network_id)
        if m is None:
            raise NotFoundError("Microred no encontrada")
        return m

    async def create(self, data: dict[str, Any]) -> MicroNetwork:
        name = clean(data.get("name")) or ""
        m = MicroNetwork(
            id=None,
            code=(data.get("code") or code_from_name(name)).strip().upper(),
            name=name,
            network=clean(data.get("network")) or "Red de Salud Huamanga",
            active=data.get("active") is not False,
        )
        validate(m)
        async with transaction() as conn:
            network_id = await microNetworkRepository.create(conn, m)
        return await self.get_by_id(network_id)

    async def ensure(self, conn: asyncpg.Connection, name: str) -> UUID:
        existing = await microNetworkRepository.find_by_name(conn, name)
        if existing is not None:
            return existing.id
        clean_name = clean(name) or name
        if not re.match(r"(?i)^micro\s*red", clean_name):
            clean_name = f"Microred {clean_name.title()}"
        return await microNetworkRepository.create(
            conn, MicroNetwork(id=None, code=code_from_name(name), name=clean_name)
        )

    async def update(self, network_id: UUID, data: dict[str, Any]) -> MicroNetwork:
        m = await self.get_by_id(network_id)
        for key in ("code", "name", "network"):
            if data.get(key) is not None:
                setattr(m, key, data[key].strip().upper() if key == "code" else clean(data[key]))
        if data.get("active") is not None:
            m.active = data["active"]
        validate(m)
        async with transaction() as conn:
            await microNetworkRepository.update(conn, m)
        return await self.get_by_id(network_id)


microNetworkService = MicroNetworkService()
