"""Import review: a review sent back -- the snapshot's spreadsheet or its
page's .json -- read, planned and written into the project's tracking."""

import hashlib
import json
import os
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from .config import (
    ConfigCache,
    get_active_project_root,
    parse_filename,
    shots_in_segment,
    validation_roles,
)
from .core import json_get, now, read_json_quiet
from .errors import PipelineError
from .review_sheet import (
    RENDER_WATCHED,
    _REVIEW_HIDDEN,
    NO_WORDS,
    OK_WORDS,
    REVIEW_GLOBAL,
    VALID_ALL,
    VALID_CHOICES,
    VALID_PREFIX,
    _col,
)
from .schedule import parse_day
from .snapshot import (
    ENTRY_TYPES,
    REVIEW_SOURCE,
    SCHEMA_VERSION,
    _render_ref,
    read_render_state,
    render_of_note,
)
from .tracking import (
    close_entry,
    _collect_folder,
    _status_from_raw,
    create_entry,
    entry_departments,
    find_file_by_name,
    set_department_approval,
    tracking_json_path,
    valid_department,
)

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _sheet_paths(z: zipfile.ZipFile) -> list[str]:
    """Zip paths of the workbook's sheets, in its order (not always
    sheetN.xml once a spreadsheet app has re-saved it)."""
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {
            rel.get("Id"): rel.get("Target")
            for rel in rels.iter(f"{_PKG_REL_NS}Relationship")
        }
        paths = []
        for sheet in wb.iter(f"{_NS}sheet"):
            target = targets.get(sheet.get(f"{_REL_NS}id"))
            if target:
                paths.append(
                    target.lstrip("/") if target.startswith("/") else f"xl/{target}"
                )
        if paths:
            return paths
    except (KeyError, AttributeError, ET.ParseError):
        pass
    return ["xl/worksheets/sheet1.xml"]


def _string_item(si) -> str:
    """Text of a sharedStrings <si> (plain or rich text runs, never the
    phonetic <rPh> guide)."""
    parts = []
    for child in si:
        if child.tag == f"{_NS}t":
            parts.append(child.text or "")
        elif child.tag == f"{_NS}r":
            parts.extend(t.text or "" for t in child.iter(f"{_NS}t"))
    return "".join(parts)


def _ref_split(ref: str) -> tuple[str, int]:
    m = re.match(r"([A-Z]+)(\d+)", ref or "")
    return (m[1], int(m[2])) if m else ("", 0)


def read_xlsx_grids(path: Path) -> list[dict[int, dict[str, str]]]:
    """Every sheet of an .xlsx, in order, as {row number: {column letters:
    text}}. Text cells resolved through sharedStrings (t="s") or inline;
    numbers (dates included) kept as their raw text."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            shared = []
            if "xl/sharedStrings.xml" in names:
                sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
                shared = [_string_item(si) for si in sst.iter(f"{_NS}si")]
            sheets = [ET.fromstring(z.read(p)) for p in _sheet_paths(z) if p in names]
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as e:
        raise PipelineError(f"Could not read {Path(path).name} as a spreadsheet: {e}")
    return [_sheet_grid(sheet, shared) for sheet in sheets]


def _sheet_grid(sheet, shared: list) -> dict[int, dict[str, str]]:
    grid: dict[int, dict[str, str]] = {}
    row_n = 0
    for row in sheet.iter(f"{_NS}row"):
        row_n = int(row.get("r") or row_n + 1)
        col_n = -1
        for c in row.iter(f"{_NS}c"):
            col, _ = _ref_split(c.get("r"))
            if not col:
                col_n += 1
                col = _col(col_n)
            else:
                col_n = (
                    sum((ord(ch) - 64) * 26**i for i, ch in enumerate(reversed(col)))
                    - 1
                )
            t = c.get("t")
            v = c.find(f"{_NS}v")
            if t == "inlineStr":
                value = "".join(x.text or "" for x in c.iter(f"{_NS}t"))
            elif v is None or v.text is None:
                continue
            elif t == "s":
                value = shared[int(v.text)]
            else:
                value = v.text
            # Excel escapes a CR as _x000D_ in strings.
            value = value.replace("_x000D_", "").replace("\r\n", "\n")
            if value != "":
                grid.setdefault(row_n, {})[col] = value
    return grid


def parse_review_date(value: str) -> datetime | None:
    """A Review date cell: an Excel date serial (a typed date is stored as a
    number of days), or text in a common date format. None when empty."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime(1899, 12, 30) + timedelta(days=float(value))
    except ValueError:
        pass
    try:
        return datetime.combine(parse_day(value), datetime.min.time())
    except PipelineError:
        pass
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise PipelineError(f"Review date '{value}' not understood (use YYYY-MM-DD).")


# A review written on the snapshot page itself (_JS's Review): the rows of a
# v4 template, as JSON.
REVIEW_JSON_FORMAT = "minimalist-pipeline-review"


def read_review_json(path: Path) -> dict:
    """read_review_xlsx()'s dict from a review downloaded from the snapshot
    page: {"format", "schema_version", "author", "role", "review_date",
    "rows": [{"filename", "stable_version", "description_exported",
    "render_watched"? (schema 7, "render" from 5: _render_ref()),
    "description"?, <department>:
    "ok" / "no" / retakes, "global"?}]}."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PipelineError(f"Could not read {Path(path).name}: {e}")
    if not isinstance(data, dict) or data.get("format") != REVIEW_JSON_FORMAT:
        raise PipelineError(
            f"{Path(path).name} isn't a review downloaded from a snapshot page."
        )
    schema = data.get("schema_version")
    if not isinstance(schema, int):
        raise PipelineError(f"{Path(path).name}: no schema_version.")
    if schema > SCHEMA_VERSION:
        raise PipelineError(
            f"{Path(path).name} comes from a newer addon version (review "
            f"v{schema}); update the addon to import it."
        )
    rows = [
        {
            str(k).strip().lower(): str(v).strip()
            for k, v in row.items()
            if v is not None
        }
        for row in data.get("rows") or []
        if isinstance(row, dict)
    ]
    return {
        "schema_version": schema,
        "author": str(data.get("author") or "").strip(),
        "role": str(data.get("role") or "").strip().lower(),
        "review_date": parse_review_date(str(data.get("review_date") or "")),
        # When the page was made: what it showed (_render_at_snapshot()).
        "snapshot": str(data.get("snapshot") or ""),
        "columns": {k for row in rows for k in row},
        "rows": rows,
    }


# A render watched as _render_ref() writes it: "v007-stable_001", or per
# shot "sh110=v007-stable_001 sh120=v006_002".
_RENDER_REF = re.compile(r"^(?:\S+=)?v\d+(?:-[a-z]+)?_\d+(?:\s+\S+=v\d+(?:-[a-z]+)?_\d+)*$", re.IGNORECASE)


def _legacy_render(review: dict) -> dict:
    """A review from before schema 7: its "render" was both the render
    watched and a department called "render" (the page wrote the second
    over the first). A render's name is the render watched; anything else
    ("ok", a retake) is that department's cell."""
    if review["schema_version"] >= 7:
        return review
    for row in review["rows"]:
        value = row.get("render")
        if value is not None and RENDER_WATCHED not in row and (
            not value.strip() or _RENDER_REF.match(value.strip())
        ):
            row[RENDER_WATCHED] = row.pop("render")
    review["columns"] = {k for row in review["rows"] for k in row}
    return review


def read_review(path: Path) -> dict:
    """A filled review: the snapshot page's .json, or the .xlsx template."""
    if Path(path).suffix.lower() == ".json":
        return _legacy_render(read_review_json(path))
    return _legacy_render(read_review_xlsx(path))


# The front sheet's how-to line (_review_front()): when the snapshot was made.
_SNAPSHOT_OF = re.compile(r"Snapshot of (\d{4}-\d\d-\d\d) (\d\d:\d\d)")


def read_review_xlsx(path: Path) -> dict:
    """{"schema_version", "author", "role", "review_date", "snapshot",
    "columns", "rows"} from a filled review template, every sheet's rows
    (v4: Shots, Assets) keyed by their own header row's names; Author,
    Review date and Role from the label cells above any header (v4: the
    front sheet); snapshot from its "Snapshot of <date>" line."""
    schema = None
    author = date = role = snapshot = ""
    columns: set[str] = set()
    rows = []
    for grid in read_xlsx_grids(path):
        header_row = None
        for r in sorted(grid):
            cells = grid[r]
            for v in cells.values():
                m = re.fullmatch(r"schema_version=(\d+)", v.strip())
                if m:
                    schema = int(m[1])
                m = _SNAPSHOT_OF.search(v)
                if m and not snapshot:
                    snapshot = f"{m[1]}T{m[2]}"
            label = cells.get("A", "").strip().lower()
            if label == "author":
                author = cells.get("B", "")
            elif label == "review date":
                date = cells.get("B", "")
            elif label == "role":
                role = cells.get("B", "")
            elif any(v.strip().lower() == "filename" for v in cells.values()):
                header_row = r
                break
        if header_row is None:
            continue
        header = {col: name.strip().lower() for col, name in grid[header_row].items()}
        columns |= set(header.values())
        rows += [
            {header[col]: v.strip() for col, v in grid[r].items() if col in header}
            for r in sorted(grid)
            if r > header_row
        ]
    if schema is None or not columns:
        raise PipelineError(
            f"{Path(path).name} isn't a review template exported by this addon."
        )
    if schema > SCHEMA_VERSION:
        raise PipelineError(
            f"{Path(path).name} comes from a newer addon version (template "
            f"v{schema}); update the addon to import it."
        )
    return {
        "schema_version": schema,
        "author": author.strip(),
        "role": role.strip().lower(),
        "review_date": parse_review_date(date),
        "snapshot": snapshot,
        "columns": columns,
        "rows": rows,
    }


_BULLET = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+")


def _review_lines(row: dict) -> list[str]:
    """A row's text cell, one note per line, a typed bullet dropped."""
    return [
        line
        for line in (
            _BULLET.sub("", l).strip() for l in row.get("text", "").split("\n")
        )
        if line
    ]


def _file_shots(filepath: Path) -> list[str]:
    """The shot numbers of a shot's .blend, padded ("010", "020" for a
    block); [] for an asset."""
    parsed = parse_filename(filepath.name) or {}
    if not parsed.get("shot"):
        return []
    digits = json_get(ConfigCache.get(), "naming.shot.digits", 3)
    try:
        return [f"{n:0{digits}d}" for n in shots_in_segment(parsed["shot"])]
    except ValueError:
        return []


_LINE_TAG = re.compile(r"\s*\[\s*([a-z]*)\s*(\d+)(?:\s*-\s*(\d+))?\s*\]", re.IGNORECASE)


def _line_tags(line: str, shots: list[str]) -> tuple[str, str | None, tuple | None]:
    """A review line's leading tags, in any order: "[sh020]" one shot of
    the block (shots: its numbers, padded), "[f12-40]" / "[f12]" its
    frames. -> (text without them, shot, (start, end or None)). A tag that
    isn't one -- an unknown shot, another word -- ends the scan and stays
    in the text."""
    shot_prefix = json_get(ConfigCache.get(), "naming.shot.prefix", "sh").lower()
    shot = frames = None
    rest = line
    while m := _LINE_TAG.match(rest):
        word, a, b = m[1].lower(), int(m[2]), m[3]
        if word in (shot_prefix, "sh") and b is None and shot is None:
            padded = next((s for s in shots if int(s) == a), None)
            if padded is None:
                break
            shot = padded
        elif word == "f" and frames is None:
            if b is not None and int(b) < a:
                break  # [f40-12]: not a range, left in the text
            frames = (a, int(b) if b else None)
        else:
            break
        rest = rest[m.end() :]
    rest = rest.strip()
    if not rest:  # tags alone: nothing to note, keep the line as typed
        return line, None, None
    return rest, shot, frames


# Not departments, in a v4 sheet's header.
# "fixed": the ids of the RTKs the reviewer marked fixed (the page's review,
# schema 6), space-separated.
_REVIEW_FIXED = {"group", "filename", "description", "fixed", REVIEW_GLOBAL, *_REVIEW_HIDDEN}
# "reply <id>": the reviewer's reply to that entry's thread (schema 6) --
# a retake on its departments, or "note:" a remark (_reply_kind()).
REPLY_PREFIX = "reply "


def _reply_kind(text: str) -> tuple[str, str]:
    """A reply as it's imported: (type, text). Every line "note:" -- a
    remark, the prefix dropped; else a retake, "still to redo", as in a
    department's cell."""
    lines = [line for line in text.splitlines() if line.strip()]
    if lines and all(_is_note(line) for line in lines):
        return "note", "\n".join(_drop_note(line) for line in lines)
    return "rtk", text


def _row_replies(row: dict) -> list[tuple[str, str]]:
    """[(entry id, text)] of a row's replies, empty ones left out."""
    return [
        (column[len(REPLY_PREFIX) :].strip(), value.strip())
        for column, value in row.items()
        if column.startswith(REPLY_PREFIX) and value.strip()
    ]
# "note:" -- or "note :", "n:", any case -- after the line's own tags
# ([sh020] [f12-40], kept): a remark, not a retake.
_NOTE_PREFIX = re.compile(r"^(\s*(?:\[[^\]]*\]\s*)*)(?:note|n)\s*:\s*", re.IGNORECASE)


def _is_note(line: str) -> bool:
    return bool(_NOTE_PREFIX.match(line))


def _drop_note(line: str) -> str:
    """The line without its "note:", its tags kept."""
    return _NOTE_PREFIX.sub(r"\1", line, count=1)


def _cell_choice(value: str) -> str:
    """A v4 department cell: "ok" (a validation word), "no", "text" (any
    other: retakes -- an "ok" line among others is text too, the retake
    wins), "" empty."""
    v = (value or "").strip()
    if not v:
        return ""
    if v.lower() in OK_WORDS:
        return "ok"
    if v.lower() in NO_WORDS:
        return "no"
    return "text"


def _row_actions(row: dict, schema: int) -> tuple[dict, str, list]:
    """What a template row asks: ({department: "yes"/"no"} of its own,
    "yes"/"no"/"" for every department done, [(line, departments, type)]
    notes to create). v4: a cell per department and "global"; before: the
    "valid <department>" columns, "valid all done", one text cell with the
    row's department(s) and type."""
    if schema < 4:
        wanted = {
            c[len(VALID_PREFIX) :]: v.strip().lower()
            for c, v in row.items()
            if c.startswith(VALID_PREFIX)
            and c != VALID_ALL
            and v.strip().lower() in VALID_CHOICES
        }
        every = (row.get(VALID_ALL) or "").strip().lower()
        every = every if every in VALID_CHOICES else ""
        departments = [
            d.strip()
            for d in re.split(r"[,;/+]", (row.get("department") or "").lower())
            if d.strip()
        ]
        entry_type = (row.get("type") or "").lower()
        entry_type = entry_type if entry_type in ENTRY_TYPES else "note"
        notes = [(line, departments, entry_type) for line in _review_lines(row)]
        return wanted, every, notes
    wanted, every, notes = {}, "", []
    for column, value in row.items():
        if column in _REVIEW_FIXED or column.startswith(REPLY_PREFIX):
            continue
        choice = _cell_choice(value)
        lines = _review_lines({"text": value}) if choice == "text" else []
        if choice == "ok":
            wanted[column] = "yes"
        elif choice == "no" or (
            # A retake withdraws the validation; "note:" lines alone are a
            # remark, the validation left as it is.
            choice == "text" and not all(_is_note(line) for line in lines)
        ):
            wanted[column] = "no"
        if choice == "text":
            notes += [
                (line, [column], "rtk") for line in _review_lines({"text": value})
            ]
    choice = _cell_choice(row.get(REVIEW_GLOBAL, ""))
    if choice in ("ok", "no"):
        every = "yes" if choice == "ok" else "no"
    elif choice == "text":
        notes += [
            (line, [], "rtk") for line in _review_lines({"text": row[REVIEW_GLOBAL]})
        ]
    # "note: ..." -- a remark, not a retake.
    notes = [
        (_drop_note(line), deps, "note")
        if _is_note(line)
        else (line, deps, t)
        for line, deps, t in notes
    ]
    return wanted, every, [n for n in notes if n[0]]


def _review_file(name: str) -> Path | None:
    """The .blend a row's filename names, None if it's gone."""
    try:
        return find_file_by_name(name if name.endswith(".blend") else f"{name}.blend")
    except PipelineError:  # unknown prefix...
        return None


def review_import_plan(path: Path, review: dict | None = None) -> dict:
    """What importing a review template would do, read only -- for its
    confirm dialog: {"role", "author", "notes" (lines in it), "fixed",
    "replies", their "notes_known" / "replies_known" / "fixed_done" (in the
    project already, left as is), "validations": [{"name", "filepath",
    "department", "approved", "stable"}] (changes only: "validations_known"
    given already), "refused": [(label, reason)]}. A template from
    1.1.2 on needs its Role, and that role must be one of the project's:
    raises PipelineError otherwise. An older one has no role (the team's
    notes) and no validation. review: read_review(path), if read."""
    review = review or read_review(path)
    role = review["role"]
    roles = {r["name"] for r in validation_roles()}
    schema = review["schema_version"]
    actions = [
        (row, *_row_actions(row, schema))
        for row in review["rows"]
        if row.get("filename")
    ]
    plan = {
        "role": role,
        "author": review["author"] or "prod",
        "notes": sum(len(notes) for _, _, _, notes in actions),
        "validations": [],
        "refused": [],
        # Retakes the reviewer marked fixed: closed under their name.
        "fixed": sum(len(row.get("fixed", "").split()) for row, *_ in actions),
        "replies": sum(len(_row_replies(row)) for row, *_ in actions),
        # What the project holds already (a review imported again), left as
        # it is: counted here as the import will tell it.
        "notes_known": 0,
        "replies_known": 0,
        "fixed_done": 0,
        "validations_known": 0,
    }
    author = plan["author"]
    for row, _, _, notes in actions:
        ids = row.get("fixed", "").split()
        replies = _row_replies(row)
        if not (notes or ids or replies):
            continue
        filepath = _review_file(row["filename"])
        if not filepath:
            continue
        if notes:
            known = _known_notes(filepath, author)
            for *_, key in _row_notes(filepath, row, notes):
                plan["notes_known"] += key in known
                known.add(key)
        entries = (read_json_quiet(tracking_json_path(filepath)) or {}).get("entries", [])
        by_id = {e.get("id"): e for e in entries}
        plan["fixed_done"] += sum(1 for i in ids if (by_id.get(i) or {}).get("done"))
        answered = {
            (e.get("response"), e.get("text"))
            for e in entries
            if e.get("response") and e.get("author") == author
        }
        plan["replies_known"] += sum(
            1 for entry_id, text in replies if (entry_id, _reply_kind(text)[1]) in answered
        )
    wanted_any = any(wanted or every for _, wanted, every, _ in actions)
    # Anything under the role: it must be one (descriptions don't need it).
    if schema >= 3 and (plan["notes"] or plan["replies"] or wanted_any):
        if not role:
            raise PipelineError(
                f"{Path(path).name}: no Role chosen at the top -- pick one, then import again."
            )
        if role not in roles:
            raise PipelineError(
                f"{Path(path).name}: '{role}' isn't one of this project's validation roles "
                f"({', '.join(sorted(roles)) or 'none'})."
            )
    for row, wanted, every, _ in actions:
        name = row["filename"]
        if not (wanted or every):
            continue
        filepath = _review_file(name)
        raw = _collect_folder(filepath.parent) if filepath else None
        if not raw:
            plan["refused"] += [
                (f"{name}: {d}", "file not found") for d in wanted or ["all"]
            ]
            continue
        status = _status_from_raw(raw)
        done_now = status.get("validated_departments", {})
        given = status.get("approvals") or {}
        if every:
            # Each department done now and not given its own value.
            for d in status.get("departments_required", []):
                if d in done_now:
                    wanted.setdefault(d, every)
        current = Path((status.get("stable_info") or {}).get("file") or "").stem
        seen = row.get("stable_version") or ""
        for department, choice in sorted(wanted.items()):
            label = f"{name}: {department}"
            if choice == "no" and role not in (given.get(department) or {}):
                continue  # nothing to withdraw (a retake on unvalidated work)
            if choice == "yes" and role in (given.get(department) or {}):
                plan["validations_known"] += 1  # given already: left as is
                continue
            if department not in status.get("departments_required", []):
                plan["refused"].append((label, "department not required"))
            elif seen and current and seen != current:
                plan["refused"].append(
                    (label, f"{current} made since {seen}: to review again")
                )
            elif choice == "yes" and department not in done_now:
                plan["refused"].append((label, "not done (yet, or any more)"))
            else:
                plan["validations"].append(
                    {
                        "name": name,
                        "filepath": str(filepath),
                        "department": department,
                        "approved": choice == "yes",
                        "stable": f"{seen}.blend" if seen else None,
                    }
                )
    return plan


def _known_notes(filepath: Path, author: str) -> set:
    """The notes this author's reviews already brought into filepath's
    tracking, by _note_key()."""
    return {
        _note_key(
            e.get("text"),
            e.get("shot"),
            e.get("frame_start"),
            e.get("frame_end"),
            e.get("departments") or [e.get("department")],
        )
        for e in (read_json_quiet(tracking_json_path(filepath)) or {}).get("entries", [])
        if e.get("source") == REVIEW_SOURCE and e.get("author") == author
    }


def _row_notes(filepath: Path, row: dict, notes: list) -> list[tuple]:
    """A row's note lines as they're imported: [(line, departments, type,
    shot, frames, key)] -- its departments the file's (unknown dropped), its
    [sh020] [f12-40] tags read. The same for the confirm dialog's count and
    the import itself, so both tell an already imported line alike."""
    shots = _file_shots(filepath)
    out = []
    for line, wanted_departments, entry_type in notes:
        # One department, or several: "layout, animation"; unknown dropped.
        departments = []
        for dep in wanted_departments:
            try:
                if valid_department(filepath, dep):
                    departments.append(dep)
            except PipelineError:
                pass
        line, shot, frames = _line_tags(line, shots)
        # A pre-1.1.2 template's own "shot" column, for all its lines.
        shot = shot or row.get("shot") or None
        key = _note_key(line, shot, *(frames or (None, None)), departments)
        out.append((line, departments, entry_type, shot, frames, key))
    return out


def _note_key(text, shot, f_start, f_end, departments) -> tuple:
    """What makes an imported review line the same as one already there."""
    return (
        text,
        shot or None,
        f_start,
        f_end if f_start is not None else None,
        frozenset(d for d in departments or () if d),
    )


def _render_at_snapshot(filepath: Path, snapshot: str) -> str:
    """A review without its "render" (before schema 5): the file's last
    render as _render_ref() writes it, if it already existed at `snapshot`
    (its folder last written before) -- what the page showed. A shot
    rendered again since: left out, never guessed. "" without a time."""
    try:
        made = datetime.fromisoformat(snapshot).timestamp()
    except ValueError:
        return ""
    root = get_active_project_root()
    if not root:
        return ""
    owner = filepath.parent
    try:
        kind = "shot" if owner.relative_to(root).parts[0] == "shots" else "asset"
    except ValueError:
        return ""
    v_prefix = json_get(ConfigCache.get(), "naming.version.prefix", "v")
    renders = read_render_state(root, kind, owner, v_prefix)
    seen = []
    for r in renders:
        try:
            if r.get("path") and os.stat(r["path"]).st_mtime <= made:
                seen.append(r)
        except OSError:
            pass
    # Per shot when one was left out: its notes must not take another's.
    return _render_ref(seen, per_shot=len(seen) < len(renders) and len(renders) > 1)


def import_review_xlsx(path: Path) -> dict:
    """Create one entry per line of each filled text cell of a review
    template, all sharing one review_id, stamped with the template's Author
    ("prod" if empty) and Review date (import time if empty), anchored on
    the version the snapshot showed. A line already imported (same file,
    text, shot, frames, departments and author, from a review) is
    skipped, so re-importing a file -- or a re-sent one with notes added,
    or another reviewer's on the same line -- never duplicates.
    Every note and validation under the template's Role (none for one made
    before 1.1.2) -- see review_import_plan().
    Retakes the reviewer marked fixed (the page's "fixed") are marked done,
    as its author (close_entry()).
    Replies ("reply <id>") go into their entry's thread under the role: a
    retake on its departments ("still to redo", the entry left open), or a
    remark when every line is "note:".
    Returns {"imported", "duplicates" (notes and replies already there),
    "validated", "same_validations" (already so), "fixed", "already_fixed"
    (done already), "replies", "skipped": [(label, reason)]}."""
    review = read_review(path)
    plan = review_import_plan(path, review)
    role = plan["role"] or None
    author = review["author"] or "prod"
    date = review["review_date"]
    created_at = date.isoformat(timespec="seconds") if date else None
    # What the reviewer could have watched: the snapshot's renders, else
    # those made by the end of the review day.
    seen_at = review.get("snapshot") or (
        datetime.combine(date.date(), datetime.max.time()).isoformat() if date else ""
    )
    review_id = hashlib.sha1(f"{now()}{Path(path).name}".encode()).hexdigest()[:5]
    result = {
        "imported": 0,
        "duplicates": 0,
        "validated": 0,
        "fixed": 0,
        "replies": 0,
        # Already so, left as it is (a review imported again): retakes done
        # since, validations already given.
        "already_fixed": 0,
        # Given already: the plan left them out of its changes.
        "same_validations": plan["validations_known"],
        "skipped": list(plan["refused"]),
    }
    # Retakes marked fixed: done, as the reviewer -- one already done, or
    # gone since, left as it is.
    for row in review["rows"]:
        ids = row.get("fixed", "").split()
        if not ids or not row.get("filename"):
            continue
        filepath = _review_file(row["filename"])
        if not filepath:
            result["skipped"].append(
                (f"{row['filename']}: {len(ids)} retake(s) fixed", "file not found")
            )
            continue
        for entry_id in ids:
            try:
                closed = close_entry(filepath, entry_id, author)
                if closed:
                    result["fixed"] += 1
                elif closed is False:
                    result["already_fixed"] += 1
                else:
                    result["skipped"].append(
                        (f"{row['filename']}: retake fixed", "its note is gone")
                    )
            except PipelineError as e:
                result["skipped"].append((f"{row['filename']}: retake fixed", e.message))
    # Replies: each in its entry's thread, a note under the review's role --
    # the retake it answers left open. The same reply from the same author
    # once only (an import run twice).
    for row in review["rows"]:
        replies = _row_replies(row)
        if not replies or not row.get("filename"):
            continue
        filepath = _review_file(row["filename"])
        if not filepath:
            result["skipped"].append(
                (f"{row['filename']}: {len(replies)} reply(ies)", "file not found")
            )
            continue
        entries = (read_json_quiet(tracking_json_path(filepath)) or {}).get("entries", [])
        by_id = {e.get("id"): e for e in entries}
        ids = set(by_id)
        known = {
            (e.get("response"), e.get("text"))
            for e in entries
            if e.get("response") and e.get("author") == author
        }
        for entry_id, text in replies:
            if entry_id not in ids:
                result["skipped"].append(
                    (f"{row['filename']}: reply {text[:30]}", "its note is gone")
                )
                continue
            # A retake answering it is on its departments (none: the whole
            # file's); a "note:" one, a remark.
            entry_type, text = _reply_kind(text)
            if (entry_id, text) in known:
                result["duplicates"] += 1
                continue
            departments = (
                entry_departments(by_id[entry_id]) if entry_type == "rtk" else []
            )
            try:
                create_entry(
                    filepath,
                    text=text,
                    departments=departments,
                    author=author,
                    type=entry_type,
                    response=entry_id,
                    review_id=review_id,
                    created_at=created_at,
                    source=REVIEW_SOURCE,
                    role=role,
                )
                known.add((entry_id, text))
                result["replies"] += 1
            except PipelineError as e:
                result["skipped"].append((f"{row['filename']}: reply", e.message))
    for v in plan["validations"]:
        try:
            if set_department_approval(
                Path(v["filepath"]),
                department=v["department"],
                role=role,
                approved=v["approved"],
                user=author,
                stable_file=v["stable"],
            ):
                result["validated"] += 1
            else:
                result["same_validations"] += 1
        except PipelineError as e:
            result["skipped"].append((f"{v['name']}: {v['department']}", e.message))
    for row in review["rows"]:
        if not row.get("filename"):
            continue
        # One line of a text cell = one entry (see NOTES.md, "Batched review
        # input, still one entry each"); a typed bullet is dropped.
        _, _, notes = _row_actions(row, review["schema_version"])
        if not notes:
            continue
        name = row["filename"]
        filepath = _review_file(name)
        row_render = ""
        if filepath:
            row_render = row.get(RENDER_WATCHED) or _render_at_snapshot(filepath, seen_at)
        if not filepath:
            result["skipped"].extend(
                (
                    f"{name}: {line[:40]}",
                    "file not found (renamed, branched or archived?)",
                )
                for line, _, _ in notes
            )
            continue
        # The same words on another shot, frames or department are another
        # retake: "[sh170] too dark" and "[sh180] too dark" are two.
        known = _known_notes(filepath, author)
        for line, departments, entry_type, shot, frames, key in _row_notes(
            filepath, row, notes
        ):
            if key in known:
                result["duplicates"] += 1
                continue
            # The version the reviewer watched: the one its render was made
            # from (v007-stable_001 -> ..._v007-stable.blend), else the file.
            render = render_of_note(row_render, shot)
            watched = filepath
            if render:
                version = render.rsplit("_", 1)[0]
                watched = filepath.with_name(
                    f"{filepath.stem.rsplit('_', 1)[0]}_{version}.blend"
                )
            try:
                create_entry(
                    filepath,
                    text=line,
                    departments=departments,
                    author=author,
                    type=entry_type,
                    shot=shot,
                    f_start=frames[0] if frames else None,
                    f_end=frames[1] if frames else None,
                    review_id=review_id,
                    created_at=created_at,
                    referenced_version=str(watched),
                    render=render,
                    source=REVIEW_SOURCE,
                    role=role,
                )
                known.add(key)
                result["imported"] += 1
            except PipelineError as e:
                result["skipped"].append((f"{name}: {line[:40]}", e.message))
    return result


def review_description_changes(path: Path) -> list[dict]:
    """[{"name", "filepath", "old", "new"}] for every row of a review
    template whose description the prod edited -- the cell differs from
    the description exported with it (description_exported) -- and that
    still differs from the file's current one. A template without that
    column (schema 1, description locked) has none: comparing with the
    current description would revert every one changed since the export.
    An empty cell is no change: the prod not writing one must never wipe a
    description out."""
    review = read_review(path)
    if "description_exported" not in review["columns"]:
        return []
    changes, seen = [], set()
    for row in review["rows"]:
        name = row.get("filename")
        new = (row.get("description") or "").strip()
        if not name or not new or name in seen:
            continue
        seen.add(name)
        try:
            filepath = find_file_by_name(
                name if name.endswith(".blend") else f"{name}.blend"
            )
        except PipelineError:
            filepath = None
        if not filepath:
            continue  # reported by import_review_xlsx() already
        tracking = read_json_quiet(tracking_json_path(filepath)) or {}
        old = (tracking.get("description") or "").strip()
        if new == (row.get("description_exported") or "").strip():
            continue  # untouched by the prod, whatever happened since
        if new != old:
            changes.append(
                {"name": name, "filepath": str(filepath), "old": old, "new": new}
            )
    return changes
