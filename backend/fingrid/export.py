import csv
import io
import zipfile
from xml.sax.saxutils import escape


def build_fingrid_csv(series: list[dict]) -> str:
    buffer = io.StringIO()
    fieldnames = [
        "timestamp",
        "timestamp_utc",
        "bucket_start",
        "bucket_end",
        "value",
        "avg_value",
        "peak_value",
        "trough_value",
        "sample_count",
        "unit",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in series:
        writer.writerow({key: row.get(key) for key in fieldnames})
    return buffer.getvalue()


def _sanitize_sheet_name(name: str, fallback: str) -> str:
    cleaned = "".join("_" if ch in '[]:*?/\\' else ch for ch in (name or fallback))
    cleaned = cleaned.strip().strip("'")
    cleaned = cleaned[:31]
    return cleaned or fallback[:31]


def _column_letter(index: int) -> str:
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheet_xml(fieldnames: list[str], rows: list[dict]) -> str:
    xml_rows = []

    header_cells = []
    for col_index, fieldname in enumerate(fieldnames, start=1):
        cell_ref = f"{_column_letter(col_index)}1"
        header_cells.append(
            f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(str(fieldname))}</t></is></c>'
        )
    xml_rows.append(f'<row r="1">{"".join(header_cells)}</row>')

    for row_index, row in enumerate(rows, start=2):
        cells = []
        for col_index, fieldname in enumerate(fieldnames, start=1):
            value = row.get(fieldname)
            cell_ref = f"{_column_letter(col_index)}{row_index}"
            if value is None:
                cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t></t></is></c>')
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{cell_ref}"><v>{value}</v></c>')
            else:
                cells.append(
                    f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
                )
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        "</worksheet>"
    )


def build_fingrid_multi_dataset_workbook(sheets: list[dict]) -> bytes:
    fieldnames = [
        "dataset_id",
        "dataset_name",
        "product",
        "signal",
        "timestamp",
        "timestamp_utc",
        "bucket_start",
        "bucket_end",
        "value",
        "avg_value",
        "peak_value",
        "trough_value",
        "sample_count",
        "unit",
    ]
    normalized_sheets = []
    for index, sheet in enumerate(sheets, start=1):
        fallback_name = f"Sheet{index}"
        normalized_sheets.append(
            {
                "name": _sanitize_sheet_name(sheet.get("name", fallback_name), fallback_name),
                "rows": sheet.get("rows", []),
            }
        )

    workbook_buffer = io.BytesIO()
    with zipfile.ZipFile(workbook_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for index, _sheet in enumerate(normalized_sheets, start=1)
            )
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            + "".join(
                f'<sheet name="{escape(sheet["name"])}" sheetId="{index}" r:id="rId{index}"/>'
                for index, sheet in enumerate(normalized_sheets, start=1)
            )
            + "</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{index}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{index}.xml"/>'
                for index, _sheet in enumerate(normalized_sheets, start=1)
            )
            + f'<Relationship Id="rId{len(normalized_sheets) + 1}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>'
            + "</Relationships>",
        )
        archive.writestr(
            "xl/styles.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            "</styleSheet>",
        )

        for index, sheet in enumerate(normalized_sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(fieldnames, sheet["rows"]))

    return workbook_buffer.getvalue()
