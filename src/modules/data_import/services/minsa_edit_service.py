import re
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

import asyncpg

from ....core.db.connection import transaction
from ....core.http.app_error import ForbiddenError, NotFoundError, ValidationError
from ....core.security.facility_scope import Scope, in_scope
from ...pregnancy.domain.pregnancy_domain import (
    GESTATION_DAYS,
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
from ..domain.minsa_format import clean_phone, parse_any_date, parse_formula, parse_weeks, split_name, item_label
from ..domain.minsa_template import APN_COUNT, SECTION_COLUMNS, build_columns

COLUMNS = {c.key: c for c in build_columns(None)}
TEXT_FIELDS = {
    "f:address": ("address", None),
    "f:clinical_record": ("clinical_record", 30),
    "f:insurance": ("insurance", 60),
    "f:province": ("province", 100),
    "f:district": ("district", 100),
    "f:locality": ("locality", 150),
}


def _date(label: str, value: str, errors: list[str], required: bool = False) -> Optional[date]:
    if not value:
        if required:
            errors.append(f"{label}: es obligatoria")
        return None
    parsed = parse_any_date(value)
    if parsed is None:
        errors.append(f"{label}: '{value[:20]}' no es una fecha (usa DD/MM/AAAA)")
    return parsed


def _apply_fields(p: Pregnancy, cells: dict[str, str], errors: list[str]) -> None:
    for key, raw in cells.items():
        value = raw.strip()
        label = COLUMNS[key].label
        if key == "f:full_name":
            first, last = split_name(value)
            if not first:
                errors.append("APELLIDOS Y NOMBRES: escribe al menos un apellido y un nombre")
            else:
                p.first_names, p.last_names = first, last
        elif key == "f:dni":
            digits = re.sub(r"\D", "", value)
            if value and len(digits) != 8:
                errors.append("DNI: debe tener 8 digitos")
            p.dni = digits or None
        elif key == "f:birth_date":
            parsed = _date(label, value, errors, required=True)
            if parsed:
                p.birth_date, p.birth_date_estimated = parsed, False
        elif key == "f:phone":
            p.phone = clean_phone(value) or (value[:30] or None)
        elif key == "f:formula":
            p.obstetric_formula = value[:30] or None
            gravida, parity = parse_formula(value)
            if value and gravida is None:
                errors.append("FORMULA OBSTETRICA: usa el formato G1 P0000")
            p.gravida, p.parity = gravida, parity
        elif key == "f:lmp":
            p.last_menstrual_period = _date(label, value, errors)
            if "f:edd" not in cells:
                p.expected_delivery_date = (
                    p.last_menstrual_period + timedelta(days=GESTATION_DAYS) if p.last_menstrual_period else None
                )
        elif key == "f:edd":
            p.expected_delivery_date = _date(label, value, errors)
        elif key in TEXT_FIELDS:
            attr, size = TEXT_FIELDS[key]
            setattr(p, attr, (value[:size] if size else value) or None)


def _apply_clinical(p: Pregnancy, cells: dict[str, str]) -> Optional[tuple[bool, Optional[date]]]:
    sections = [dict(s, items=list(s.get("items", []))) for s in (p.clinical_data or [])]
    termination = None
    for key, raw in cells.items():
        index = int(key.split(":", 1)[1])
        section, group, label = SECTION_COLUMNS[index]
        target_label = item_label(section, group, label)
        occurrence = sum(
            1
            for s, g, lab in SECTION_COLUMNS[: index + 1]
            if fold(s) == fold(section) and fold(item_label(s, g, lab)) == fold(target_label)
        )
        value = raw.strip()[:1000]
        block = next((s for s in sections if fold(s.get("section", "")) == fold(section)), None)
        if block is None:
            block = {"section": section, "items": []}
            sections.append(block)
        seen = 0
        found = None
        for item in block["items"]:
            if fold(item.get("label", "")) == fold(target_label):
                seen += 1
                if (item.get("occ") or seen) == occurrence:
                    found = item
                    break
        if found is not None:
            if value or found.get("color"):
                found["value"] = value
            else:
                block["items"].remove(found)
        elif value:
            block["items"].append({"label": target_label, "value": value, "occ": occurrence})
        if "terminacion" in fold(section) and fold(target_label).endswith("fecha"):
            termination = (True, parse_any_date(value) if value else None)
    p.clinical_data = [s for s in sections if s["items"]]
    return termination


async def _controls(conn: asyncpg.Connection, pregnancy_id: UUID) -> dict[int, PrenatalControl]:
    controls = await prenatalControlRepository.get_all(conn, pregnancy_id, None, None)
    ordered = sorted(controls, key=lambda c: (c.control_date, c.created_at))
    out: dict[int, PrenatalControl] = {}
    pending = []
    for c in ordered:
        if c.control_number and 1 <= c.control_number <= APN_COUNT and c.control_number not in out:
            out[c.control_number] = c
        else:
            pending.append(c)
    free = (n for n in range(1, APN_COUNT + 1) if n not in out)
    for c in pending:
        n = next(free, None)
        if n is None:
            break
        out[n] = c
    return out


async def _apply_controls(
    conn: asyncpg.Connection, p: Pregnancy, cells: dict[str, str], user_id: UUID, errors: list[str]
) -> None:
    by_number: dict[int, dict[str, str]] = {}
    for key, value in cells.items():
        _, n, part = key.split(":")
        by_number.setdefault(int(n), {})[part] = value.strip()
    existing = await _controls(conn, p.id)
    today = date.today()
    for n, parts in sorted(by_number.items()):
        label = f"APN {n}"
        current = existing.get(n)
        raw_date = parts.get("date", current.control_date.strftime("%d/%m/%Y") if current else "")
        if not raw_date:
            if current is not None:
                await prenatalControlRepository.delete(conn, current.id)
            continue
        control_date = _date(f"{label} fecha", raw_date, errors)
        if control_date is None:
            continue
        c = current or PrenatalControl(id=None, pregnancy_id=p.id, control_date=control_date, registered_by=user_id)
        c.control_date = control_date
        if "weeks" in parts:
            c.gestational_weeks = parse_weeks(parts["weeks"]) if parts["weeks"] else None
            if parts["weeks"] and c.gestational_weeks is None:
                errors.append(f"{label} edad gestacional: debe estar entre 0 y 45 semanas")
        if "next" in parts:
            c.next_appointment = _date(f"{label} cita", parts["next"], errors)
        for part, size in (("supplementation", 60), ("risk_factor", 500), ("performed_at", 150)):
            if part in parts:
                setattr(c, part, parts[part][:size] or None)
        if control_date > today:
            errors.append(f"{label}: la fecha no puede estar en el futuro")
        if p.last_menstrual_period and control_date < p.last_menstrual_period:
            errors.append(f"{label}: la fecha es anterior a la FUM")
        if c.next_appointment and c.next_appointment < control_date:
            errors.append(f"{label}: la cita debe ser igual o posterior al control")
        if c.gestational_weeks is None and p.last_menstrual_period and control_date >= p.last_menstrual_period:
            c.gestational_weeks = round((control_date - p.last_menstrual_period).days / 7, 1)
        if errors:
            continue
        if current is None:
            c.control_number = n
            await prenatalControlRepository.create(conn, c)
        else:
            await prenatalControlRepository.update(conn, c)
            await conn.execute("UPDATE prenatal_controls SET control_number = $2 WHERE id = $1", c.id, n)


class MinsaEditService:
    async def update_cells(
        self, pregnancy_id: UUID, cells: dict[str, str], scope: Optional[Scope], user_id: UUID, can_controls: bool
    ) -> None:
        unknown = [k for k in cells if k not in COLUMNS or not COLUMNS[k].editable]
        if unknown:
            raise ValidationError(f"Estas columnas no se editan aqui: {', '.join(unknown[:5])}")
        groups = {
            "f": {k: v for k, v in cells.items() if k.startswith("f:")},
            "apn": {k: v for k, v in cells.items() if k.startswith("apn:")},
            "c": {k: v for k, v in cells.items() if k.startswith("c:")},
        }
        if groups["apn"] and not can_controls:
            raise ForbiddenError("No tienes permiso para editar controles prenatales")

        errors: list[str] = []
        async with transaction() as conn:
            p = await pregnancyRepository.get_by_id(conn, pregnancy_id)
            if p is None or not p.active or not in_scope(p.health_facility_id, scope):
                raise NotFoundError("Registro de gestante no encontrado")
            _apply_fields(p, groups["f"], errors)
            termination = _apply_clinical(p, groups["c"]) if groups["c"] else None
            if termination:
                _, delivered = termination
                if delivered:
                    p.status, p.delivery_date = STATUS_COMPLETED, delivered
                elif p.status == STATUS_COMPLETED:
                    p.delivery_date = None
                    p.status = STATUS_IN_FOLLOWUP if p.controls_count else STATUS_PENDING
            if errors:
                raise ValidationError(errors)
            normalize(p)
            validate(p)
            await pregnancyRepository.update(conn, p)
            if groups["apn"]:
                await _apply_controls(conn, p, groups["apn"], user_id, errors)
                if errors:
                    raise ValidationError(errors)
                if p.status == STATUS_PENDING:
                    count = await conn.fetchval("SELECT count(*) FROM prenatal_controls WHERE pregnancy_id = $1", p.id)
                    if count:
                        await pregnancyRepository.set_status(conn, p.id, STATUS_IN_FOLLOWUP)


minsaEditService = MinsaEditService()
