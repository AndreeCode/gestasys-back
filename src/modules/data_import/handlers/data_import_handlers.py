from datetime import datetime
from uuid import UUID

from fastapi import UploadFile
from fastapi.responses import Response

from ....core.config.config import config
from ....core.http.app_error import AppError, ValidationError
from ....core.http.list import list_response
from ....core.http.success import success
from ....core.http.uuid_param import parse_uuid
from ...pregnancy.domain.pregnancy_domain import PregnancyFilter
from ..services.data_import_service import dataImportService, sanitize_file_name


class DataImportHandler:
    async def import_file(self, importer: UUID, file: UploadFile, dry_run: bool):
        name = sanitize_file_name(file.filename)
        if not name.lower().endswith((".csv", ".txt")):
            raise ValidationError("Solo se aceptan archivos .csv")
        data = await file.read(config.import_max_bytes + 1)
        if len(data) > config.import_max_bytes:
            raise AppError(413, f"El archivo supera el maximo de {config.import_max_bytes // 1024 // 1024} MB")

        result = await dataImportService.import_csv(importer, name, data, dry_run)
        counts = f"{result.inserted} nuevos, {result.updated} actualizados, {result.failed} con errores"
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

    def template(self):
        return Response(
            content=dataImportService.template_csv(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="plantilla-registros.csv"'},
        )

    async def get_all(self, limit: int, offset: int):
        items, total = await dataImportService.get_all(limit, offset)
        return list_response(
            200,
            "Importaciones obtenidas correctamente",
            [i.to_dict() for i in items],
            {"total": total, "limit": limit, "offset": offset},
        )

    async def get_by_id(self, import_id: str):
        item = await dataImportService.get_by_id(parse_uuid(import_id, "import_id"))
        return success(200, "Importacion obtenida correctamente", item.to_dict())


dataImportHandler = DataImportHandler()
