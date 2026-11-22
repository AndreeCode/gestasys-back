import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from ....core.http.app_error import ValidationError
from ...pregnancy.domain.pregnancy_domain import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    STATUS_COMPLETED,
    STATUS_IN_FOLLOWUP,
    STATUS_PENDING,
)

EXPORT_COLUMNS = [
    "codigo", "dni", "nombres", "apellidos", "fecha_nacimiento", "edad", "telefono", "direccion",
    "establecimiento", "fum", "fpp", "edad_gestacional", "gestas", "partos", "riesgo", "estado",
    "fecha_parto", "ultimo_control", "proxima_cita", "observaciones",
]

TEMPLATE_COLUMNS = [
    "codigo", "dni", "nombres", "apellidos", "fecha_nacimiento", "telefono", "direccion", "establecimiento",
    "fum", "fpp", "gestas", "partos", "riesgo", "estado", "fecha_parto", "observaciones",
]

HEADER_ALIASES = {
    "codigo": "codigo", "code": "codigo", "id": "codigo",
    "dni": "dni", "documento": "dni",
    "nombres": "nombres", "nombre": "nombres", "first_names": "nombres",
    "apellidos": "apellidos", "apellido": "apellidos", "last_names": "apellidos",
    "fecha_nacimiento": "fecha_nacimiento", "fecha_de_nacimiento": "fecha_nacimiento",
    "nacimiento": "fecha_nacimiento", "birth_date": "fecha_nacimiento",
    "telefono": "telefono", "celular": "telefono", "phone": "telefono",
    "direccion": "direccion", "domicilio": "direccion", "address": "direccion",
    "establecimiento": "establecimiento", "sede": "establecimiento",
    "establecimiento_de_salud": "establecimiento", "health_facility": "establecimiento",
    "fum": "fum", "fecha_ultima_menstruacion": "fum", "last_menstrual_period": "fum",
    "fpp": "fpp", "fecha_probable_parto": "fpp", "fecha_probable_de_parto": "fpp", "expected_delivery_date": "fpp",
    "gestas": "gestas", "gravida": "gestas", "g": "gestas",
    "partos": "partos", "paridad": "partos", "parity": "partos", "p": "partos",
    "riesgo": "riesgo", "nivel_de_riesgo": "riesgo", "risk_level": "riesgo",
    "estado": "estado", "status": "estado",
    "fecha_parto": "fecha_parto", "fecha_de_parto": "fecha_parto", "delivery_date": "fecha_parto",
    "observaciones": "observaciones", "notas": "observaciones", "notes": "observaciones",
}

REQUIRED_COLUMNS = ("nombres", "apellidos", "fecha_nacimiento", "establecimiento")

STATUS_LABELS = {STATUS_PENDING: "Pendiente", STATUS_IN_FOLLOWUP: "En seguimiento", STATUS_COMPLETED: "Completado"}
RISK_LABELS = {RISK_LOW: "Bajo", RISK_MEDIUM: "Medio", RISK_HIGH: "Alto"}

STATUS_VALUES = {
    "pendiente": STATUS_PENDING, "pending": STATUS_PENDING,
    "en seguimiento": STATUS_IN_FOLLOWUP, "seguimiento": STATUS_IN_FOLLOWUP, "en_seguimiento": STATUS_IN_FOLLOWUP,
    "in_followup": STATUS_IN_FOLLOWUP,
    "completado": STATUS_COMPLETED, "completada": STATUS_COMPLETED, "completed": STATUS_COMPLETED,
    "finalizado": STATUS_COMPLETED,
}
RISK_VALUES = {
    "bajo": RISK_LOW, "low": RISK_LOW,
    "medio": RISK_MEDIUM, "moderado": RISK_MEDIUM, "medium": RISK_MEDIUM,
    "alto": RISK_HIGH, "high": RISK_HIGH,
}

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")


def fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(c for c in value if not unicodedata.combining(c)).strip().lower()


def normalize_header(header: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]", "_", fold(header))).strip("_")


def parse_date(field_name: str, value: str) -> date:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field_name} '{value}' no es una fecha valida (AAAA-MM-DD o DD/MM/AAAA)")


def parse_int(field_name: str, value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{field_name} '{value}' debe ser un numero entero")


def parse_status(value: str) -> str:
    if fold(value) not in STATUS_VALUES:
        raise ValueError(f"estado '{value}' no reconocido (Pendiente, En seguimiento, Completado)")
    return STATUS_VALUES[fold(value)]


def parse_risk(value: str) -> str:
    if fold(value) not in RISK_VALUES:
        raise ValueError(f"riesgo '{value}' no reconocido (Bajo, Medio, Alto)")
    return RISK_VALUES[fold(value)]


def detect_delimiter(header_line: str) -> str:
    counts = {d: header_line.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralize(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def restore(value: str) -> str:
    if len(value) > 1 and value[0] == "'" and value[1:].startswith(FORMULA_PREFIXES):
        return value[1:].strip()
    return value


@dataclass
class Sheet:
    columns: dict[str, int]
    rows: list[list[str]] = field(default_factory=list)
    lines: list[int] = field(default_factory=list)

    def has(self, key: str) -> bool:
        return key in self.columns

    def get(self, row: list[str], key: str) -> str:
        index = self.columns.get(key)
        if index is None or index >= len(row):
            return ""
        return restore(row[index].strip())


BINARY_SIGNATURES = (b"PK\x03\x04", b"%PDF", b"MZ", b"\x7fELF", b"\xd0\xcf\x11\xe0", b"\x89PNG", b"\xff\xd8\xff", b"GIF8")


def decode(data: bytes) -> str:
    if b"\x00" in data or data.startswith(BINARY_SIGNATURES):
        raise ValidationError("El archivo no es un CSV de texto (si es Excel, guardalo como CSV UTF-8)")
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValidationError("No se pudo leer el archivo: usa codificacion UTF-8")


def read_sheet(data: bytes, max_rows: int) -> Sheet:
    text = decode(data)
    if not text.strip():
        raise ValidationError("El archivo esta vacio")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=detect_delimiter(text.splitlines()[0]))
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as err:
        raise ValidationError(f"No se pudo leer la cabecera del CSV: {err}")

    columns: dict[str, int] = {}
    for index, name in enumerate(header):
        key = HEADER_ALIASES.get(normalize_header(name))
        if key and key not in columns:
            columns[key] = index
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise ValidationError(f"Faltan columnas obligatorias en el CSV: {', '.join(missing)}")

    sheet = Sheet(columns=columns)
    try:
        for record in reader:
            if not any(cell.strip() for cell in record):
                continue
            if len(sheet.rows) >= max_rows:
                raise ValidationError(f"El archivo supera el maximo de {max_rows} filas por importacion")
            sheet.rows.append(record)
            sheet.lines.append(reader.line_num)
    except csv.Error as err:
        raise ValidationError(f"CSV mal formado (linea {reader.line_num}): {err}")
    if not sheet.rows:
        raise ValidationError("El archivo no contiene filas de datos")
    return sheet


def write_csv(header: list[str], rows: list[list], delimiter: str = ",") -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow([neutralize(cell) for cell in header])
    writer.writerows([neutralize(cell) for cell in row] for row in rows)
    return ("﻿" + buffer.getvalue()).encode("utf-8")
