import csv
import io
import json
import zipfile
from typing import List, Dict, Any
from xml.sax.saxutils import escape as xml_escape

# Column definitions: (key, header_title, column_width, wrap_text)
EXPORT_COLUMNS = [
    ("candidate_name", "Candidate Name", 24, False),
    ("status", "Status", 15, False),
    ("match_score", "Match Score", 14, False),
    ("target_position", "Target Position", 24, False),
    ("ai_summary", "AI Match Evaluation", 48, True),
    ("cited_quote", "Resume Evidence Quote", 42, True),
    ("cited_section", "Resume Section", 18, False),
    ("years_experience", "Experience (Years)", 18, False),
    ("skills", "Skills", 36, True),
    ("education", "Education", 28, False),
    ("email", "Email", 28, False),
    ("phone", "Phone", 18, False),
    ("resume_filename", "Resume File", 25, False),
    ("uploaded_at", "Uploaded At", 18, False),
    ("id", "Candidate ID", 36, False),
]


def _col_idx_to_letter(col_idx: int) -> str:
    """Convert 1-based column index to Excel column letter (1 -> A, 27 -> AA)."""
    result = ""
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


def export_candidates_to_xlsx(candidates_data: List[Dict[str, Any]]) -> bytes:
    """
    Exports candidates data to a genuinely compliant .xlsx (Excel) workbook
    with styled header row, freeze panes, auto-fit column widths, and cell borders.
    """
    # 1. Styles XML
    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font>
      <sz val="11"/>
      <name val="Calibri"/>
      <family val="2"/>
    </font>
    <font>
      <b/>
      <sz val="11"/>
      <color rgb="FFFFFFFF"/>
      <name val="Calibri"/>
      <family val="2"/>
    </font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF1E293B"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/></border>
    <border>
      <left style="thin"><color rgb="FFE2E8F0"/></left>
      <right style="thin"><color rgb="FFE2E8F0"/></right>
      <top style="thin"><color rgb="FFE2E8F0"/></top>
      <bottom style="thin"><color rgb="FFE2E8F0"/></bottom>
    </border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="4">
    <!-- 0: Standard cell -->
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1">
      <alignment vertical="top"/>
    </xf>
    <!-- 1: Header cell (dark blue fill, bold white text, centered) -->
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center"/>
    </xf>
    <!-- 2: Wrapped text cell (AI summaries, quotes, skills) -->
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1">
      <alignment vertical="top" wrapText="1"/>
    </xf>
    <!-- 3: Numeric / centered cell -->
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="top"/>
    </xf>
  </cellXfs>
</styleSheet>"""

    # 2. Worksheet XML
    sheet_rows = []

    # Column definition tags
    cols_xml = ['<cols>']
    for idx, (_, _, width, _) in enumerate(EXPORT_COLUMNS, 1):
        cols_xml.append(f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>')
    cols_xml.append('</cols>')

    # Header Row (Row 1)
    header_cells = []
    for col_idx, (_, header_title, _, _) in enumerate(EXPORT_COLUMNS, 1):
        cell_ref = f"{_col_idx_to_letter(col_idx)}1"
        safe_val = xml_escape(header_title)
        header_cells.append(f'<c r="{cell_ref}" t="inlineStr" s="1"><is><t>{safe_val}</t></is></c>')
    sheet_rows.append(f'<row r="1" ht="28" customHeight="1">{"".join(header_cells)}</row>')

    # Data Rows (Row 2+)
    for row_idx, item in enumerate(candidates_data, 2):
        row_cells = []
        for col_idx, (key, _, _, wrap_text) in enumerate(EXPORT_COLUMNS, 1):
            cell_ref = f"{_col_idx_to_letter(col_idx)}{row_idx}"
            raw_val = item.get(key, "")
            if isinstance(raw_val, list):
                raw_val = ", ".join(str(v) for v in raw_val)
            elif raw_val is None:
                raw_val = ""

            style_id = 2 if wrap_text else (3 if key in ("match_score", "years_experience", "status") else 0)

            # Check if value is a pure number for experience
            if key == "years_experience" and isinstance(raw_val, (int, float)):
                row_cells.append(f'<c r="{cell_ref}" t="n" s="{style_id}"><v>{raw_val}</v></c>')
            else:
                str_val = str(raw_val)
                safe_val = xml_escape(str_val)
                row_cells.append(f'<c r="{cell_ref}" t="inlineStr" s="{style_id}"><is><t>{safe_val}</t></is></c>')

        sheet_rows.append(f'<row r="{row_idx}" ht="22">{"".join(row_cells)}</row>')

    sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetViews>
    <sheetView tabSelected="1" workbookViewId="0">
      <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
    </sheetView>
  </sheetViews>
  <sheetFormatPr defaultRowHeight="16"/>
  {"".join(cols_xml)}
  <sheetData>
    {"".join(sheet_rows)}
  </sheetData>
</worksheet>"""

    # 3. Workbook XML
    workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Candidate Search &amp; Ranking" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""

    # 4. Relationships and Content Types
    content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

    root_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

    workbook_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    # Pack into in-memory ZIP
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("[Content_Types].xml", content_types_xml.strip())
        zip_file.writestr("_rels/.rels", root_rels_xml.strip())
        zip_file.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml.strip())
        zip_file.writestr("xl/workbook.xml", workbook_xml.strip())
        zip_file.writestr("xl/styles.xml", styles_xml.strip())
        zip_file.writestr("xl/worksheets/sheet1.xml", sheet_xml.strip())

    buffer.seek(0)
    return buffer.getvalue()


def export_candidates_to_csv(candidates_data: List[Dict[str, Any]]) -> str:
    """
    Exports candidates list to Excel-compatible CSV string with UTF-8 BOM
    so Microsoft Excel and spreadsheet tools open it with proper character encoding.
    """
    output = io.StringIO()
    # Write UTF-8 Byte Order Mark (BOM) so Excel opens UTF-8 text cleanly
    output.write("\ufeff")

    headers = [col[1] for col in EXPORT_COLUMNS]
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)

    for item in candidates_data:
        row = []
        for key, _, _, _ in EXPORT_COLUMNS:
            val = item.get(key, "")
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            elif val is None:
                val = ""
            row.append(str(val))
        writer.writerow(row)

    return output.getvalue()


def export_candidates_to_json(candidates_data: List[Dict[str, Any]]) -> str:
    """Exports candidates list to pretty-printed JSON string."""
    return json.dumps(candidates_data, indent=2, default=str)
