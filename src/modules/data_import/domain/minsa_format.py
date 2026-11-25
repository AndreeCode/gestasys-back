import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from ....core.http.app_error import ValidationError
from .csv_format import fold
from .xlsx_reader import XlsxSheet, column_letter, excel_date

FIELD_HEADERS = {
    "renaes": ("codigo de establecimiento", "renaes"),
    "province": ("provincia",),
    "district": ("distrito",),
    "locality": ("localidad",),
    "micro_network": ("microred",),
    "facility": ("ee. ss.", "ee.ss.", "establecimiento de salud", "eess"),
    "address": ("direccion",),
    "full_name": ("apellidos y nombres",),
    "birth_date": ("fecha de nacimiento",),
    "age": ("edad",),
    "dni": ("dni",),
    "clinical_record": ("historia clinica",),
    "phone": ("celular",),
    "insurance": ("tipo de seguro", "seguro"),
    "formula": ("formula obstetrica",),
    "lmp": ("fum",),
    "edd": ("fpp",),
}

APN_PARTS = ("date", "weeks", "supplementation", "risk_factor", "performed_at", "next")
NAME_PARTICLES = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "SAN", "SANTA"}
EMPTY = {"", "-", "--", "na", "n/a", "no", "ninguno", "ninguna", "no tiene", "nr", "s/d", "sd", "0"}
DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d")
FORMULA_RE = re.compile(r"G\s*(\d{1,2})\s*P\s*(\d)\s*(\d)\s*(\d)\s*(\d)", re.I)


@dataclass
class MinsaControl:
    number: int
    control_date: Optional[date]
    raw_date: str
    gestational_weeks: Optional[float] = None
    supplementation: Optional[str] = None
    risk_factor: Optional[str] = None
    performed_at: Optional[str] = None
    next_appointment: Optional[date] = None


@dataclass
class MinsaRecord:
    sheet: str
    row: int
    values: dict[str, str]
    controls: list[MinsaControl] = field(default_factory=list)
    clinical_data: list[dict] = field(default_factory=list)
    delivery_date: Optional[date] = None
    termination: Optional[str] = None
    observations: Optional[str] = None
    row_color: Optional[str] = None
    cell_marks: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def get(self, key: str) -> str:
        return self.values.get(key, "").strip()


def is_empty(value: str) -> bool:
    return fold(value) in EMPTY


def parse_any_date(value: str) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        return None
    serial = excel_date(value)
    if serial is not None:
        return serial
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_weeks(value: str) -> Optional[float]:
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    if not match:
        return None
    weeks = float(match.group().replace(",", "."))
    return weeks if 0 <= weeks <= 45 else None


def split_name(full_name: str) -> tuple[str, str]:
    tokens = [t for t in re.split(r"\s+", full_name.strip().upper()) if t]
    units: list[str] = []
    buffer: list[str] = []
    for token in tokens:
        buffer.append(token)
        if token not in NAME_PARTICLES:
            units.append(" ".join(buffer))
            buffer = []
    if buffer:
        units.append(" ".join(buffer))
    if len(units) >= 3:
        last, first = units[:2], units[2:]
    elif len(units) == 2:
        last, first = units[:1], units[1:]
    else:
        last, first = units, []
    return " ".join(first).title(), " ".join(last).title()


def parse_formula(value: str) -> tuple[Optional[int], Optional[int]]:
    match = FORMULA_RE.search(value or "")
    if not match:
        return None, None
    gravida = int(match.group(1))
    parity = int(match.group(2)) + int(match.group(3))
    if gravida < 1:
        return None, None
    return gravida, parity if parity < gravida else None


def clean_phone(value: str) -> Optional[str]:
    digits = re.sub(r"\D", "", value or "")
    if digits.endswith("0") and re.fullmatch(r"\d+\.0", (value or "").strip()):
        digits = digits[:-1]
    return digits if 6 <= len(digits) <= 15 else None


def _carry(sheet: XlsxSheet, row: int, max_col: int, reset: set[int] | None = None) -> dict[int, str]:
    out: dict[int, str] = {}
    current = ""
    for col in range(1, max_col + 1):
        value = sheet.cell(row, col)
        if value:
            current = " ".join(value.split())
        elif reset and col in reset:
            current = ""
        out[col] = current
    return out


def _find_header(sheet: XlsxSheet) -> Optional[int]:
    for number in sorted(sheet.rows)[:60]:
        texts = [fold(v) for v in sheet.rows[number].values()]
        if any("apellidos y nombres" in t for t in texts) and any(t == "dni" for t in texts):
            return number
    return None


MARKS_SECTION = "marcas gestasys"


@dataclass
class Layout:
    header_row: int
    fields: dict[str, int]
    apn: list[dict[str, int]]
    sections: dict[int, str]
    groups: dict[int, str]
    labels: dict[int, str]
    max_col: int
    occurrences: dict[int, int] = field(default_factory=dict)
    keys: dict[int, str] = field(default_factory=dict)


def detect_layout(sheet: XlsxSheet) -> Optional[Layout]:
    header_row = _find_header(sheet)
    if header_row is None:
        return None
    max_col = max((max(cells) for cells in sheet.rows.values() if cells), default=0)
    labels = {col: " ".join(sheet.cell(header_row, col).split()) for col in range(1, max_col + 1)}
    sections = _carry(sheet, header_row - 2, max_col)
    starts = {col for col in range(1, max_col + 1) if sheet.cell(header_row - 2, col)}
    groups = _carry(sheet, header_row - 1, max_col, starts)

    fields: dict[str, int] = {}
    first_apn = next((c for c, label in labels.items() if fold(label).startswith("fecha de control")), max_col + 1)
    for col in range(1, first_apn):
        label = fold(labels.get(col, ""))
        if not label:
            continue
        for key, needles in FIELD_HEADERS.items():
            if key in fields:
                continue
            if key == "age" and not label.startswith("edad"):
                continue
            if key == "dni" and label != "dni":
                continue
            if any(needle in label for needle in needles):
                fields[key] = col
                break

    apn: list[dict[str, int]] = []
    col = first_apn
    while col <= max_col and fold(labels.get(col, "")).startswith("fecha de control"):
        apn.append({part: col + i for i, part in enumerate(APN_PARTS)})
        col += len(APN_PARTS)

    missing = [k for k in ("full_name", "facility") if k not in fields]
    if missing:
        raise ValidationError(
            f"La hoja '{sheet.name}' no tiene las columnas obligatorias del formato MINSA: {', '.join(missing)}"
        )
    layout = Layout(header_row, fields, apn, sections, groups, labels, max_col)
    layout.keys[1] = "n"
    for key, col in fields.items():
        layout.keys[col] = f"f:{key}"
    for number, block in enumerate(apn, start=1):
        for part, col in block.items():
            layout.keys[col] = f"apn:{number}:{part}"
    seen: dict[tuple[str, str], int] = {}
    for col in range(1, max_col + 1):
        if col in layout.keys:
            continue
        section = sections.get(col) or "Otros datos"
        key = (fold(section), fold(item_label(section, groups.get(col, ""), labels.get(col, ""), col)))
        seen[key] = seen.get(key, 0) + 1
        layout.occurrences[col] = seen[key]
    return layout


def row_color(sheet: XlsxSheet, row: int, max_col: int) -> Optional[str]:
    colors: dict[str, int] = {}
    for color in sheet.fills.get(row, {}).values():
        colors[color] = colors.get(color, 0) + 1
    if not colors:
        return None
    color, count = max(colors.items(), key=lambda kv: kv[1])
    return color if count >= max(3, max_col * 0.4) else None


def item_label(section: str, group: str, label: str, col: int = 0) -> str:
    label = label or group or "Detalle"
    if group and fold(group) != fold(label) and fold(group) != fold(section):
        label = f"{group} · {label}" if label else group
    return label[:160]


def _looks_like_date_column(section: str, group: str, label: str) -> bool:
    text = fold(f"{section} {group} {label}")
    return any(word in text for word in ("fecha", "dosis", "(dd", "plan de parto", "control (", "1er control", "2do control"))


def parse_record(sheet: XlsxSheet, layout: Layout, row: int) -> MinsaRecord:
    cells = sheet.rows.get(row, {})
    record = MinsaRecord(
        sheet=sheet.name,
        row=row,
        values={key: cells.get(col, "") for key, col in layout.fields.items()},
    )
    record.row_color = row_color(sheet, row, layout.max_col)
    marks = {
        col: color for col, color in sheet.fills.get(row, {}).items() if color != record.row_color and col <= layout.max_col
    }
    for col, color in marks.items():
        if col in layout.keys:
            record.cell_marks[layout.keys[col]] = color

    apn_cols: set[int] = set()
    for number, block in enumerate(layout.apn, start=1):
        apn_cols.update(block.values())
        raw = cells.get(block["date"], "").strip()
        if not raw or is_empty(raw):
            continue
        control = MinsaControl(number=number, control_date=parse_any_date(raw), raw_date=raw)
        control.gestational_weeks = parse_weeks(cells.get(block["weeks"], ""))
        for part in ("supplementation", "risk_factor", "performed_at"):
            value = cells.get(block[part], "").strip()
            if value and not is_empty(value):
                setattr(control, part, " ".join(value.split())[:500])
        control.next_appointment = parse_any_date(cells.get(block["next"], ""))
        if control.control_date is None:
            record.warnings.append(f"APN {number}: fecha '{raw[:20]}' no reconocida, no se registro el control")
        record.controls.append(control)

    used = set(layout.fields.values()) | apn_cols
    grouped: dict[str, list[dict]] = {}
    for col in range(1, layout.max_col + 1):
        if col in used or col == 1:
            continue
        value = cells.get(col, "").strip()
        if not value and col not in marks:
            continue
        section = layout.sections.get(col) or "Otros datos"
        if fold(section) == MARKS_SECTION:
            continue
        group = layout.groups.get(col, "")
        label = item_label(section, group, layout.labels.get(col, ""), col)
        section_key = fold(section)
        shown = value
        if _looks_like_date_column(section, group, label):
            as_date = excel_date(value)
            if as_date is not None:
                shown = as_date.strftime("%d/%m/%Y")
        item = {"label": label, "value": shown[:1000], "column": column_letter(col), "occ": layout.occurrences.get(col, 1)}
        if col in marks:
            item["color"] = marks[col]
        grouped.setdefault(section[:120], []).append(item)

        if "terminacion" in section_key:
            label_key = fold(label)
            if label_key.endswith("fecha") or label_key == "fecha":
                record.delivery_date = record.delivery_date or parse_any_date(value)
            elif "aborto" in label_key or "tipo de parto" in label_key:
                record.termination = (record.termination or value)[:120]
        if "observaciones" in section_key:
            record.observations = value[:2000]

    record.clinical_data = [{"section": name, "items": items} for name, items in grouped.items()]
    return record


def read_minsa(sheets: list[XlsxSheet], max_rows: int) -> list[MinsaRecord]:
    records: list[MinsaRecord] = []
    found = False
    for sheet in sheets:
        if fold(sheet.name).startswith("marcas"):
            continue
        layout = detect_layout(sheet)
        if layout is None:
            continue
        found = True
        name_col = layout.fields["full_name"]
        for row in sorted(r for r in sheet.rows if r > layout.header_row):
            if not sheet.cell(row, name_col).strip():
                continue
            if len(records) >= max_rows:
                raise ValidationError(f"El Excel supera el maximo de {max_rows} gestantes por importacion")
            records.append(parse_record(sheet, layout, row))
    if not found:
        raise ValidationError(
            "No se encontro el formato MINSA de seguimiento de gestantes (fila con 'APELLIDOS Y NOMBRES' y 'DNI')"
        )
    if not records:
        raise ValidationError("El Excel no contiene gestantes")
    return records
