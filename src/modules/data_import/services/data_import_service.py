import os
from datetime import date
from typing import Callable, Optional
from uuid import UUID

import asyncpg

from ....core.db.connection import connection, transaction
from ....core.http.app_error import AppError, NotFoundError, ValidationError
from ....core.http.exception_handlers import describe_db_error
from ....core.security.facility_scope import Scope, ids, in_scope
from ....core.logger.logger import logger
from ...health_facility.repositories.health_facility_repositories import healthFacilityRepository
from ...pregnancy.domain.pregnancy_domain import STATUS_COMPLETED, Pregnancy, PregnancyFilter
from ...pregnancy.repositories.pregnancy_repositories import pregnancyRepository
from ...pregnancy.services.pregnancy_service import pregnancyService
from ..domain.csv_format import (
    EXPORT_COLUMNS,
    RISK_LABELS,
    STATUS_LABELS,
    TEMPLATE_COLUMNS,
    Sheet,
    fold,
    parse_date,
    parse_int,
    parse_risk,
    parse_status,
    read_sheet,
    write_csv,
)
from ..domain.data_import_domain import DataImport
from ..domain.minsa_format import read_minsa
from ..domain.colors import color_name
from ..domain.minsa_template import Template
from .minsa_template_service import minsaTemplateService
from ..domain.xlsx_writer import SheetSpec, write_minsa_xlsx
from ...prenatal_control.repositories.prenatal_control_repositories import prenatalControlRepository
from ..domain.xlsx_reader import read_xlsx
from ..repositories.data_import_repositories import dataImportRepository
from .minsa_import_service import FacilityResolver, process_minsa_record

MAX_ROWS = 20000


class DryRunRollback(Exception):
    pass


class FacilityCache:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn
        self.cache: dict[str, object] = {}

    async def resolve(self, value: str) -> UUID:
        key = fold(value)
        if key not in self.cache:
            self.cache[key] = await healthFacilityRepository.find_by_code_or_name(self.conn, value)
        facility = self.cache[key]
        if facility is None:
            raise ValueError(f"establecimiento '{value}' no existe (usa el codigo o el nombre registrado)")
        if not facility.active:
            raise ValueError(f"establecimiento '{value}' esta inactivo")
        return facility.id


async def apply_row(sheet: Sheet, row: list[str], p: Pregnancy, facilities: FacilityCache) -> None:
    errors: list[str] = []

    def value(key: str) -> str:
        return sheet.get(row, key) if sheet.has(key) else ""

    simple: dict[str, tuple[str, Callable]] = {
        "dni": ("dni", str),
        "nombres": ("first_names", str),
        "apellidos": ("last_names", str),
        "fecha_nacimiento": ("birth_date", lambda v: parse_date("fecha_nacimiento", v)),
        "telefono": ("phone", str),
        "direccion": ("address", str),
        "fum": ("last_menstrual_period", lambda v: parse_date("fum", v)),
        "fpp": ("expected_delivery_date", lambda v: parse_date("fpp", v)),
        "gestas": ("gravida", lambda v: parse_int("gestas", v)),
        "partos": ("parity", lambda v: parse_int("partos", v)),
        "riesgo": ("risk_level", parse_risk),
        "estado": ("status", parse_status),
        "fecha_parto": ("delivery_date", lambda v: parse_date("fecha_parto", v)),
        "observaciones": ("notes", str),
    }
    for column, (attr, parse) in simple.items():
        raw = value(column)
        if raw:
            try:
                setattr(p, attr, parse(raw))
            except ValueError as err:
                errors.append(str(err))

    raw = value("establecimiento")
    if raw:
        try:
            p.health_facility_id = await facilities.resolve(raw)
        except ValueError as err:
            errors.append(str(err))

    if errors:
        raise ValidationError(errors)


def error_message(err: Exception) -> str:
    if isinstance(err, AppError):
        return err.msg
    if isinstance(err, asyncpg.PostgresError):
        return describe_db_error(err)[1]
    logger.error(f"Error inesperado al importar una fila: {err}", exc_info=err)
    return "Error inesperado al guardar la fila"


async def process_row(
    conn, sheet: Sheet, row: list[str], importer: UUID, facilities: FacilityCache, scope: Optional[Scope] = None
) -> tuple[str, str]:
    code = sheet.get(row, "codigo").upper()
    dni = sheet.get(row, "dni")

    existing = None
    if code:
        existing = await pregnancyRepository.get_by_code(conn, code)
        if existing is None or not in_scope(existing.health_facility_id, scope):
            raise AppError(400, f"No existe un registro con el codigo {code} (deja la columna vacia para crear uno nuevo)")
    elif dni:
        existing = await pregnancyRepository.get_open_by_dni(conn, dni)
        if existing is not None and not in_scope(existing.health_facility_id, scope):
            raise AppError(409, f"El DNI {dni} ya tiene un registro abierto en otro establecimiento")

    if existing is not None:
        before = existing.health_facility_id
        await apply_row(sheet, row, existing, facilities)
        if existing.status != STATUS_COMPLETED and not sheet.get(row, "fecha_parto"):
            existing.delivery_date = None
        if sheet.get(row, "fum") and not sheet.get(row, "fpp"):
            existing.expected_delivery_date = None
        await pregnancyService.update_in(conn, existing, existing.health_facility_id != before, scope)
        return "updated", existing.code

    p = Pregnancy(id=None, first_names="", last_names="", birth_date=None, health_facility_id=None, registered_by=importer)
    await apply_row(sheet, row, p, facilities)
    await pregnancyService.create_in(conn, p, scope)
    return "inserted", p.code


def sanitize_file_name(name: str | None) -> str:
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    return (name or "importacion.csv")[:200]


class DataImportService:
    async def get_all(
        self, limit: int, offset: int, only_by: Optional[UUID] = None, scope: Optional[Scope] = None
    ) -> tuple[list[DataImport], int]:
        network = scope.micro_network_id if scope is not None else None
        async with connection() as conn:
            return await dataImportRepository.get_all(conn, limit, offset, only_by, ids(scope), network)

    async def get_by_id(self, import_id: UUID, only_by: Optional[UUID] = None) -> DataImport:
        async with connection() as conn:
            item = await dataImportRepository.get_by_id(conn, import_id)
        if item is None or (only_by is not None and item.imported_by != only_by):
            raise NotFoundError("Importacion no encontrada")
        return item

    async def import_csv(
        self, importer: UUID, file_name: str, data: bytes, dry_run: bool, scope: Optional[Scope] = None
    ) -> DataImport:
        sheet = read_sheet(data, MAX_ROWS)
        result = DataImport(id=None, file_name=file_name, total_rows=len(sheet.rows), dry_run=dry_run, imported_by=importer)

        try:
            async with transaction() as conn:
                facilities = FacilityCache(conn)
                for row, line in zip(sheet.rows, sheet.lines):
                    savepoint = conn.transaction()
                    await savepoint.start()
                    try:
                        action, code = await process_row(conn, sheet, row, importer, facilities, scope)
                    except Exception as err:
                        await savepoint.rollback()
                        result.failed += 1
                        entry = {"line": line, "message": error_message(err)}
                        if sheet.get(row, "codigo"):
                            entry["code"] = sheet.get(row, "codigo").upper()
                        result.errors.append(entry)
                        continue
                    await savepoint.commit()
                    if action == "inserted":
                        result.inserted += 1
                    else:
                        result.updated += 1
                if dry_run:
                    raise DryRunRollback()
                saved = await dataImportRepository.create(conn, result)
                result.id, result.created_at = saved["id"], saved["created_at"]
        except DryRunRollback:
            pass
        return result

    async def import_minsa(
        self, importer: UUID, file_name: str, data: bytes, dry_run: bool, scope: Optional[Scope] = None
    ) -> DataImport:
        records = read_minsa(read_xlsx(data, MAX_ROWS), MAX_ROWS)
        result = DataImport(
            id=None, file_name=file_name, total_rows=len(records), dry_run=dry_run, imported_by=importer,
            format="minsa_xlsx",
        )
        touched: list[UUID] = []
        try:
            async with transaction() as conn:
                facilities = FacilityResolver(conn, scope)
                for record in records:
                    location = {"sheet": record.sheet, "line": record.row}
                    savepoint = conn.transaction()
                    await savepoint.start()
                    try:
                        action, p, controls, warnings = await process_minsa_record(
                            conn, record, importer, facilities, scope
                        )
                    except Exception as err:
                        await savepoint.rollback()
                        result.failed += 1
                        result.errors.append({**location, "level": "error", "message": error_message(err)})
                        continue
                    await savepoint.commit()
                    touched.append(p.id)
                    result.controls += controls
                    if action == "inserted":
                        result.inserted += 1
                    else:
                        result.updated += 1
                    for warning in warnings:
                        result.warnings += 1
                        result.errors.append({**location, "code": p.code, "level": "warning", "message": warning})
                result.created_facilities = facilities.created
                if dry_run:
                    raise DryRunRollback()
                saved = await dataImportRepository.create(conn, result)
                result.id, result.created_at = saved["id"], saved["created_at"]
                await dataImportRepository.set_import(conn, result.id, touched)
        except DryRunRollback:
            pass
        return result

    async def _minsa_rows(
        self, conn, items, offset: int, columns, template: Template
    ) -> tuple[list[list[str]], list[list]]:
        ids = [p.id for p in items]
        controls = await prenatalControlRepository.for_pregnancies(conn, ids)
        facilities = {
            row["id"]: dict(row)
            for row in await conn.fetch(
                "SELECT id, renaes, province, district FROM health_facilities WHERE id = ANY($1::uuid[])",
                list({p.health_facility_id for p in items}),
            )
        }
        rows, fills = [], []
        for i, p in enumerate(items, start=offset + 1):
            data = p.to_dict()
            facility = facilities.get(p.health_facility_id, {})
            data["renaes"] = facility.get("renaes")
            data["facility_province"] = facility.get("province")
            data["facility_district"] = facility.get("district")
            rows.append(template.row_values(i, data, controls.get(p.id, []), columns))
            fills.append(template.row_fills(data, columns))
        return rows, fills

    async def minsa_view(self, f: PregnancyFilter, sections: Optional[set[str]], limit: int, offset: int) -> dict:
        async with connection() as conn:
            template = await minsaTemplateService.get(conn)
            columns = template.build_columns(sections)
            items, total = await pregnancyRepository.get_all(conn, f, limit, offset)
            rows, fills = await self._minsa_rows(conn, items, offset, columns, template)
        colors = sorted({c for row in fills for c in row if c})
        return {
            "sections": template.section_list(),
            "columns": [
                {
                    "key": c.key, "section": c.section, "group": c.group, "label": c.label,
                    "fills": list(c.fills), "editable": c.editable,
                }
                for c in columns
            ],
            "rows": rows,
            "fills": fills,
            "legend": [{"color": c, "name": color_name(c)} for c in colors],
            "ids": [str(p.id) for p in items],
            "codes": [p.code for p in items],
            "total": total,
        }

    async def minsa_row(self, pregnancy_id: UUID, scope: Optional[Scope]) -> dict:
        async with connection() as conn:
            template = await minsaTemplateService.get(conn)
            columns = template.build_columns(None)
            p = await pregnancyRepository.get_by_id(conn, pregnancy_id)
            if p is None or not in_scope(p.health_facility_id, scope):
                raise NotFoundError("Registro de gestante no encontrado")
            rows, fills = await self._minsa_rows(conn, [p], 0, columns, template)
        return {"id": str(p.id), "code": p.code, "keys": [c.key for c in columns], "row": rows[0], "fills": fills[0]}

    async def export_minsa(self, f: PregnancyFilter, sections: Optional[set[str]]) -> tuple[bytes, int]:
        async with connection() as conn:
            template = await minsaTemplateService.get(conn)
            columns = template.build_columns(sections)
            items = await pregnancyRepository.get_all_unpaged(conn, f)
            if len(items) > MAX_ROWS:
                raise ValidationError(f"Son {len(items)} registros: filtra para exportar como maximo {MAX_ROWS}")
            rows, fills = await self._minsa_rows(conn, items, 0, columns, template)
        today = date.today().strftime("%d/%m/%Y")
        keep = {"n", "f:full_name", "f:dni"}
        marks = [
            [row[i] if c.key in keep else ("1" if fill[i] else "0") for i, c in enumerate(columns)]
            for row, fill in zip(rows, fills)
        ]
        mark_fills = [[None if c.key in keep else fill[i] for i, c in enumerate(columns)] for fill in fills]
        content = write_minsa_xlsx(
            [c.section for c in columns],
            [c.group for c in columns],
            [c.label for c in columns],
            [c.width for c in columns],
            [
                SheetSpec(
                    "Gestantes",
                    f"SEGUIMIENTO DE GESTANTES - FORMATO MINSA ({len(items)} registros, generado {today})",
                    rows,
                    fills,
                ),
                SheetSpec(
                    "Marcas 0-1",
                    f"MARCAS DE COLOR: 1 = celda pintada en el Excel original, 0 = sin color (generado {today})",
                    marks,
                    mark_fills,
                ),
            ],
            header_fills=[c.fills for c in columns],
        )
        return content, len(items)

    async def export_csv(self, f: PregnancyFilter, delimiter: str) -> tuple[bytes, int]:
        async with connection() as conn:
            items = await pregnancyRepository.get_all_unpaged(conn, f)
        rows = []
        for p in items:
            data = p.to_dict()
            ga = data["gestational_age"]
            rows.append([
                p.code, p.dni or "", p.first_names, p.last_names, iso(p.birth_date), p.age if p.age is not None else "",
                p.phone or "", p.address or "", p.health_facility_name or "", iso(p.last_menstrual_period),
                iso(p.expected_delivery_date), f"{ga['weeks']}s {ga['days']}d" if ga else "",
                "" if p.gravida is None else p.gravida, "" if p.parity is None else p.parity,
                RISK_LABELS.get(p.risk_level, p.risk_level), STATUS_LABELS.get(p.status, p.status), iso(p.delivery_date),
                iso(p.last_control_date), iso(p.next_appointment), p.notes or "",
            ])
        return write_csv(EXPORT_COLUMNS, rows, delimiter), len(items)

    def template_csv(self) -> bytes:
        example_lmp = date.fromordinal(date.today().toordinal() - 70).strftime("%d/%m/%Y")
        return write_csv(
            TEMPLATE_COLUMNS,
            [[
                "", "70123456", "Maria Fernanda", "Lopez Quispe", "15/03/1998", "987654321", "Jr. Lima 123",
                "CS-SANMARTIN", example_lmp, "", "2", "1", "Bajo", "Pendiente", "",
                "Deja 'codigo' vacio para crear; con codigo se actualiza",
            ]],
        )


def iso(value) -> str:
    return value.isoformat() if value else ""


dataImportService = DataImportService()
