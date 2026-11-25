import re
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from .colors import color_name
from .csv_format import fold
from .minsa_format import item_label

ORDINALS = ["1era", "2da", "3era", "4ta", "5ta", "6ta", "7ma", "8va", "9na", "10ma", "11vo", "12vo", "13vo"]
APN_COUNT = 13

IDENTITY_SECTION = "DATOS DE LA GESTANTE"
PREGNANCY_SECTION = "EMBARAZO ACTUAL"
APN_SECTION = "ATENCIONES PRENATALES"
MARKS_SECTION = "MARCAS GESTASYS"

SECTION_COLUMNS: list[tuple[str, str, str]] = [
    ("ADMINISTRACION DE CALCIO", "", "CALCIO (1)/ N° TAB"),
    ("ADMINISTRACION DE CALCIO", "", "CALCIO (2)/ N° TAB"),
    ("ADMINISTRACION DE CALCIO", "", "CALCIO (3)/ N° TAB"),
    ("ADMINISTRACION DE CALCIO", "", "CALCIO (4)/ N° TAB"),
    ("ADMINISTRACION DE CALCIO", "", "CALCIO (5)/ N° TAB"),
    ("EXAMENES AUXILIARES", "I Bateria de Laboratorio", "FECHA"),
    ("EXAMENES AUXILIARES", "I Bateria de Laboratorio", "VIH (REACTIVO - NO REACTIVO)"),
    ("EXAMENES AUXILIARES", "I Bateria de Laboratorio", "Sifilis (REACTIVO - NO REACTIVO)"),
    ("EXAMENES AUXILIARES", "I Bateria de Laboratorio", "Hepatitis B (REACTIVO - NO REACTIVO)"),
    ("EXAMENES AUXILIARES", "I Bateria de Laboratorio", "Ex. Completo de Orina (NORMAL - ANORMAL)"),
    ("EXAMENES AUXILIARES", "I Bateria de Laboratorio", "Grupo y Factor (FECHA)"),
    ("EXAMENES AUXILIARES", "DOSAJE DE HEMOGLOBINA EN APN(AJUSTADA)", "1ra HB (durante el 1er CPN) / FECHA"),
    ("EXAMENES AUXILIARES", "DOSAJE DE HEMOGLOBINA EN APN(AJUSTADA)", "2da HB ( 25 a 28 semanas de gestacion) / FECHA"),
    ("EXAMENES AUXILIARES", "DOSAJE DE HEMOGLOBINA EN APN(AJUSTADA)", "3ra HB ( 37 a 40 semanas de gestacion) / FECHA"),
    ("EXAMENES AUXILIARES", "DOSAJE DE HEMOGLOBINA EN APN(AJUSTADA)", "4ta HB (a los 30 dias post parto) / FECHA"),
    ("EXAMENES AUXILIARES", "I I Bateria de Laboratorio", "FECHA"),
    ("EXAMENES AUXILIARES", "I I Bateria de Laboratorio", "VIH (REACTIVO - NO REACTIVO)"),
    ("EXAMENES AUXILIARES", "I I Bateria de Laboratorio", "Sifilis (REACTIVO - NO REACTIVO)"),
    ("EXAMENES AUXILIARES", "I I Bateria de Laboratorio", "Hepatitis B (REACTIVO - NO REACTIVO)"),
    ("EXAMENES AUXILIARES", "I I Bateria de Laboratorio", "HB/Ht Ajustado"),
    ("EXAMENES AUXILIARES", "I I Bateria de Laboratorio", "Ex. Completo de Orina (NORMAL - ANORMAL)"),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "1er Control de Hb (FECHA / resultado)", ""),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "TRATAMIENTO", "SF + AF (1) TABLETAS ENTREGADAS"),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "2do Control de Hb (FECHA / resultado)", ""),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "TRATAMIENTO", "SF + AF (2) TABLETAS ENTREGADAS"),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "3ro Control de Hb (FECHA / resultado)", ""),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "TRATAMIENTO", "SF + AF (3) TABLETAS ENTREGADAS"),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "4to Control de Hb (FECHA / resultado)", ""),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "TRATAMIENTO", "SF + AF (4) TABLETAS ENTREGADAS"),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "5to Control de Hb (FECHA / resultado)", ""),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "TRATAMIENTO", "SF + AF (5) TABLETAS ENTREGADAS"),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "6to Control de Hb (FECHA / resultado)", ""),
    ("CONTROL DE HEMOGLOBINA GESTANTE CON ANEMIA", "TRATAMIENTO", "SF + AF (6) TABLETAS ENTREGADAS"),
    ("TRATAMIENTO DE ITU", "Ex. Completo de orina /FECHA (dd/mm/aa)", ""),
    ("TRATAMIENTO DE ITU", "Tratamiento SI o NO / FECHA (dd/mm/aa)", ""),
    ("TRATAMIENTO DE ITU", "Visita domiciliaria antes de los 29 dias / FECHA (dd/mm/aa)", ""),
    ("Ecografía Obstétrica", "I Trimestre ( Edad Gest.)", ""),
    ("Ecografía Obstétrica", "FECHA (dd/mm/aa)", ""),
    ("Ecografía Obstétrica", "III Trimestre ( Edad Gest.)", ""),
    ("Ecografía Obstétrica", "FECHA (dd/mm/aa)", ""),
    ("Ecografía Obstétrica", "Hallazgos", ""),
    ("ODONTOLOGICO", "1er Control (NORMAL/ ANORMAL)/ FECHA (dd/mm/aa)", ""),
    ("ODONTOLOGICO", "2do Control (NORMAL/ ANORMAL) /FECHA (dd/mm/aa)", ""),
    ("TAMIZAJE VIF", "1er ( VIOLENCIA NEGATIVA/POSITIVO) /FECHA", ""),
    ("TAMIZAJE VIF", "Tratamiento SI o NO / FECHA (dd/mm/aa)", ""),
    ("TAMIZAJE VIF", "2do ( VIOLENCIA NEGATIVA/POSITIVO) /FECHA", ""),
    ("PAPANICOLAU", "Toma de PAP SI o NO / FECHA (dd/mm/aa)", ""),
    ("PAPANICOLAU", "RESULTADO (NORMAL ANORMAL) / FECHA (dd/mm/aa)", ""),
    ("VACUNAS", "DT Al primer contacto con el servicio de salud", "1era. Dosis Fecha"),
    ("VACUNAS", "DT Al primer contacto con el servicio de salud", "2da. Dosis Fecha"),
    ("VACUNAS", "Tdap ( 20- 36 ss)", "Dosis única Fecha"),
    ("VACUNAS", "HEPATITIS B (Cualquier edad gestacional, si no estan vacunadas o tienen esquema incompleto tres dosis en intervalos de 1 mes).", "1era. Dosis Fecha"),
    ("VACUNAS", "HEPATITIS B (Cualquier edad gestacional, si no estan vacunadas o tienen esquema incompleto tres dosis en intervalos de 1 mes).", "2da. Dosis Fecha"),
    ("VACUNAS", "HEPATITIS B (Cualquier edad gestacional, si no estan vacunadas o tienen esquema incompleto tres dosis en intervalos de 1 mes).", "3ra. Dosis Fecha"),
    ("VACUNAS", "INFLUENZA (Cualquier edad gestacional)", "Dosis única Fecha"),
    ("PLAN DE PARTO", "1° PP (FECHA)", ""),
    ("PLAN DE PARTO", "2° PP (FECHA)", ""),
    ("PLAN DE PARTO", "3° PP (FECHA)", ""),
    ("SEGUIMIENTO A LA GESTANTE", "1°", "fecha (dd/mm/aa)"),
    ("SEGUIMIENTO A LA GESTANTE", "1°", "Factor de riesgo / Signos de alarma identificado o presuntivo"),
    ("SEGUIMIENTO A LA GESTANTE", "2°", "fecha (dd/mm/aa)"),
    ("SEGUIMIENTO A LA GESTANTE", "2°", "Factor de riesgo / Signos de alarma identificado o presuntivo"),
    ("SEGUIMIENTO A LA GESTANTE", "3°", "fecha (dd/mm/aa)"),
    ("SEGUIMIENTO A LA GESTANTE", "3°", "Factor de riesgo / Signos de alarma identificado o presuntivo"),
    ("SEGUIMIENTO A LA GESTANTE", "4°", "fecha (dd/mm/aa)"),
    ("SEGUIMIENTO A LA GESTANTE", "4°", "Factor de riesgo / Signos de alarma identificado o presuntivo"),
    ("SEGUIMIENTO A LA GESTANTE", "5°", "fecha (dd/mm/aa)"),
    ("SEGUIMIENTO A LA GESTANTE", "5°", "Factor de riesgo / Signos de alarma identificado o presuntivo"),
    ("SEGUIMIENTO A LA GESTANTE", "6°", "fecha (dd/mm/aa)"),
    ("SEGUIMIENTO A LA GESTANTE", "6°", "Factor de riesgo / Signos de alarma identificado o presuntivo"),
    ("TERMINACIÓN DEL EMBARAZO", "ABORTO/PARTO", "FECHA"),
    ("TERMINACIÓN DEL EMBARAZO", "ABORTO/PARTO", "ABORTO COMPLETO (C) ó INCOMPLETO (I) /Procedimiento"),
    ("TERMINACIÓN DEL EMBARAZO", "ABORTO/PARTO", "TIPO DE PARTO (EUTOCICO, CESAREA)"),
    ("TERMINACIÓN DEL EMBARAZO", "ABORTO/PARTO", "PARTO INSTITUCIONAL (EE. SS.)"),
    ("TERMINACIÓN DEL EMBARAZO", "ABORTO/PARTO", "PERSONA QUIEN ATENDIO PARTO/ABORTO"),
    ("TERMINACIÓN DEL EMBARAZO", "ABORTO/PARTO", "OBSERVACION"),
    ("TERMINACIÓN DEL EMBARAZO", "Control de Puerperio", "1er Control (fecha)"),
    ("TERMINACIÓN DEL EMBARAZO", "Control de Puerperio", "SOFE (Nº /TA)"),
    ("TERMINACIÓN DEL EMBARAZO", "Control de Puerperio", "2do control (fecha)"),
    ("TERMINACIÓN DEL EMBARAZO", "Control de Puerperio", "MAC POST EVENTO OBSTETRICO (ALTA) /FECHA"),
    ("TERMINACIÓN DEL EMBARAZO", "Control de Puerperio", "Método Anticonceptivo, control puerperal(MAC / FECHA)"),
    ("VISITA DOMICILIARIA EN EL PUERPERIO", "1°", "fecha (dd/mm/aa)"),
    ("VISITA DOMICILIARIA EN EL PUERPERIO", "1°", "Signos de alarma identificado o presuntivo"),
    ("VISITA DOMICILIARIA EN EL PUERPERIO", "2°", "fecha (dd/mm/aa)"),
    ("VISITA DOMICILIARIA EN EL PUERPERIO", "2°", "Signos de alarma identificado o presuntivo"),
    ("DATOS DEL PADRE", "APELLIDOS Y NOMBRES", ""),
    ("DATOS DEL PADRE", "N°CELULAR", ""),
    ("SECTORISTA-OBSTETRA Y/O PERSONAL DE SALUD RESPONSABLE", "", ""),
    ("REFERENCIA", "FECHA DE LA REFERENCIA", ""),
    ("REFERENCIA", "DIGANOSTICO DE LA REFERENCIA", ""),
    ("REFERENCIA", "DESTINO DE LA REFERENCIA", ""),
    ("MIGRACIÒN", "VIAJE, CAMBIO DE DOMICILIO,VICTIMA DE VIOLENCIA SEXUAL,ETC)", "FECHA"),
    ("MIGRACIÒN", "VIAJE, CAMBIO DE DOMICILIO,VICTIMA DE VIOLENCIA SEXUAL,ETC)", "MOTIVO"),
    ("MIGRACIÒN", "VIAJE, CAMBIO DE DOMICILIO,VICTIMA DE VIOLENCIA SEXUAL,ETC)", "REGIÓN, NOMBRE DE LA IPRESS DONDE MIGRO"),
    ("OBSERVACIONES POR LOS EE. SS. (CONSIGNAR FECHA Y MOTIVO DE LA OBSERVACIÓN)", "", ""),
]

@dataclass(frozen=True)
class Column:
    key: str
    section: str
    group: str
    label: str
    width: int = 14


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")[:40] or "otros"


def fmt(value: Optional[date]) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


FIXED: list[tuple[str, str, int, Callable]] = [
    ("renaes", "CÓDIGO DE ESTABLECIMIENTO(RENAES)", 12, lambda p: p.get("renaes") or ""),
    ("province", "PROVINCIA", 12, lambda p: p.get("province") or p.get("facility_province") or ""),
    ("district", "DISTRITO", 14, lambda p: p.get("district") or p.get("facility_district") or ""),
    ("locality", "LOCALIDAD / SECTOR", 16, lambda p: p.get("locality") or ""),
    ("micro_network", "MICRORED", 16, lambda p: p.get("micro_network_name") or ""),
    ("facility", "EE. SS.", 18, lambda p: p.get("health_facility_name") or ""),
    ("address", "DIRECCION / REFERENCIA DEL DOMICILIO", 24, lambda p: p.get("address") or ""),
    ("full_name", "APELLIDOS Y NOMBRES", 30, lambda p: f"{p.get('last_names', '')} {p.get('first_names', '')}".strip().upper()),
    ("birth_date", "FECHA DE NACIMIENTO (DIA/MES/AÑO)", 13, lambda p: "" if p.get("birth_date_estimated") else fmt(p.get("birth_date"))),
    ("age", "EDAD (años)", 7, lambda p: "" if p.get("age") is None else str(p["age"])),
    ("dni", "DNI", 11, lambda p: p.get("dni") or ""),
    ("clinical_record", "HISTORIA CLINICA", 12, lambda p: p.get("clinical_record") or ""),
    ("phone", "N° CELULAR", 12, lambda p: p.get("phone") or ""),
    ("insurance", "TIPO DE SEGURO SIS/ESSALUD/OTRO", 12, lambda p: p.get("insurance") or ""),
    ("formula", "FÓRMULA OBSTETRICA", 12, lambda p: p.get("obstetric_formula") or (f"G{p['gravida']} P{p['parity'] if p.get('parity') is not None else ''}" if p.get("gravida") else "")),
    ("lmp", "FUM (dd/mm/aa)", 12, lambda p: fmt(p.get("last_menstrual_period"))),
    ("edd", "FPP (dd/mm/aa)", 12, lambda p: fmt(p.get("expected_delivery_date"))),
]

APN_PARTS: list[tuple[str, str, int]] = [
    ("date", "Fecha de Control (dd/mm/aa)", 12),
    ("weeks", "Edad Gest.", 7),
    ("supplementation", "Nº SUPLEMENTACIÓN (Ac. Fólico/Sof)", 11),
    ("risk_factor", "Factor de riesgo identificado", 16),
    ("performed_at", "EE.SS QUE REALIZO LA APN", 16),
    ("next", "Cita (dd/mm/aa)", 12),
]


def section_list() -> list[dict]:
    out = [
        {"id": "datos", "title": "Datos de la gestante y embarazo", "fixed": True},
        {"id": "apn", "title": "Atenciones prenatales (13 APN)"},
    ]
    seen: set[str] = set()
    for section, _, _ in SECTION_COLUMNS:
        sid = slug(section)
        if sid not in seen:
            seen.add(sid)
            out.append({"id": sid, "title": section.capitalize() if section.isupper() else section})
    out.append({"id": "otros", "title": "Otros datos"})
    out.append({"id": "marcas", "title": "Marcas de color (0/1)"})
    return out


def build_columns(selected: Optional[set[str]] = None) -> list[Column]:
    want = lambda sid: selected is None or sid in selected
    columns: list[Column] = [Column("n", IDENTITY_SECTION, "", "Nº", 5)]
    for key, label, width, _ in FIXED:
        section = PREGNANCY_SECTION if key in ("formula", "lmp", "edd") else IDENTITY_SECTION
        columns.append(Column(f"f:{key}", section, "", label, width))
    if want("apn"):
        for n in range(1, APN_COUNT + 1):
            for part, label, width in APN_PARTS:
                columns.append(Column(f"apn:{n}:{part}", APN_SECTION, f"{ORDINALS[n - 1]} APN", label, width))
    for index, (section, group, label) in enumerate(SECTION_COLUMNS):
        if want(slug(section)):
            columns.append(Column(f"c:{index}", section, group, label, 14))
    if want("otros"):
        columns.append(Column("other", "OTROS DATOS", "", "Datos sin columna en el formato", 30))
    if want("marcas"):
        columns.append(Column("m:row", MARKS_SECTION, "Fila pintada en el Excel", "Fila marcada (1 = pintada, 0 = sin color)", 12))
        columns.append(Column("m:color", MARKS_SECTION, "Fila pintada en el Excel", "Color de la fila", 12))
        columns.append(Column("m:cells", MARKS_SECTION, "Celdas pintadas distinto a su fila", "Cantidad de celdas marcadas", 12))
    return columns


def clinical_index() -> dict[tuple[str, str, int], int]:
    out: dict[tuple[str, str, int], int] = {}
    seen: dict[tuple[str, str], int] = {}
    for index, (section, group, label) in enumerate(SECTION_COLUMNS):
        key = (fold(section), fold(item_label(section, group, label)))
        seen[key] = seen.get(key, 0) + 1
        out[(*key, seen[key])] = index
    return out


CLINICAL_INDEX = clinical_index()


def control_values(controls: list[dict]) -> dict[str, str]:
    ordered = sorted(controls, key=lambda c: (c["control_date"], c.get("created_at") or date.min))
    out: dict[str, str] = {}
    used: set[int] = set()
    pending = []
    for c in ordered:
        n = c.get("control_number")
        if n and 1 <= n <= APN_COUNT and n not in used:
            used.add(n)
            out.update(_apn(n, c))
        else:
            pending.append(c)
    free = (n for n in range(1, APN_COUNT + 1) if n not in used)
    for c in pending:
        n = next(free, None)
        if n is None:
            break
        out.update(_apn(n, c))
    return out


def _apn(n: int, c: dict) -> dict[str, str]:
    weeks = c.get("gestational_weeks")
    return {
        f"apn:{n}:date": fmt(c.get("control_date")),
        f"apn:{n}:weeks": "" if weeks is None else (str(int(weeks)) if float(weeks).is_integer() else str(weeks)),
        f"apn:{n}:supplementation": c.get("supplementation") or "",
        f"apn:{n}:risk_factor": c.get("risk_factor") or "",
        f"apn:{n}:performed_at": c.get("performed_at") or "",
        f"apn:{n}:next": fmt(c.get("next_appointment")),
    }


def row_values(index: int, p: dict, controls: list[dict], columns: list[Column]) -> list[str]:
    values: dict[str, str] = {"n": str(index)}
    for key, _, _, getter in FIXED:
        values[f"f:{key}"] = getter(p)
    values.update(control_values(controls))
    others: list[str] = []
    for section, item, pos in clinical_positions(p):
        if pos is not None:
            values[f"c:{pos}"] = str(item.get("value", ""))
        elif item.get("value"):
            others.append(f"{section.get('section', '')}: {item.get('label', '')} = {item.get('value', '')}")
    values["other"] = " | ".join(others)
    marks = cell_marks(p)
    values["m:row"] = "1" if p.get("row_color") else "0"
    values["m:color"] = color_name(p.get("row_color")) or ""
    values["m:cells"] = str(len(marks))
    return [values.get(c.key, "") for c in columns]


def clinical_positions(p: dict):
    seen: dict[tuple[str, str], int] = {}
    for section in p.get("clinical_data") or []:
        for item in section.get("items", []):
            key = (fold(section.get("section", "")), fold(item.get("label", "")))
            seen[key] = seen.get(key, 0) + 1
            yield section, item, CLINICAL_INDEX.get((*key, item.get("occ") or seen[key]))


def cell_marks(p: dict) -> dict[str, str]:
    marks = dict(p.get("cell_marks") or {})
    for _, item, pos in clinical_positions(p):
        if pos is not None and item.get("color"):
            marks[f"c:{pos}"] = item["color"]
    return marks


def row_fills(p: dict, columns: list[Column]) -> list[Optional[str]]:
    marks = cell_marks(p)
    base = p.get("row_color")
    return [None if c.key.startswith("m:") else marks.get(c.key, base) for c in columns]
