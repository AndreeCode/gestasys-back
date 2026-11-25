from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from pydantic import Field

from ...core.http.request_models import StrictModel
from ...core.http.success import success
from ...core.security.permission_guard import require_permission
from .services.minsa_template_service import minsaTemplateService

router = APIRouter(prefix="/minsa-template", tags=["minsa-template"])

Text = Annotated[str, Field(max_length=200)]


class TemplateColumnRequest(StrictModel):
    key: Optional[str] = Field(default=None, max_length=40)
    kind: Optional[str] = Field(default=None, max_length=10)
    section: str = Field(max_length=150)
    group: str = Field(default="", max_length=150)
    label: str = Field(default="", max_length=200)
    width: int = Field(default=14, ge=4, le=60)
    visible: bool = True
    fills: list[Optional[Annotated[str, Field(max_length=7)]]] = Field(default_factory=list, max_length=3)
    aliases: list[Text] = Field(default_factory=list, max_length=10)


class TemplateRequest(StrictModel):
    columns: list[TemplateColumnRequest] = Field(min_length=1, max_length=600)


@router.get("", dependencies=[Depends(require_permission("pregnancy.get"))])
async def get_minsa_template():
    return success(200, "Formato MINSA obtenido correctamente", await minsaTemplateService.definitions())


@router.put("", dependencies=[Depends(require_permission("minsa_template.put"))])
async def update_minsa_template(body: TemplateRequest):
    data = await minsaTemplateService.update([c.model_dump() for c in body.columns])
    return success(200, "Formato MINSA guardado: se aplica a la vista, la edicion, la exportacion y la importacion", data)


@router.post("/reset", dependencies=[Depends(require_permission("minsa_template.put"))])
async def reset_minsa_template():
    return success(200, "Formato MINSA restablecido al original", await minsaTemplateService.reset())
