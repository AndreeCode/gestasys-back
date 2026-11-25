import re
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

import asyncpg

from ....core.http.app_error import AppError, ForbiddenError, ValidationError
from ....core.security.facility_scope import Scope, in_scope
from ...health_facility.domain.health_facility_domain import HealthFacility
from ...health_facility.repositories.health_facility_repositories import healthFacilityRepository
from ...micro_network.services.micro_network_service import microNetworkService
from ...pregnancy.domain.pregnancy_domain import (
    GESTATION_DAYS,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    STATUS_COMPLETED,
    STATUS_IN_FOLLOWUP,
    STATUS_PENDING,
    Pregnancy,
)
from ...pregnancy.repositories.pregnancy_repositories import pregnancyRepository
from ...pregnancy.services.pregnancy_service import normalize, validate
from ...prenatal_control.domain.prenatal_control_domain import PrenatalControl
from ...prenatal_control.repositories.prenatal_control_repositories import prenatalControlRepository
from ..domain.csv_format import fold
from ..domain.minsa_format import (
    MinsaRecord,
    clean_phone,
    is_empty,
    parse_any_date,
    parse_formula,
    split_name,
)

CATEGORY_PREFIXES = (
    (("hospital", "hosp", "h"), "Hospital"),
    (("centro de salud", "cs", "c s"), "Centro de Salud"),
    (("puesto de salud", "ps", "p s"), "Puesto de Salud"),
)


def facility_key(name: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", fold(name))
    text = " ".join(text.split())
    for prefixes, _ in CATEGORY_PREFIXES:
        for prefix in sorted(prefixes, key=len, reverse=True):
            if text.startswith(prefix + " "):
                text = text[len(prefix) + 1:]
                break
    text = re.sub(r"^de ", "", text)
    return text.replace(" ", "")


def facility_category(name: str) -> Optional[str]:
    text = " ".join(re.sub(r"[^a-z0-9 ]+", " ", fold(name)).split())
    for prefixes, category in CATEGORY_PREFIXES:
        if any(text.startswith(p + " ") for p in prefixes):
            return category
    return None


def display_name(raw: str) -> str:
    text = " ".join(raw.replace(".", ". ").split())
    category = facility_category(raw)
    core = re.sub(r"^(P\.\s*S\.|C\.\s*S\.|H\.|HOSP\.?|PUESTO DE SALUD( DE)?|CENTRO DE SALUD( DE)?|HOSPITAL)\s*", "", text, flags=re.I)
    prefix = {"Puesto de Salud": "P.S.", "Centro de Salud": "C.S.", "Hospital": "H."}.get(category or "", "")
    return f"{prefix} {core.title()}".strip()[:150]


class FacilityResolver:
    def __init__(self, conn: asyncpg.Connection, scope: Optional[Scope]):
        self.conn = conn
        self.scope = scope
        self.loaded = False
        self.by_renaes: dict[str, HealthFacility] = {}
        self.by_key: dict[str, HealthFacility] = {}
        self.created: list[str] = []

    async def load(self) -> None:
        for f in await healthFacilityRepository.get_all(self.conn, None, None):
            if f.renaes:
                self.by_renaes[f.renaes] = f
            self.by_key.setdefault(facility_key(f.name), f)
            self.by_key.setdefault(facility_key(f.code), f)
        self.loaded = True

    async def resolve(self, record: MinsaRecord) -> UUID:
        if not self.loaded:
            await self.load()
        renaes = re.sub(r"\D", "", record.get("renaes")) or None
        name = record.get("facility")
        key = facility_key(name)
        facility = self.by_key.get(key) if name else None
        owner = self.by_renaes.get(renaes) if renaes else None
        if facility is None and owner is not None and (not name or facility_key(owner.name) == key):
            facility = owner
        if renaes and owner is not None and facility is not owner:
            record.warnings.append(f"RENAES {renaes} pertenece a '{owner.name}', no a '{name}': se ignoro el codigo")
            renaes = None
        if facility is None:
            if self.scope is not None:
                raise ForbiddenError(
                    f"El EE.SS. '{name}' no esta registrado: pidele al superadmin que lo cree en su microred"
                )
            facility = await self._create(record, renaes, name)
        if not facility.active:
            raise AppError(400, f"El EE.SS. '{facility.name}' esta inactivo")
        if not in_scope(facility.id, self.scope):
            raise ForbiddenError(f"El EE.SS. '{facility.name}' no esta a tu cargo")
        if renaes and not facility.renaes:
            await self.conn.execute("UPDATE health_facilities SET renaes = $2 WHERE id = $1 AND renaes IS NULL", facility.id, renaes)
            facility.renaes = renaes
            self.by_renaes[renaes] = facility
        return facility.id

    async def _create(self, record: MinsaRecord, renaes: Optional[str], name: str) -> HealthFacility:
        if not name:
            raise AppError(400, "La fila no indica el EE.SS.")
        network_name = record.get("micro_network")
        network_id = await microNetworkService.ensure(self.conn, network_name) if network_name else None
        code = f"EESS-{renaes}" if renaes else ("EESS-" + re.sub(r"[^A-Z0-9]+", "-", fold(name).upper()).strip("-"))[:20]
        facility = HealthFacility(
            id=None,
            code=code[:20],
            name=display_name(name),
            category=facility_category(name),
            district=(record.get("district") or None),
            province=(record.get("province") or None),
            renaes=renaes,
            micro_network_id=network_id,
        )
        facility.id = await healthFacilityRepository.create(self.conn, facility)
        self.created.append(facility.name)
        if renaes:
            self.by_renaes[renaes] = facility
        self.by_key[facility_key(name)] = facility
        self.by_key[facility_key(facility.name)] = facility
        return facility


def estimate_birth_date(age: str, reference: date) -> Optional[date]:
    match = re.search(r"\d{1,2}", age or "")
    if not match:
        return None
    years = int(match.group())
    try:
        return reference.replace(year=reference.year - years) - timedelta(days=182)
    except ValueError:
        return reference.replace(month=2, day=28, year=reference.year - years) - timedelta(days=182)


def risk_from(record: MinsaRecord, age: Optional[int]) -> str:
    text = fold(" ".join([record.observations or ""] + [c.risk_factor or "" for c in record.controls]))
    has_factor = any(c.risk_factor and not is_empty(c.risk_factor) for c in record.controls)
    if re.search(r"\baro\b", text) or has_factor or (age is not None and (age < 15 or age > 35)):
        return RISK_HIGH
    if age is not None and age < 18:
        return RISK_MEDIUM
    return RISK_LOW


def age_on(birth: date, today: date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def fill(p: Pregnancy, record: MinsaRecord, facility_id: UUID) -> list[str]:
    warnings: list[str] = []
    first, last = split_name(record.get("full_name"))
    if not first:
        raise ValidationError("APELLIDOS Y NOMBRES debe tener al menos un apellido y un nombre")
    p.first_names, p.last_names = first, last
    p.health_facility_id = facility_id

    dni = re.sub(r"\D", "", record.get("dni"))
    if dni and len(dni) == 8:
        p.dni = dni
    elif record.get("dni") and not is_empty(record.get("dni")):
        warnings.append("DNI con formato invalido, se omitio")

    first_control = min((c.control_date for c in record.controls if c.control_date), default=None)
    birth = parse_any_date(record.get("birth_date"))
    if birth is not None:
        p.birth_date, p.birth_date_estimated = birth, False
    elif p.birth_date is None:
        estimated = estimate_birth_date(record.get("age"), first_control or date.today())
        if estimated is None:
            raise ValidationError("Falta la FECHA DE NACIMIENTO y la EDAD")
        p.birth_date, p.birth_date_estimated = estimated, True
        warnings.append("fecha de nacimiento estimada desde la edad")

    p.phone = clean_phone(record.get("phone")) or p.phone
    p.address = record.get("address") or p.address
    p.clinical_record = (record.get("clinical_record") or p.clinical_record or None)
    if p.clinical_record:
        p.clinical_record = p.clinical_record[:30]
    p.insurance = (record.get("insurance") or p.insurance or None)
    p.province = record.get("province") or p.province
    p.district = record.get("district") or p.district
    p.locality = record.get("locality") or p.locality
    formula = record.get("formula")
    if formula:
        p.obstetric_formula = formula[:30]
        gravida, parity = parse_formula(formula)
        if gravida is not None:
            p.gravida, p.parity = gravida, parity

    lmp = parse_any_date(record.get("lmp"))
    edd = parse_any_date(record.get("edd"))
    if lmp is not None:
        p.last_menstrual_period = lmp
        p.expected_delivery_date = edd if edd and edd > lmp else lmp + timedelta(days=GESTATION_DAYS)
    elif edd is not None:
        p.expected_delivery_date = edd

    if record.delivery_date is not None:
        p.status, p.delivery_date = STATUS_COMPLETED, record.delivery_date
    elif p.status != STATUS_COMPLETED:
        p.status = STATUS_IN_FOLLOWUP if any(c.control_date for c in record.controls) else STATUS_PENDING
    if p.status != STATUS_COMPLETED and lmp and (date.today() - lmp).days > 45 * 7:
        p.status = STATUS_COMPLETED
        warnings.append("FUM con mas de 45 semanas y sin fecha de parto: se marco como completado")

    p.risk_level = risk_from(record, age_on(p.birth_date, date.today()))
    notes = [record.observations] if record.observations else []
    if record.termination:
        notes.append(f"Terminacion: {record.termination}")
    p.notes = " · ".join(notes)[:2000] or p.notes
    p.clinical_data = record.clinical_data
    p.row_color = record.row_color
    p.cell_marks = record.cell_marks
    p.source = "import_minsa"
    return warnings


async def save_controls(conn: asyncpg.Connection, p: Pregnancy, record: MinsaRecord, user: UUID) -> tuple[int, list[str]]:
    saved, warnings = 0, []
    today = date.today()
    for mc in record.controls:
        if mc.control_date is None:
            continue
        problem = None
        if mc.control_date > today:
            problem = "fecha en el futuro"
        elif p.last_menstrual_period and mc.control_date < p.last_menstrual_period:
            problem = "fecha anterior a la FUM"
        if problem:
            warnings.append(f"APN {mc.number} ({mc.control_date.strftime('%d/%m/%Y')}): {problem}, no se registro")
            continue
        weeks = mc.gestational_weeks
        if weeks is None and p.last_menstrual_period:
            weeks = round((mc.control_date - p.last_menstrual_period).days / 7, 1)
        next_appointment = mc.next_appointment if mc.next_appointment and mc.next_appointment >= mc.control_date else None
        existing = await prenatalControlRepository.find_by_date(conn, p.id, mc.control_date)
        c = existing or PrenatalControl(id=None, pregnancy_id=p.id, control_date=mc.control_date, registered_by=user)
        c.gestational_weeks = weeks if weeks is None or 0 <= weeks <= 45 else None
        c.next_appointment = next_appointment
        c.supplementation = mc.supplementation[:60] if mc.supplementation else None
        c.risk_factor = mc.risk_factor
        c.performed_at = mc.performed_at[:150] if mc.performed_at else None
        c.control_number = mc.number
        if existing:
            await prenatalControlRepository.update(conn, c)
            await conn.execute("UPDATE prenatal_controls SET control_number = $2 WHERE id = $1", c.id, mc.number)
        else:
            await prenatalControlRepository.create(conn, c)
        saved += 1
    return saved, warnings


async def process_minsa_record(
    conn: asyncpg.Connection, record: MinsaRecord, importer: UUID, facilities: FacilityResolver, scope: Optional[Scope]
) -> tuple[str, Pregnancy, int, list[str]]:
    facility_id = await facilities.resolve(record)
    first, last = split_name(record.get("full_name"))
    dni = re.sub(r"\D", "", record.get("dni"))
    existing = await pregnancyRepository.find_for_import(
        conn, dni if len(dni) == 8 else None, facility_id, record.get("clinical_record") or None, first, last
    )
    if existing is not None and not in_scope(existing.health_facility_id, scope):
        raise ForbiddenError("La gestante ya esta registrada en un EE.SS. que no esta a tu cargo")

    p = existing or Pregnancy(
        id=None, first_names="", last_names="", birth_date=None, health_facility_id=None, registered_by=importer
    )
    warnings = list(record.warnings) + fill(p, record, facility_id)
    normalize(p)
    validate(p)
    if existing is None:
        p.id = await pregnancyRepository.create(conn, p)
        action = "inserted"
    else:
        await pregnancyRepository.update(conn, p)
        action = "updated"
    saved, control_warnings = await save_controls(conn, p, record, importer)
    return action, p, saved, warnings + control_warnings
