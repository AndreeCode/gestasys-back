import io
import re
import zipfile
from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape

from .xlsx_reader import column_letter

INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

TITLE, SECTION, GROUP, LABEL, CELL = 5, 1, 2, 3, 4
BASE_XFS = 6

FONTS = """<fonts count="4">
<font><sz val="10"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="13"/><color rgb="FF0B4F7C"/><name val="Calibri"/></font>
</fonts>"""

BASE_FILLS = [
    '<fill><patternFill patternType="none"/></fill>',
    '<fill><patternFill patternType="gray125"/></fill>',
    '<fill><patternFill patternType="solid"><fgColor rgb="FF0284C7"/></patternFill></fill>',
    '<fill><patternFill patternType="solid"><fgColor rgb="FFE0F2FE"/></patternFill></fill>',
    '<fill><patternFill patternType="solid"><fgColor rgb="FFF1F8FD"/></patternFill></fill>',
]

BORDERS = """<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFB9D7EA"/></left><right style="thin"><color rgb="FFB9D7EA"/></right><top style="thin"><color rgb="FFB9D7EA"/></top><bottom style="thin"><color rgb="FFB9D7EA"/></bottom><diagonal/></border>
</borders>"""

BASE_XF = [
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>',
    '<xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
    '<xf numFmtId="0" fontId="1" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
    '<xf numFmtId="0" fontId="1" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>',
    '<xf numFmtId="49" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>',
    '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>',
]

HEX = re.compile(r"^[0-9A-F]{6}$")


def _dark(color: str) -> bool:
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b < 140


def _styles(colors: list[str], header_colors: list[str]) -> tuple[str, dict[str, int], dict[str, int]]:
    fills = list(BASE_FILLS)
    xfs = list(BASE_XF)
    index: dict[str, int] = {}
    headers: dict[str, int] = {}
    for color in header_colors:
        fills.append(f'<fill><patternFill patternType="solid"><fgColor rgb="FF{color}"/></patternFill></fill>')
        font = 2 if _dark(color) else 1
        xfs.append(
            f'<xf numFmtId="0" fontId="{font}" fillId="{len(fills) - 1}" borderId="1" xfId="0" applyFont="1" applyFill="1" '
            'applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        )
        headers[color] = len(xfs) - 1
    for color in colors:
        fills.append(f'<fill><patternFill patternType="solid"><fgColor rgb="FF{color}"/></patternFill></fill>')
        xfs.append(
            f'<xf numFmtId="49" fontId="0" fillId="{len(fills) - 1}" borderId="1" xfId="0" applyNumberFormat="1" '
            'applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        )
        index[color] = len(xfs) - 1
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + FONTS
        + f'<fills count="{len(fills)}">{"".join(fills)}</fills>'
        + BORDERS
        + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        + f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
        + "</styleSheet>"
    )
    return xml, index, headers


def _text(value: str) -> str:
    return escape(INVALID_XML.sub("", value))


def _cell(ref: str, value: str, style: int) -> str:
    if value == "":
        return f'<c r="{ref}" s="{style}"/>'
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{_text(value)}</t></is></c>'


def _spans(values: list[str]) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    start = 0
    for i in range(1, len(values) + 1):
        if i == len(values) or values[i] != values[start]:
            out.append((start, i - 1, values[start]))
            start = i
    return out


def _sheet(
    title: str,
    sections: list[str],
    groups: list[str],
    labels: list[str],
    widths: list[int],
    rows: list[list[str]],
    fills: list[list[Optional[str]]],
    styles: dict[str, int],
    freeze_columns: int,
    header_fills: list[tuple[Optional[str], Optional[str], Optional[str]]],
    headers: dict[str, int],
) -> str:
    def head(col: int, level: int, default: int) -> int:
        color = header_fills[col][level] if col < len(header_fills) else None
        return headers.get(color, default) if color else default

    n = len(labels)
    last = column_letter(n)
    xml: list[str] = [f'<row r="1" ht="22" customHeight="1">{_cell("A1", title, TITLE)}</row>']
    merges: list[str] = []

    cells = []
    for start, end, text in _spans(sections):
        cells.append(_cell(f"{column_letter(start + 1)}3", text, head(start, 0, SECTION)))
        cells.extend(_cell(f"{column_letter(col)}3", "", head(col - 1, 0, SECTION)) for col in range(start + 2, end + 2))
        if end > start:
            merges.append(f"{column_letter(start + 1)}3:{column_letter(end + 1)}3")
    xml.append(f'<row r="3" ht="30" customHeight="1">{"".join(cells)}</row>')

    cells = []
    for start, end, text in _spans([f"{sections[i]}\u0000{groups[i]}" for i in range(n)]):
        group = text.split("\u0000", 1)[1]
        cells.append(_cell(f"{column_letter(start + 1)}4", group, head(start, 1, GROUP)))
        cells.extend(_cell(f"{column_letter(col)}4", "", head(col - 1, 1, GROUP)) for col in range(start + 2, end + 2))
        if end > start and group:
            merges.append(f"{column_letter(start + 1)}4:{column_letter(end + 1)}4")
    xml.append(f'<row r="4" ht="30" customHeight="1">{"".join(cells)}</row>')
    xml.append(
        f'<row r="5" ht="54" customHeight="1">'
        f'{"".join(_cell(f"{column_letter(i + 1)}5", labels[i], head(i, 2, LABEL)) for i in range(n))}</row>'
    )

    for r, row in enumerate(rows):
        row_fill = fills[r] if r < len(fills) else []
        out = []
        for c, value in enumerate(row):
            color = row_fill[c] if c < len(row_fill) else None
            out.append(_cell(f"{column_letter(c + 1)}{r + 6}", str(value or ""), styles.get(color, CELL) if color else CELL))
        xml.append(f'<row r="{r + 6}">{"".join(out)}</row>')

    end_row = max(5, len(rows) + 5)
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths))
    pane = column_letter(freeze_columns + 1) + "6"
    merge_xml = (
        f'<mergeCells count="{len(merges)}">{"".join(f"<mergeCell ref=\"{m}\"/>" for m in merges)}</mergeCells>'
        if merges
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{last}{end_row}"/>'
        f'<sheetViews><sheetView workbookViewId="0"><pane xSplit="{freeze_columns}" ySplit="5" topLeftCell="{pane}" '
        'activePane="bottomRight" state="frozen"/></sheetView></sheetViews>'
        f"<cols>{cols}</cols>"
        f'<sheetData>{"".join(xml)}</sheetData>'
        f'<autoFilter ref="A5:{last}{end_row}"/>'
        + merge_xml
        + "</worksheet>"
    )


@dataclass
class SheetSpec:
    name: str
    title: str
    rows: list[list[str]]
    fills: list[list[Optional[str]]]


def write_minsa_xlsx(
    sections: list[str],
    groups: list[str],
    labels: list[str],
    widths: list[int],
    sheets: list[SheetSpec],
    freeze_columns: int = 10,
    header_fills: Optional[list[tuple[Optional[str], Optional[str], Optional[str]]]] = None,
) -> bytes:
    header_fills = header_fills or []
    colors = sorted({c for spec in sheets for row in spec.fills for c in row if c and HEX.match(c)})
    header_colors = sorted({c for t in header_fills for c in t if c and HEX.match(c)})
    styles_xml, styles, headers = _styles(colors, header_colors)
    last = column_letter(len(labels))
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(sheets) + 1)
        )
        + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    rels = "".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, len(sheets) + 1)
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + rels
        + f'<Relationship Id="rId{len(sheets) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )
    sheet_list = "".join(
        f'<sheet name="{_text(spec.name[:31])}" sheetId="{i}" r:id="rId{i}"/>' for i, spec in enumerate(sheets, start=1)
    )
    names = "".join(
        f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
        f"'{_text(spec.name[:31])}'!$A$5:${last}${max(5, len(spec.rows) + 5)}</definedName>"
        for i, spec in enumerate(sheets)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_list}</sheets><definedNames>{names}</definedNames></workbook>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        z.writestr("xl/styles.xml", styles_xml)
        for i, spec in enumerate(sheets, start=1):
            z.writestr(
                f"xl/worksheets/sheet{i}.xml",
                _sheet(
                    spec.title, sections, groups, labels, widths, spec.rows, spec.fills, styles, freeze_columns,
                    header_fills, headers,
                ),
            )
    return buffer.getvalue()
