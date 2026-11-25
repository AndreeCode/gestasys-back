import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from ....core.http.app_error import ValidationError

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

MAX_MEMBERS = 2000
MAX_UNCOMPRESSED = 80 * 1024 * 1024
MAX_MEMBER = 40 * 1024 * 1024
MAX_SHEETS = 30
MAX_COLUMNS = 400
EXCEL_EPOCH = date(1899, 12, 30)


DRAWING_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
THEME_ORDER = ["lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"]
WHITE = "FFFFFF"


@dataclass
class XlsxSheet:
    name: str
    rows: dict[int, dict[int, str]] = field(default_factory=dict)
    fills: dict[int, dict[int, str]] = field(default_factory=dict)

    def cell(self, row: int, col: int) -> str:
        return self.rows.get(row, {}).get(col, "")

    def fill(self, row: int, col: int) -> Optional[str]:
        return self.fills.get(row, {}).get(col)


def _apply_tint(rgb: str, tint: float) -> str:
    out = ""
    for i in (0, 2, 4):
        c = int(rgb[i:i + 2], 16)
        c = c * (1 + tint) if tint < 0 else c + (255 - c) * tint
        out += f"{max(0, min(255, round(c))):02X}"
    return out


def _theme_colors(z: zipfile.ZipFile, names: set[str]) -> list[str]:
    path = next((n for n in names if n.startswith("xl/theme/") and n.endswith(".xml")), None)
    if path is None:
        return []
    scheme = {}
    for node in _parse(_read(z, path)).iter():
        tag = node.tag.replace(DRAWING_NS, "")
        if tag in THEME_ORDER:
            child = next(iter(node), None)
            if child is not None:
                scheme[tag] = (child.get("lastClr") or child.get("val") or "")[-6:].upper()
    return [scheme.get(name, "") for name in THEME_ORDER]


def _color(node, theme: list[str]) -> Optional[str]:
    if node is None:
        return None
    rgb = node.get("rgb")
    if rgb:
        rgb = rgb[-6:].upper()
    elif node.get("theme") is not None:
        index = int(node.get("theme"))
        rgb = theme[index] if index < len(theme) else None
    if not rgb or not re.fullmatch(r"[0-9A-F]{6}", rgb):
        return None
    tint = node.get("tint")
    return _apply_tint(rgb, float(tint)) if tint else rgb


def _style_fills(z: zipfile.ZipFile, names: set[str]) -> list[Optional[str]]:
    if "xl/styles.xml" not in names:
        return []
    styles = _parse(_read(z, "xl/styles.xml"))
    theme = _theme_colors(z, names)
    fills: list[Optional[str]] = []
    fills_node = styles.find(NS + "fills")
    for f in fills_node if fills_node is not None else []:
        pattern = f.find(NS + "patternFill")
        color = None
        if pattern is not None and pattern.get("patternType") not in (None, "none"):
            color = _color(pattern.find(NS + "fgColor"), theme)
        fills.append(None if color == WHITE else color)
    out: list[Optional[str]] = []
    xfs = styles.find(NS + "cellXfs")
    for xf in xfs if xfs is not None else []:
        index = int(xf.get("fillId") or 0)
        out.append(fills[index] if index < len(fills) else None)
    return out


def column_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref)
    if letters is None:
        raise ValidationError("El Excel tiene una referencia de celda invalida")
    n = 0
    for ch in letters.group():
        n = n * 26 + ord(ch) - 64
    return n


def column_letter(index: int) -> str:
    out = ""
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def excel_date(value: str) -> Optional[date]:
    try:
        serial = float(value)
    except (TypeError, ValueError):
        return None
    if not 20000 <= serial <= 80000:
        return None
    return EXCEL_EPOCH + timedelta(days=int(serial))


def _read(z: zipfile.ZipFile, name: str) -> bytes:
    info = z.getinfo(name)
    if info.file_size > MAX_MEMBER:
        raise ValidationError("El Excel contiene una hoja demasiado grande")
    data = z.read(name)
    if b"<!DOCTYPE" in data[:2048] or b"<!ENTITY" in data[:4096]:
        raise ValidationError("El Excel contiene XML no permitido")
    return data


def _parse(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        raise ValidationError("El Excel esta danado o no es un .xlsx valido")


def _target(base: str, target: str) -> str:
    target = target.lstrip("/")
    if target.startswith("xl/"):
        return target
    return base + target


def read_xlsx(data: bytes, max_rows: int) -> list[XlsxSheet]:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValidationError("El archivo no es un Excel .xlsx valido (si es .xls antiguo, guardalo como .xlsx)")
    infos = z.infolist()
    if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
        raise ValidationError("El Excel es demasiado grande una vez descomprimido")
    if any(i.flag_bits & 0x1 for i in infos):
        raise ValidationError("El Excel esta protegido con contrasena: quita la proteccion y vuelve a intentarlo")
    names = set(z.namelist())
    if "xl/workbook.xml" not in names:
        raise ValidationError("El archivo no es un libro de Excel (.xlsx)")

    shared: list[str] = []
    if "xl/sharedStrings.xml" in names:
        for si in _parse(_read(z, "xl/sharedStrings.xml")).iter(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))

    rels = {}
    if "xl/_rels/workbook.xml.rels" in names:
        for rel in _parse(_read(z, "xl/_rels/workbook.xml.rels")).iter(PKG_REL_NS + "Relationship"):
            rels[rel.get("Id")] = rel.get("Target") or ""

    style_fills = _style_fills(z, names)
    workbook = _parse(_read(z, "xl/workbook.xml"))
    sheets: list[XlsxSheet] = []
    total_rows = 0
    for sheet in workbook.iter(NS + "sheet"):
        if sheet.get("state") in ("hidden", "veryHidden"):
            continue
        if len(sheets) >= MAX_SHEETS:
            raise ValidationError(f"El Excel tiene mas de {MAX_SHEETS} hojas")
        path = _target("xl/", rels.get(sheet.get(REL_NS + "id"), ""))
        if path not in names:
            continue
        out = XlsxSheet(name=(sheet.get("name") or "Hoja")[:60])
        for row in _parse(_read(z, path)).iter(NS + "row"):
            cells: dict[int, str] = {}
            colors: dict[int, str] = {}
            for c in row.findall(NS + "c"):
                ref = c.get("r")
                if not ref:
                    continue
                col = column_index(ref)
                if col > MAX_COLUMNS:
                    continue
                style = int(c.get("s") or 0)
                if style < len(style_fills) and style_fills[style]:
                    colors[col] = style_fills[style]
                kind = c.get("t")
                if kind == "inlineStr":
                    value = "".join(t.text or "" for t in c.iter(NS + "t"))
                else:
                    v = c.find(NS + "v")
                    if v is None or v.text is None:
                        continue
                    value = v.text
                    if kind == "s":
                        try:
                            value = shared[int(value)]
                        except (ValueError, IndexError):
                            continue
                value = value.replace("\r", " ").strip()
                if value:
                    cells[col] = value
            number = int(row.get("r") or 0)
            if colors:
                out.fills[number] = colors
            if cells:
                total_rows += 1
                if total_rows > max_rows + 50 * MAX_SHEETS:
                    raise ValidationError(f"El Excel supera el maximo de {max_rows} filas por importacion")
                out.rows[number] = cells
        sheets.append(out)
    if not sheets:
        raise ValidationError("El Excel no tiene hojas con datos")
    return sheets
