import re
import secrets
from typing import Any, Optional

import asyncpg

from ....core.db.connection import connection, transaction
from ....core.http.app_error import ValidationError
from ....core.http.validation import clean
from ..domain.minsa_format import item_label
from ..domain.minsa_template import DEFAULT_TEMPLATE, Template, TemplateColumn, default_template
from ..repositories.minsa_template_repositories import minsaTemplateRepository

HEX = re.compile(r"^[0-9A-F]{6}$")


def _fill(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip().lstrip("#").upper()
    if not HEX.match(value):
        raise ValidationError(f"Color invalido: {value[:10]} (usa #RRGGBB)")
    return value


class MinsaTemplateService:
    async def get(self, conn: Optional[asyncpg.Connection] = None) -> Template:
        if conn is None:
            async with connection() as own:
                return await self.get(own)
        defs = await minsaTemplateRepository.get_all(conn)
        return Template(defs) if defs else DEFAULT_TEMPLATE

    async def definitions(self) -> dict:
        template = await self.get()
        return {"columns": [d.to_dict() for d in template.defs], "customized": template is not DEFAULT_TEMPLATE}

    async def update(self, items: list[dict[str, Any]]) -> dict:
        current = {d.key: d for d in (await self.get()).defs}
        builtin = {d.key for d in default_template()}
        seen: set[str] = set()
        out: list[TemplateColumn] = []
        errors: list[str] = []
        for position, item in enumerate(items):
            key = (item.get("key") or "").strip()
            base = current.get(key)
            if key and base is None and key not in builtin:
                errors.append(f"Columna desconocida: {key}")
                continue
            if key in seen:
                errors.append(f"Columna repetida: {key}")
                continue
            section = clean(item.get("section")) or (base.section if base else "")
            label = clean(item.get("label")) or ""
            group = clean(item.get("group")) or ""
            if not section:
                errors.append(f"Fila {position + 1}: la seccion es obligatoria")
                continue
            if base is None:
                if not label:
                    errors.append(f"Fila {position + 1}: la columna nueva necesita un nombre")
                    continue
                key = f"c:x{secrets.token_hex(4)}"
                base = TemplateColumn(
                    key, "custom", position, section, group, label, match_section=section,
                    match_label=item_label(section, group, label), occ=1,
                )
            seen.add(key)
            if base.kind != "custom" and item.get("kind") not in (None, base.kind):
                errors.append(f"{key}: no se puede cambiar el tipo de una columna del formato")
            aliases = [a.strip()[:200] for a in (item.get("aliases") or []) if a and a.strip()][:10]
            fills = tuple(_fill(f) for f in (list(item.get("fills") or []) + [None, None, None])[:3])
            width = int(item.get("width") or base.width)
            out.append(
                TemplateColumn(
                    key=key, kind=base.kind, position=position, section=section[:150], group=group[:150],
                    label=label[:200], width=max(4, min(60, width)),
                    visible=True if base.kind == "id" else bool(item.get("visible", True)),
                    fills=fills, aliases=aliases, match_section=base.match_section, match_label=base.match_label,
                    occ=base.occ,
                )
            )
        missing = builtin - seen
        if missing:
            errors.append(f"No se pueden borrar columnas del formato original (ocultalas): {', '.join(sorted(missing)[:5])}")
        if errors:
            raise ValidationError(errors[:20])
        async with transaction() as conn:
            await minsaTemplateRepository.replace_all(conn, out)
        return await self.definitions()

    async def reset(self) -> dict:
        async with transaction() as conn:
            await minsaTemplateRepository.clear(conn)
        return await self.definitions()


minsaTemplateService = MinsaTemplateService()
