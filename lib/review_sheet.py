"""The snapshot's review spreadsheet (.xlsx), written by hand: a front
sheet, then one per section, for people outside the studio to fill in
(see NOTES.md, "Production snapshot")."""

import io
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from .snapshot import SCHEMA_VERSION, TEAM_ROLE, _render_ref, _rtk_on


# Template v4: a front sheet (Author, Review date, Role, how to, legend),
# then one sheet per section -- Shots, Assets -- each with only its own
# departments. A cell per department: "ok" validates it for the Role, "no"
# withdraws that, any other text withdraws it too and makes an RTK of each
# line ([sh020] [f12-40] at its start). "global": ok = every department
# done so far, text = an RTK for no department. Each cell's fill is the
# department's state at the snapshot. See NOTES.md, "Validation roles".
REVIEW_GLOBAL = "global"
# What reads as "validated" in a department cell, case aside.
OK_WORDS = ("ok", "yes", "oui", "v", "x", "✓", "✔", "valid", "validé", "valide")
NO_WORDS = ("no", "non")
# Hidden columns after the departments' and "global", for the import.
# render_watched: what the reviewer watched (_render_ref()) -- the notes'
# version. Not "render": a project's department can be called that (schema
# 7; until 6 the two shared the name and an asset's "render" was lost).
RENDER_WATCHED = "render_watched"
_REVIEW_HIDDEN = ("wip_version", "stable_version", "description_exported", RENDER_WATCHED)
_SHEET_HEADER_ROW = 2  # row 1: the sheet's one-line how-to
# Template v3 (1.1.2 before its release): read back for the import only.
VALID_PREFIX = "valid "
VALID_CHOICES = ("yes", "no")
VALID_ALL = "valid all done"

# cellXfs indexes in _STYLES_XML
_S_TITLE, _S_LABEL, _S_HINT, _S_HEADER, _S_LOCKED = 1, 2, 3, 4, 5
# 6: locked and muted, kept so the indexes below don't move.
_S_INPUT, _S_INPUT_DATE, _S_INPUT_TEXT, _S_GROUP = 7, 8, 9, 10
# A department cell, by state (then +1: the same with an open RTK's red
# border): input cells, filled with the state's colour.
_S_STATE = {"todo": 11, "wip": 13, "rework": 15, "done": 17, "validated": 19}
_S_NA = 21  # not required: locked, "–"
_S_HINT_WRAP = 22
# The front sheet's three fields to fill: a bigger label, a yellow input.
_S_FIELD_LABEL, _S_FIELD, _S_FIELD_DATE, _S_SECTION = 23, 24, 25, 26

_XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _col(n: int) -> str:
    """0-based column index -> letters."""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref: str, value, style: int = 0) -> str:
    """One inline-string cell of the review sheet's XML; empty for no value."""
    if value in (None, ""):
        return f'<c r="{ref}" s="{style}"/>'
    text = xml_escape(_XML_ILLEGAL.sub("", str(value)))
    return (
        f'<c r="{ref}" s="{style}" t="inlineStr">'
        f'<is><t xml:space="preserve">{text}</t></is></c>'
    )


def _stem(filename: str | None) -> str | None:
    return Path(filename).stem if filename else None


def _department_style(item: dict, department: str) -> int:
    """A department cell's style: its state's fill (violet once validated
    by the top role at the stable shown), red-bordered with an open RTK on
    it or on no department."""
    state = item["departments"][department]
    key = "validated" if item.get("validated", {}).get(department) else state
    return _S_STATE[key] + _rtk_on(item, department)


def _with_team(roles: list) -> list:
    """The Role choices: the validation roles, then "team" (the team's own
    retakes, no validation) unless one of them has that name."""
    return [*roles, TEAM_ROLE] if TEAM_ROLE not in roles else list(roles)


def _review_front(meta: dict, roles: list, top_role: str | None) -> str:
    """Sheet 1: title, Author / Review date / Role inputs, how to fill the
    other sheets, the colour legend; schema_version in a hidden cell."""
    title = f"{meta.get('project') or ''} review".strip()
    scan_date = (meta.get("scan_started_at") or "").replace("T", " ")[:16]
    how = (
        f"Snapshot of {scan_date}. One sheet per section (Shots, Assets), one "
        "row per file, a cell per department:",
        "  ok  →  validates the department as your role (yes, v, ✓... too)",
        "  no  →  withdraws that validation",
        "  any other text  →  withdraws it too, and each line becomes a retake "
        "(RTK) of that department -- Alt+Enter for the next line",
        "  start a line with [sh020] for one shot of a block, [f12-40] or [f12] "
        "for its frames:  [sh020] [f12-40] the foot slides",
        "  global  →  ok validates every department done so far; a text is a "
        "retake for no department in particular",
        "  empty  →  nothing changes.  Edit a description to change it.",
        "  Role team  →  your retakes and notes are the team's (no role, no "
        "prod tag); ok and no are left out: the team doesn't validate.",
    )
    legend = [
        (_S_STATE["todo"], "Not started"),
        (_S_STATE["wip"], "Work in progress"),
        (_S_STATE["rework"], "Done, reworked since"),
        (_S_STATE["done"], "Done -- to validate"),
        (
            _S_STATE["validated"],
            f"Validated by {top_role} (or equivalent)" if top_role else "Validated",
        ),
        (_S_STATE["todo"] + 1, "Red border: an open retake"),
        (_S_NA, "–  not required"),
    ]
    field = '<row r="{r}" ht="26" customHeight="1">'
    rows = [
        '<row r="1" ht="24" customHeight="1">'
        + _cell("A1", title, _S_SECTION)
        + _cell("D1", f"schema_version={SCHEMA_VERSION}")
        + "</row>",
        field.format(r=2)
        + _cell("A2", "Author", _S_FIELD_LABEL)
        + _cell("B2", "", _S_FIELD)
        + _cell("C2", 'Empty: "prod"', _S_HINT)
        + "</row>",
        field.format(r=3)
        + _cell("A3", "Review date", _S_FIELD_LABEL)
        + _cell("B3", "", _S_FIELD_DATE)
        + _cell("C3", "Empty: the day the file is imported", _S_HINT)
        + "</row>",
        field.format(r=4)
        + _cell("A4", "Role", _S_FIELD_LABEL)
        + _cell("B4", "", _S_FIELD)
        + _cell(
            "C4",
            "Required: pick it in the list -- your validations and retakes are recorded under it",
            _S_HINT,
        )
        + "</row>",
    ]
    r = 7
    rows.append(f'<row r="{r}">' + _cell(f"A{r}", "How to fill", _S_LABEL) + "</row>")
    for line in how:
        r += 1
        rows.append(f'<row r="{r}">' + _cell(f"A{r}", line, _S_HINT) + "</row>")
    r += 2
    rows.append(
        f'<row r="{r}">'
        + _cell(f"A{r}", "Colours (state at the snapshot)", _S_LABEL)
        + "</row>"
    )
    for style, label in legend:
        r += 1
        rows.append(
            f'<row r="{r}">'
            + _cell(f"A{r}", "", style)
            + _cell(f"B{r}", label, _S_HINT)
            + "</row>"
        )
    validations = ""
    if roles:
        validations = (
            '<dataValidations count="1"><dataValidation type="list" allowBlank="1" '
            f'showErrorMessage="1" sqref="B4"><formula1>"{xml_escape(",".join(_with_team(roles)))}"'
            "</formula1></dataValidation></dataValidations>"
        )
    return _worksheet(
        f"A1:D{r}",
        '<col min="1" max="1" width="16" customWidth="1"/>'
        '<col min="2" max="2" width="28" customWidth="1"/>'
        '<col min="3" max="3" width="60" customWidth="1"/>'
        '<col min="4" max="4" width="8" hidden="1"/>',
        "".join(rows),
        validations,
        active="B2",
    )


def _review_section(title: str, items: list, departments: list) -> tuple[str, str]:
    """A section's sheet: group (merged), filename, description, a column
    per department and "global" -- input cells filled by state, "–" locked
    where not required -- then the hidden columns. -> (sheet XML, the
    autofilter's range)."""
    columns = [("group", 12), ("filename", 36), ("description", 28)]
    columns += [(d, 24) for d in departments] + [(REVIEW_GLOBAL, 30)]
    visible = len(columns)
    columns += [(h, 10) for h in _REVIEW_HIDDEN]
    col = {h: _col(i) for i, (h, _) in enumerate(columns)}
    hr = _SHEET_HEADER_ROW
    first, last = hr + 1, hr + max(1, len(items))
    how = (
        f"{title}: ok validates a department, no withdraws, any other text = "
        "retakes (one per line, [sh020] [f12-40] at its start). Colours and "
        "details: first sheet."
    )
    rows = [
        '<row r="1">' + _cell("A1", how, _S_HINT) + "</row>",
        f'<row r="{hr}">'
        + "".join(_cell(f"{col[h]}{hr}", h, _S_HEADER) for h, _ in columns)
        + "</row>",
    ]
    inputs, merges, group_start = [], [], None
    for n, item in enumerate(items):
        r = first + n
        new_group = n == 0 or item["group"] != items[n - 1]["group"]
        if new_group:
            if group_start is not None and r - 1 > group_start:
                merges.append(f"A{group_start}:A{r - 1}")
            group_start = r
        cells = [
            _cell(f"A{r}", item["group"] if new_group else None, _S_GROUP),
            _cell(f"B{r}", _stem(item["current_version"]) or item["name"], _S_LOCKED),
            _cell(f"C{r}", item["description"], _S_INPUT),
        ]
        for d in departments:
            ref = f"{col[d]}{r}"
            if d in item["departments"]:
                cells.append(_cell(ref, "", _department_style(item, d)))
                inputs.append(ref)
            else:
                cells.append(_cell(ref, "–", _S_NA))
        ref = f"{col[REVIEW_GLOBAL]}{r}"
        cells.append(_cell(ref, "", _S_INPUT))
        inputs.append(ref)
        cells += [
            _cell(f"{col['wip_version']}{r}", _stem(item["wip_version"]), _S_LOCKED),
            _cell(
                f"{col['stable_version']}{r}", _stem(item["stable_version"]), _S_LOCKED
            ),
            _cell(f"{col['description_exported']}{r}", item["description"], _S_LOCKED),
            _cell(f"{col[RENDER_WATCHED]}{r}", _render_ref(item["renders"]), _S_LOCKED),
        ]
        rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    if group_start is not None and last > group_start:
        merges.append(f"A{group_start}:A{last}")
    cols = "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"'
        + (' hidden="1"' if i >= visible else "")
        + "/>"
        for i, (_, w) in enumerate(columns)
    )
    filter_ref = f"A{hr}:{_col(visible - 1)}{last}"
    # A suggestion, not a rule: any text goes (showErrorMessage="0").
    validations = (
        '<dataValidations count="1"><dataValidation type="list" allowBlank="1" '
        f'showErrorMessage="0" sqref="{" ".join(inputs)}"><formula1>"ok,no"</formula1>'
        "</dataValidation></dataValidations>"
        if inputs
        else ""
    )
    merge_xml = (
        f'<mergeCells count="{len(merges)}">'
        + "".join(f'<mergeCell ref="{m}"/>' for m in merges)
        + "</mergeCells>"
        if merges
        else ""
    )
    sheet = _worksheet(
        f"A1:{_col(len(columns) - 1)}{last}",
        cols,
        "".join(rows),
        validations,
        active=f"{col[departments[0]] if departments else 'C'}{first}",
        freeze=(2, hr),
        after_data=f'<autoFilter ref="{filter_ref}"/>{merge_xml}',
    )
    return sheet, filter_ref


def _worksheet(
    dimension: str,
    cols: str,
    rows: str,
    validations: str,
    active: str,
    freeze: tuple[int, int] | None = None,
    after_data: str = "",
) -> str:
    """One protected sheet (no password: it only stops accidental edits of
    the locked cells), printed landscape one page wide."""
    if freeze:
        x, y = freeze
        pane = (
            f'<pane xSplit="{x}" ySplit="{y}" topLeftCell="{_col(x)}{y + 1}" '
            'activePane="bottomRight" state="frozen"/>'
            f'<selection pane="bottomRight" activeCell="{active}" sqref="{active}"/>'
        )
    else:
        pane = f'<selection activeCell="{active}" sqref="{active}"/>'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'
        f'<dimension ref="{dimension}"/>'
        f'<sheetViews><sheetView workbookViewId="0">{pane}</sheetView></sheetViews>'
        f"<cols>{cols}</cols>"
        f"<sheetData>{rows}</sheetData>"
        '<sheetProtection sheet="1" objects="1" scenarios="1" formatCells="0" '
        'formatColumns="0" formatRows="0" autoFilter="0"/>'
        f"{after_data}{validations}"
        '<pageMargins left="0.5" right="0.5" top="0.5" bottom="0.5" header="0.3" footer="0.3"/>'
        '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>'
        "</worksheet>"
    )


def render_review_xlsx(snapshot: dict) -> bytes:
    """Review template v4: the front sheet, then Shots and Assets (a
    section with nothing tracked left out), each with its own departments
    -- see the comment above REVIEW_GLOBAL."""
    meta = snapshot["meta"]
    roles = [r["name"] for r in meta.get("validation_roles", [])]
    top_role = meta.get("validation_role")
    sheets = [("Review", _review_front(meta, roles, top_role), None)]
    for title, items, departments in (
        ("Shots", snapshot["shots"], meta.get("shot_departments", [])),
        ("Assets", snapshot["assets"], meta.get("asset_departments", [])),
    ):
        if items:
            xml, filter_ref = _review_section(title, items, departments)
            sheets.append((title, xml, filter_ref))
    n = len(sheets)
    names = "".join(
        f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
        + name
        + "!"
        + re.sub(r"([A-Z]+)(\d+)", r"$\1$\2", ref)
        + "</definedName>"
        for i, (name, _, ref) in enumerate(sheets)
        if ref
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        + "".join(
            f'<sheet name="{name}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
            for i, (name, _, _) in enumerate(sheets)
        )
        + "</sheets>"
        + (f"<definedNames>{names}</definedNames>" if names else "")
        + "</workbook>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(n)
        )
        + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
            for i in range(n)
        )
        + f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", _RELS_XML)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        for i, (_, xml, _) in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", xml)
        z.writestr("xl/styles.xml", _STYLES_XML)
    return buf.getvalue()


_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)
# One font, one size: weight and grey only. Grey fill = locked, white =
# to fill in. cellXfs: 0 default, 1 title, 2 label, 3 hint, 4 header,
# 5 locked, 6 locked muted, 7 input, 8 input date, 9 input text-format
# (keeps "045" a string), 10 group (merged left column), then a
# department's input cell per state (_S_STATE) and its red-bordered twin,
# 21 not required, 22 hint wrapped.
_UNLOCK = '<protection locked="0"/>'
_TOP = '<alignment vertical="top"/>'
_TOP_WRAP = '<alignment vertical="top" wrapText="1"/>'
# fillId per state: todo white (0), wip amber, rework light green, done
# green, validated violet -- the snapshot page's colours, lightened.
_STATE_FILLS = (("todo", 0), ("wip", 5), ("rework", 6), ("done", 7), ("validated", 8))
_STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/></numFmts>'
    '<fonts count="5">'
    '<font><sz val="11"/><color rgb="FF1F2328"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><color rgb="FF1F2328"/><name val="Calibri"/></font>'
    '<font><sz val="11"/><color rgb="FF6E7781"/><name val="Calibri"/></font>'
    '<font><b/><sz val="13"/><color rgb="FF1F2328"/><name val="Calibri"/></font>'
    '<font><b/><sz val="16"/><color rgb="FF1F2328"/><name val="Calibri"/></font>'
    "</fonts>"
    '<fills count="10">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFDDE3EA"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFF3F4F6"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFE9EDF2"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFFCEBC4"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFE4F4D4"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFC8EBCD"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFE6D8F7"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF3B0"/></patternFill></fill>'
    "</fills>"
    '<borders count="4"><border/>'
    '<border><left style="thin"><color rgb="FFC8CED6"/></left><right style="thin"><color rgb="FFC8CED6"/></right>'
    '<top style="thin"><color rgb="FFC8CED6"/></top><bottom style="thin"><color rgb="FFC8CED6"/></bottom></border>'
    '<border><left style="medium"><color rgb="FFC62828"/></left><right style="medium"><color rgb="FFC62828"/></right>'
    '<top style="medium"><color rgb="FFC62828"/></top><bottom style="medium"><color rgb="FFC62828"/></bottom></border>'
    '<border><left style="medium"><color rgb="FF8A6D00"/></left><right style="medium"><color rgb="FF8A6D00"/></right>'
    '<top style="medium"><color rgb="FF8A6D00"/></top><bottom style="medium"><color rgb="FF8A6D00"/></bottom></border>'
    "</borders>"
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="27">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>'
    f'<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1">{_TOP}</xf>'
    f'<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">{_TOP_WRAP}</xf>'
    f'<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1" applyProtection="1">{_TOP_WRAP}{_UNLOCK}</xf>'
    f'<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1" applyProtection="1"><alignment horizontal="left"/>{_UNLOCK}</xf>'
    f'<xf numFmtId="49" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1" applyProtection="1">{_TOP}{_UNLOCK}</xf>'
    '<xf numFmtId="0" fontId="1" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
    + "".join(
        f'<xf numFmtId="0" fontId="0" fillId="{fill}" borderId="{border}" xfId="0" '
        'applyFill="1" applyBorder="1" applyAlignment="1" applyProtection="1">'
        f"{_TOP_WRAP}{_UNLOCK}</xf>"
        for _, fill in _STATE_FILLS
        for border in (1, 2)
    )
    + '<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" '
    'applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>'
    f'<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">{_TOP_WRAP}</xf>'
    '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="center"/></xf>'
    f'<xf numFmtId="0" fontId="3" fillId="9" borderId="3" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1" applyProtection="1"><alignment vertical="center"/>{_UNLOCK}</xf>'
    f'<xf numFmtId="164" fontId="3" fillId="9" borderId="3" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1" applyProtection="1"><alignment horizontal="left" vertical="center"/>{_UNLOCK}</xf>'
    '<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    "</cellXfs>"
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    "</styleSheet>"
)
