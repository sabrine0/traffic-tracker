# traffic_web/app/xlsx_writer.py
from __future__ import annotations

from pathlib import Path
import zipfile
from typing import Any, List, Tuple
from xml.sax.saxutils import escape

_INVALID_SHEET_CHARS = set('[]:*?/\\')

def _sanitize_sheet_name(name: str) -> str:
    cleaned = ''.join(ch for ch in name if ch not in _INVALID_SHEET_CHARS).strip()
    if not cleaned:
        cleaned = 'Sheet'
    return cleaned[:31]

def _unique_sheet_names(names: List[str]) -> List[str]:
    used = {}
    out = []
    for name in names:
        base = _sanitize_sheet_name(name)
        if base not in used:
            used[base] = 1
            out.append(base)
            continue
        idx = used[base]
        while True:
            candidate = f"{base[:28]}_{idx}"
            if candidate not in used:
                used[base] += 1
                used[candidate] = 1
                out.append(candidate)
                break
            idx += 1
    return out

def _col_name(idx: int) -> str:
    name = ''
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        name = chr(65 + rem) + name
    return name

def _cell_xml(cell_ref: str, value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return f'<c r="{cell_ref}" t="n"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{cell_ref}" t="n"><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>'

def _sheet_xml(rows: List[List[Any]]) -> str:
    row_xml = []
    for r_idx, row in enumerate(rows, 1):
        cells = []
        for c_idx, value in enumerate(row, 1):
            if value is None:
                continue
            ref = f"{_col_name(c_idx)}{r_idx}"
            cell = _cell_xml(ref, value)
            if cell:
                cells.append(cell)
        joined = ''.join(cells)
        row_xml.append(f'<row r="{r_idx}">{joined}</row>')
    sheet_data = ''.join(row_xml)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{sheet_data}</sheetData>'
        '</worksheet>'
    )

def write_xlsx(path: Path, sheets: List[Tuple[str, List[List[Any]]]]) -> None:
    if not sheets:
        raise ValueError('sheets must not be empty')

    names = _unique_sheet_names([name for name, _ in sheets])

    content_types = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    for i in range(len(sheets)):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    content_types.append('</Types>')

    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    workbook_sheets = []
    for i, name in enumerate(names, 1):
        workbook_sheets.append(
            f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
        )
    sheets_xml = ''.join(workbook_sheets)

    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{sheets_xml}</sheets>'
        '</workbook>'
    )

    workbook_rels = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    for i in range(len(sheets)):
        workbook_rels.append(
            f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
        )
    workbook_rels.append(
        '<Relationship Id="rId999" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    workbook_rels.append('</Relationships>')

    styles = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '</styleSheet>'
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    content_types_xml = ''.join(content_types)
    workbook_rels_xml = ''.join(workbook_rels)

    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types_xml)
        zf.writestr('_rels/.rels', rels)
        zf.writestr('xl/workbook.xml', workbook)
        zf.writestr('xl/styles.xml', styles)
        zf.writestr('xl/_rels/workbook.xml.rels', workbook_rels_xml)
        for i, (_, rows) in enumerate(sheets, 1):
            zf.writestr(f'xl/worksheets/sheet{i}.xml', _sheet_xml(rows))
