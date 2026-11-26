from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import UploadFile
from fastapi.responses import Response

from ....core.config.config import config
from ....core.http.app_error import AppError, ValidationError
from ....core.http.list import list_response
from ....core.http.success import success
from ....core.http.uuid_param import parse_uuid
from ....core.security.facility_scope import Scope
from ...pregnancy.domain.pregnancy_domain import PregnancyFilter
from ..services.data_import_service import dataImportService, sanitize_file_name
from ..services.minsa_edit_service import minsaEditService


class DataImportHandler:
    async def import_file(self, importer: UUID, scope: Optional[Scope], file: UploadFile, dry_run: bool):
        name = sanitize_file_name(file.filename)
        lower = name.lower()
        if not lower.endswith((".csv", ".txt", ".xlsx")):
            raise ValidationError("Solo se aceptan archivos .csv o Excel .xlsx (formato MINSA)")
        data = await file.read(config.import_max_bytes + 1)
        if len(data) > config.import_max_bytes:
            raise AppError(413, f"El archivo supera el maximo de {config.import_max_bytes // 1024 // 1024} MB")

        if lower.endswith(".xlsx"):
            result = await dataImportService.import_minsa(importer, name, data, dry_run, scope)
        else:
            result = await dataImportService.import_csv(importer, name, data, dry_run, scope)
        counts = f"{result.inserted} nuevos, {result.updated} actualizados, {result.failed} con errores"
        if result.format == "minsa_xlsx":
            counts += f", {result.controls} controles"
            if result.warnings:
                counts += f", {result.warnings} avisos"
        if dry_run:
            return success(200, f"Validacion completada (no se guardo nada): {counts}", result.to_dict())
        return success(201, f"Importacion completada: {counts}", result.to_dict())

    async def export(self, f: PregnancyFilter, delimiter: str | None):
        content, total = await dataImportService.export_csv(f, ";" if delimiter in (";", "semicolon") else ",")
        file_name = f"registros-{datetime.now():%Y%m%d-%H%M}.csv"
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{file_name}"', "X-Total-Count": str(total)},
        )

    async def export_minsa(self, f: PregnancyFilter, sections: Optional[list[str]]):
        content, total = await dataImportService.export_minsa(f, set(sections) | {"datos"} if sections else None)
        file_name = f"gestantes-minsa-{datetime.now():%Y%m%d-%H%M}.xlsx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{file_name}"', "X-Total-Count": str(total)},
        )

    async def minsa_view(self, f: PregnancyFilter, sections: Optional[list[str]], limit: int, offset: int):
        data = await dataImportService.minsa_view(f, set(sections) | {"datos"} if sections else None, limit, offset)
        total = data.pop("total")
        return list_response(
            200, "Vista en formato MINSA obtenida correctamente", data, {"total": total, "limit": limit, "offset": offset}
        )

    async def update_minsa(
        self, pregnancy_id: str, cells: dict[str, str], scope: Optional[Scope], user_id: UUID, can_controls: bool
    ):
        pid = parse_uuid(pregnancy_id, "pregnancy_id")
        await minsaEditService.update_cells(pid, cells, scope, user_id, can_controls)
        row = await dataImportService.minsa_row(pid, scope)
        return success(200, f"Registro {row['code']} actualizado ({len(cells)} celdas)", row)

    async def create_minsa(
        self, cells: dict[str, str], facility_id: Optional[UUID], scope: Optional[Scope], user_id: UUID, can_controls: bool
    ):
        pid = await minsaEditService.create_from_cells(dict(cells), facility_id, scope, user_id, can_controls)
        row = await dataImportService.minsa_row(pid, scope)
        return success(201, f"Registro {row['code']} creado con el formato MINSA", row)

    def template(self):
        return Response(
            content=dataImportService.template_csv(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="plantilla-registros.csv"'},
        )

    async def get_all(self, limit: int, offset: int, only_by: Optional[UUID] = None, scope: Optional[Scope] = None):
        items, total = await dataImportService.get_all(limit, offset, only_by, scope)
        return list_response(
            200,
            "Importaciones obtenidas correctamente",
            [i.to_dict() for i in items],
            {"total": total, "limit": limit, "offset": offset},
        )

    async def get_by_id(self, import_id: str, only_by: Optional[UUID] = None):
        item = await dataImportService.get_by_id(parse_uuid(import_id, "import_id"), only_by)
        return success(200, "Importacion obtenida correctamente", item.to_dict())


dataImportHandler = DataImportHandler()
