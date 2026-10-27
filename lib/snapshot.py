"""Production snapshot: one self-contained HTML page of the project's state
for people outside the studio, with a review spreadsheet embedded in it that
they fill in and send back (see NOTES.md, "Production snapshot")."""

import base64
import hashlib
import html
import io
import json
import math
import os
import re
import threading
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from .background import background_work
from .config import (
    ConfigCache,
    covering_role,
    parse_filename,
    shots_in_segment,
    validation_roles,
)
from .core import json_get, now, read_json_quiet
from .errors import PipelineError
from .preview import latest_render_dir, render_root
from .thumbnails import (
    jpeg_size_of,
    owner_shot_render_dirs,
    owner_thumbnail_dirs,
    run_thumbnail_jobs,
    thumbnail_jobs,
    thumbnail_path,
    thumbnail_size,
)
from .tracking import (
    _DATA_ROOTS,
    _collect_folder,
    _pipeline_entries,
    _status_from_raw,
    _walk_owner_dirs,
    create_entry,
    entry_departments,
    find_file_by_name,
    owner_key,
    render_to_check_label,
    set_department_approval,
    tracking_json_path,
    valid_department,
)

# Bumped whenever the review template's columns change -- the import refuses
# a template made by a newer addon.
SCHEMA_VERSION = 4  # 2: hidden description_exported column; 3: role, "valid <dept>"; 4: a sheet per section, a cell per department

ENTRY_TYPES = ("note", "todo", "rtk")

# Department state -> (label, css class). "rework" is done at the last
# stable AND worked since: never shown as plain "done".
STATES = {
    "done": ("Done", "st-done"),
    "rework": ("Done, reworked since", "st-rework"),
    "wip": ("Work in progress", "st-wip"),
    "todo": ("Not started", "st-todo"),
}
# What a table cell shows: six departments of full labels don't fit a page.
# The full label is its tooltip and in the legend.
SHORT_STATES = {
    "done": "Done",
    "rework": "Reworked",
    "wip": "WIP",
    "todo": "Not started",
}

# Share of a department counted as done per state, in % -- the project's
# "snapshot.progress" (Edit project) overrides each. Validated counts 100,
# not started 0. "rtk": validated, with an open RTK.
PROGRESS_WEIGHTS = {"wip": 33, "rework": 67, "rtk": 67}

# Entry "source" stamped on every note imported from a review template.
REVIEW_SOURCE = "prod_review"

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------


def read_snapshot_raw(root: Path) -> list[tuple[str, Path, dict, list[str]]]:
    """(kind, owner folder, _collect_folder() data, .blend names) for every
    tracked folder. Disk only, pure os/json: thread-safe."""
    out = []
    for top in _DATA_ROOTS:
        kind = "shot" if top == "shots" else "asset"
        for owner in _walk_owner_dirs(root / top):
            raw = _collect_folder(owner, _pipeline_entries(owner))
            if raw is None:
                continue
            try:
                blends = [
                    e.name for e in os.scandir(owner) if e.name.endswith(".blend")
                ]
            except OSError:
                blends = []
            out.append((kind, owner, raw, blends))
    return out


def _owner_shots(owner: Path) -> list[str]:
    """A shot folder's shots: ["sh040"], or ["sh040", "sh050", "sh060"] for
    a block "sh040-050-060". Name parsing only, no config."""
    first, *rest = owner.name.split("-")
    m = re.match(r"(\D*)(\d+)$", first)
    if not m:
        return [owner.name]
    return [first] + [f"{m[1]}{n.zfill(len(m[2]))}" for n in rest]


def read_render_state(root: Path, kind: str, owner: Path, v_prefix: str = "v") -> list:
    """What was last rendered for an asset/shot folder, per shot (a block
    has several, anything else one): [{"shot", "file", "folder", "path",
    "frame_machines", "machine_seconds"}] (the last two None without them),
    path the render folder's absolute path. From the
    folder's render_history.json -- its last finished render of that shot,
    file = the .blend it rendered -- else (no such entry, or an entry from
    before source_file came after it) from the latest render folder's own
    name (renders/<seq>/<shot>/v004-stable_002). Pure os/json: thread-safe."""
    history = read_json_quiet(owner / ".pipeline" / "render_history.json") or {}
    finished = [
        e
        for e in history.get("entries", [])
        if isinstance(e, dict) and e.get("status") == "finished"
    ]
    base = render_root(root, owner)
    shots = _owner_shots(owner) if kind == "shot" else [""]
    block = len(shots) > 1

    def last_render(shot: str, mine: list, folder_dir: Path) -> dict:
        # An older version's entry (no source_file, no shot_override) after
        # it may be a newer render of this shot: the folder name knows.
        if mine and all(e.get("source_file") for e in finished[mine[-1] + 1 :]):
            last = finished[mine[-1]]
            output = last.get("output_path")
            folder = (Path(root) / output).parent if output else None
            return {
                "shot": shot,
                "file": Path(last["source_file"]).name,
                "folder": folder.name if folder else None,
                "path": str(folder) if folder else None,
                # Which machine wrote each frame, and their pace
                # (farm queue._note_frames()): File details' lookup.
                "frame_machines": last.get("frame_machines"),
                "machine_seconds": last.get("machine_seconds"),
            }
        latest = latest_render_dir(folder_dir, v_prefix)
        return {
            "shot": shot,
            "file": None,
            "folder": latest.name if latest else None,
            "path": str(latest) if latest else None,
        }

    out = []
    for shot in shots:
        # A block's history holds every shot it rendered, told apart by
        # shot_override; a mono shot's or an asset's is all its own.
        mine = [
            i
            for i, e in enumerate(finished)
            if e.get("source_file") and (not block or e.get("shot_override") == shot)
        ]
        out.append(last_render(shot, mine, base.with_name(shot) if shot else base))
    if block:
        # The block rendered whole (no split per shot: renders/<seq>/
        # sh030-040/...): each shot's last render is the newer of its own
        # and that one ("whole": the to-check label is the folder alone).
        mine = [
            i
            for i, e in enumerate(finished)
            if e.get("source_file") and not e.get("shot_override")
        ]
        whole = last_render("", mine, base)
        if whole["path"]:
            out = [
                dict(whole, shot=r["shot"], whole=True)
                if _render_order(whole["folder"]) > _render_order(r["folder"])
                else r
                for r in out
            ]
    return out


_RENDER_FOLDER = re.compile(r"(\d+)(?:-[a-z]+)?_(\d+)$")


def _render_order(folder: str | None) -> tuple[int, int]:
    """A render folder's (version, increment) -- v004-stable_002 -> (4, 2);
    (-1, -1) for none."""
    m = _RENDER_FOLDER.search(folder or "")
    return (int(m[1]), int(m[2])) if m else (-1, -1)


def group_renders(renders: list, key: str = "folder") -> list[tuple[list, dict]]:
    """A folder's last renders (read_render_state()) grouped by render:
    [(its shots, the render)], in the block's order -- five shots of one
    render are one line, not five. key "folder": the same folder name is
    the same render (a split render writes one per shot -- the snapshot);
    "path": the very same folder (File details, whose buttons open it)."""
    groups: dict = {}
    for r in renders:
        groups.setdefault((r.get(key), bool(r.get("whole"))), (r, []))[1].append(
            r["shot"]
        )
    return [(shots, r) for r, shots in groups.values()]


def shots_label(shots: list, every: list) -> str:
    """ "sh020-030-040", as a block's name -- "" when that's every shot."""
    if len(shots) == len(every) and len(every) > 1:
        return ""
    first, *rest = shots
    prefix = first.rstrip("0123456789")
    return "-".join(
        [first, *(s[len(prefix) :] if s.startswith(prefix) else s for s in rest)]
    )


def read_snapshot_data(
    root: Path, thumbnails: dict | None = None, v_prefix: str = "v"
) -> dict:
    """read_snapshot_raw() plus each folder's last render
    (read_render_state()) and thumbnails: those missing or older than
    their latest render are remade first (one headless Blender, waited on
    -- run this on a thread). thumbnails: {"size", "blender", "ffmpeg"},
    None to skip them. Returns {"raws", "renders": {owner:
    [...]}, "thumbs": {owner: base64 JPEG}, "shot_thumbs": {block owner:
    [(shot label, base64 JPEG or None)]}, "thumb_warnings": [...]}."""
    raws = read_snapshot_raw(root)
    renders = {
        str(owner): read_render_state(root, kind, owner, v_prefix)
        for kind, owner, raw, _ in raws
        if not raw["tracking"].get("archived")
    }
    thumbs, shot_thumbs, warnings = {}, {}, []
    if thumbnails is not None:
        dirs, shot_dirs = {}, {}
        for _, owner, raw, _ in raws:
            if not raw["tracking"].get("archived"):
                dirs[str(owner)] = owner_thumbnail_dirs(root, owner)
                # A block: every shot's own, to find one's way in the edit.
                if shots := owner_shot_render_dirs(root, owner):
                    shot_dirs[str(owner)] = shots
        size = thumbnails.get("size") or thumbnail_size({})
        every = dict.fromkeys(
            [
                *(d for candidates in dirs.values() for d in candidates),
                *(d for shots in shot_dirs.values() for _, d in shots),
            ]
        )
        jobs = thumbnail_jobs(every, v_prefix, size=size)
        results = run_thumbnail_jobs(
            jobs, thumbnails["blender"], thumbnails.get("ffmpeg"), size=size
        )
        warnings = [
            f"{Path(dst).name}: {why}" for dst, why in results.items() if why != "ok"
        ]

        def encoded(d: Path) -> str | None:
            try:  # an older thumbnail still beats none
                return base64.b64encode(thumbnail_path(d).read_bytes()).decode("ascii")
            except OSError:
                return None

        for owner, candidates in dirs.items():
            b64 = next((b for d in candidates if (b := encoded(d)) is not None), None)
            if b64 is not None:
                thumbs[owner] = b64
        for owner, shots in shot_dirs.items():
            found = [(label, encoded(d)) for label, d in shots]
            if any(b64 for _, b64 in found):
                shot_thumbs[owner] = found
    return {
        "raws": raws,
        "renders": renders,
        "thumbs": thumbs,
        "shot_thumbs": shot_thumbs,
        "thumb_warnings": warnings,
    }


def build_snapshot(data, config: dict, meta: dict, farm: dict | None = None) -> dict:
    """Neutral snapshot dict from read_snapshot_data()'s result (or a bare
    read_snapshot_raw() list): {"meta", "assets", "shots", "notes"}. farm:
    the farm's jobs still to go by folder (farm_activity()). Memory only,
    main thread (_status_from_raw() reads ConfigCache)."""
    if isinstance(data, list):
        data = {"raws": data, "thumbs": {}, "thumb_warnings": []}
    raws = data["raws"]
    weights = progress_weights(config)
    roles = validation_roles(config)
    top_role = top_validation_role(roles)
    v_prefix = json_get(config, "naming.version.prefix", "v")
    version_re = re.compile(rf"_{re.escape(v_prefix)}(\d+)(-[a-z]+)?\.blend$")
    folder_re = re.compile(rf"^{re.escape(v_prefix)}(\d+)(-[a-z]+)?_\d+$")
    items = {"asset": [], "shot": []}
    notes = []
    for kind, owner, raw, blends in raws:
        status = _status_from_raw(raw)
        if status.get("archived"):
            continue
        name = status.get("file_name") or owner.name
        wips = [
            (int(m[1]), b) for b in blends if (m := version_re.search(b)) and not m[2]
        ]
        stable_file = (status.get("stable_info") or {}).get("file")
        stable_name = Path(stable_file).name if stable_file else None
        stable_m = version_re.search(stable_name or "")
        stable_n = int(stable_m[1]) if stable_m else -1
        wip_n, wip_name = max(wips) if wips else (-1, None)
        item = {
            "name": name,
            "kind": kind,
            "group": name.split("_", 1)[0],
            "description": status.get("description", ""),
            "departments_required": list(status.get("departments_required", [])),
            "departments": {
                d: _department_state(status, d)
                for d in status.get("departments_required", [])
            },
            "wip_version": wip_name,
            # Work on top of the last stable (a wip made after it), else none
            # to show: the Blender file column names the stable alone.
            "wip_after_stable": wip_n > stable_n,
            "stable_version": stable_name,
            # What the prod sees and what its notes get anchored on: the
            # most recent of the two (a stable can be newer than any wip).
            "current_version": wip_name
            if wip_n > stable_n
            else stable_name or wip_name,
            "thumbnail": data["thumbs"].get(str(owner)),
            # A block's shots, each its own thumbnail (None: not rendered).
            "shot_thumbnails": [
                list(t) for t in data.get("shot_thumbs", {}).get(str(owner), [])
            ],
        }
        # A render's folder is vXXX_YYY: XXX the .blend version rendered,
        # YYY the render increment. The history's source_file says XXX
        # first-hand; the folder name is the fallback.
        renders = []
        for r in data.get("renders", {}).get(str(owner), []):
            m = version_re.search(r["file"] or "") or folder_re.match(r["folder"] or "")
            renders.append(
                {
                    "shot": r["shot"],
                    "folder": r["folder"],
                    "whole": bool(r.get("whole")),
                    "file_number": int(m[1]) if m else None,
                }
            )
        item["renders"] = renders
        # Rendered, not checked by the team yet / still in the farm.
        to_check = status.get("to_check")
        if not isinstance(to_check, dict):
            to_check = {}
        item["to_check"] = [
            render_to_check_label(shot, info)
            for shot, info in sorted(to_check.items())
            if isinstance(info, dict)
        ]
        item["farm"] = (farm or {}).get(owner_key(owner), [])
        # What the prod must see: a render made from an older .blend than
        # the last stable -- the picture lags the validated work.
        item["stable_number"] = stable_n
        item["render_behind"] = stable_n >= 0 and any(
            r["file_number"] is not None and r["file_number"] < stable_n
            for r in renders
        )
        # Every thread: the snapshot is a record. Closed ones are only
        # hidden by the page (_JS, "Show closed").
        threads = [
            _thread_dict(name, t, closed=_thread_closed(t))
            for box in status.get("entries_grouped", [])
            for t in box["threads"]
        ]
        open_threads = [t for t in threads if not t["closed"]]
        item["open_rtk"] = sum(
            1
            for t in open_threads
            for e in [t, *t["replies"]]
            if e["type"] == "rtk" and e["done"] is False
        )
        item["open_notes"] = len(open_threads)
        rtk_departments = {
            d
            for t in open_threads
            for e in [t, *t["replies"]]
            if e["type"] == "rtk" and e["done"] is False
            for d in e["departments"]
        }
        item["rtk_departments"] = sorted(rtk_departments)
        # Per done department: its validations at the stable shown, and the
        # last ones given to an earlier stable (to review again).
        item["approvals"] = {
            d: {r: dict(info) for r, info in roles.items()}
            for d, roles in (status.get("approvals") or {}).items()
        }
        item["approvals_previous"] = {
            d: {r: dict(info) for r, info in roles.items()}
            for d, roles in (status.get("approvals_previous") or {}).items()
            if d in item["departments"]
        }
        # Per department, then their mean: the footer averages the first.
        item["scores"] = {
            d: _department_score(st, d in rtk_departments, weights)
            for d, st in item["departments"].items()
        }
        scores = list(item["scores"].values())
        item["progress"] = sum(scores) / len(scores) if scores else None
        # Apart from Done: the share of the required departments the top
        # role (or an equivalent one) validated at the stable shown.
        item["validated"] = {
            d: bool(
                top_role
                and covering_role(item["approvals"].get(d) or {}, top_role, roles)
            )
            for d in item["departments"]
        }
        valid = list(item["validated"].values())
        item["validation"] = sum(valid) / len(valid) if valid else None
        items[kind].append(item)
        notes.extend(threads)

    for k in items:
        items[k].sort(key=lambda i: i["name"])
    notes.sort(key=lambda n: (n["item"], n["last_activity"]), reverse=False)
    meta = dict(meta)
    meta.setdefault("schema_version", SCHEMA_VERSION)
    meta["thumbnail_warnings"] = list(data["thumb_warnings"])
    meta["thumbnail_size"] = thumbnail_size(config)
    meta["progress"] = {k: average_progress(v) for k, v in items.items()}
    meta["progress_weights"] = weights
    meta["validation_roles"] = roles
    meta["validation_role"] = top_role
    meta["validation"] = {
        k: average_progress(v, "validation") for k, v in items.items()
    }
    schedule = project_schedule(config)
    if schedule:
        today = datetime.fromisoformat(meta.get("scan_started_at") or now()).date()
        meta["schedule"] = schedule_progress(schedule, today, meta["progress"])
    meta["asset_departments"] = _columns(
        json_get(config, "assets_departments", []), items["asset"]
    )
    meta["shot_departments"] = _columns(
        json_get(config, "shots_departments", []), items["shot"]
    )
    return {
        "meta": meta,
        "assets": items["asset"],
        "shots": items["shot"],
        "notes": notes,
    }


def _department_state(status: dict, department: str) -> str:
    """done / rework (validated at the latest stable, worked since or not),
    wip (worked since, or started before: validated at an earlier stable or
    worked before the latest one), todo (never)."""
    validated = department in status.get("validated_departments", {})
    worked = department in status.get("worked_departments", {})
    if validated:
        return "rework" if worked else "done"
    started = department in status.get("started_departments", ())
    return "wip" if worked or started else "todo"


def progress_weights(config: dict) -> dict[str, int]:
    """PROGRESS_WEIGHTS with the project's own values, each kept 0..100."""
    out = {}
    for key, default in PROGRESS_WEIGHTS.items():
        try:
            value = int(json_get(config, f"snapshot.progress.{key}", default))
        except (TypeError, ValueError):
            value = default
        out[key] = max(0, min(100, value))
    return out


def _department_score(state: str, open_rtk: bool, weights: dict) -> float:
    """One department's share done, 0..1: validated 1 (its "rtk" weight
    with an open RTK), not started 0, else its state's weight."""
    if state == "done":
        return weights["rtk"] / 100 if open_rtk else 1.0
    return weights.get(state, 0) / 100


def top_validation_role(roles: list) -> str | None:
    """The role the "Validated" figures count: the highest level's (its
    equivalents cover it). None without any role."""
    return max(roles, key=lambda r: r["level"])["name"] if roles else None


def department_progress(items: list, department: str) -> float | None:
    """Mean of one department over the items requiring it, None if none
    does -- the snapshot table's per-department footer."""
    values = [i["scores"][department] for i in items if department in i["scores"]]
    return sum(values) / len(values) if values else None


def average_progress(items: list, key: str = "progress") -> float | None:
    """Mean progress of items (key "validation": their Validated), each
    weighing the same; those without any required department left out.
    None if none is left."""
    values = [i[key] for i in items if i.get(key) is not None]
    return sum(values) / len(values) if values else None


def parse_day(value: str) -> date:
    """A date typed day first -- 20/10/2026, 20-10-2026, 20.10.2026 -- or
    year first (2026-10-20, 2026/10/20). Raises PipelineError otherwise."""
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise PipelineError(f"'{value}' is not a date (DD/MM/YYYY).")


# ISO weekday numbers (1 Monday .. 7 Sunday) a schedule works by default.
WORK_WEEK = (1, 2, 3, 4, 5)


def project_schedule(config: dict) -> dict | None:
    """The project's "snapshot.schedule" (Edit project): {"start", "end",
    "days_off" (dates), "worked_days" (ISO weekday numbers, WORK_WEEK when
    unset)}. None unless start and end are both set, in order, and some
    day of the week is worked."""
    raw = json_get(config, "snapshot.schedule", {}) or {}
    try:
        start = date.fromisoformat(raw["start"])
        end = date.fromisoformat(raw["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if end < start:
        return None
    days_off = set()
    for day in raw.get("days_off") or []:
        try:
            days_off.add(date.fromisoformat(day))
        except (TypeError, ValueError):
            pass
    try:
        weekdays = sorted(
            {int(d) for d in raw.get("worked_days", WORK_WEEK)} & set(range(1, 8))
        )
    except (TypeError, ValueError):
        weekdays = list(WORK_WEEK)
    if not weekdays:
        return None
    return {"start": start, "end": end, "days_off": days_off, "worked_days": weekdays}


def _is_working_day(schedule: dict, day: date) -> bool:
    """Whether day counts in the schedule: a worked weekday, not a day off."""
    return (
        day.isoweekday() in schedule["worked_days"] and day not in schedule["days_off"]
    )


def working_days(schedule: dict, start: date, end: date) -> int:
    """The schedule's working days from start to end, both included: its
    worked days of the week, its days off left out -- a spreadsheet's
    NETWORKDAYS.INTL(). 0 when end is before start."""
    count, day = 0, start
    while day <= end:
        count += _is_working_day(schedule, day)
        day += timedelta(days=1)
    return count


def nth_working_day(schedule: dict, n: int) -> date:
    """The schedule's n-th working day (1: the first), its end past the last."""
    count, day = 0, schedule["start"]
    while day < schedule["end"]:
        count += _is_working_day(schedule, day)
        if count >= max(n, 1):
            return day
        day += timedelta(days=1)
    return schedule["end"]


def schedule_progress(schedule: dict, today: date, progress: dict) -> dict:
    """meta["schedule"]: the schedule (ISO dates) and where the project
    should be on today at an even pace -- "expected" (0..1), its working
    days so far, today included ("elapsed_days"), over all of them
    ("total_days"). "at": per section of progress ({kind: Done or None}),
    the day an even pace reaches its Done and how many working days ahead
    (+) or behind (-) of today that is."""
    start, end = schedule["start"], schedule["end"]
    total = working_days(schedule, start, end)
    elapsed = working_days(schedule, start, min(today, end))
    at = {}
    for kind, done in progress.items():
        if done is not None:
            days = done * total
            at[kind] = {
                "date": nth_working_day(schedule, math.ceil(days)).isoformat(),
                "days": round(days - elapsed),
            }
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "worked_days": list(schedule["worked_days"]),
        "days_off": sorted(d.isoformat() for d in schedule["days_off"]),
        "expected": elapsed / total if total else float(today >= end),
        "elapsed_days": elapsed,
        "total_days": total,
        "at": at,
    }


def _pct(value: float | None) -> str:
    return "–" if value is None else f"{round(value * 100)} %"


def _day(iso: str) -> str:
    """ "2026-10-20..." -> "20/10/2026": day before month."""
    return f"{datetime.fromisoformat(iso):%d/%m/%Y}"


def _columns(configured: list, items: list) -> list:
    """Config's department order, plus any department an item requires that
    the config no longer lists."""
    cols = list(configured)
    for item in items:
        for d in item["departments_required"]:
            if d not in cols:
                cols.append(d)
    return cols


def _entry_dict(e: dict) -> dict:
    """An entry as the snapshot page shows it: plain fields, its departments
    joined for the tag."""
    version = e.get("referenced_version")
    return {
        "type": e.get("type", "note"),
        "text": e.get("text", ""),
        "author": e.get("author", ""),
        "date": e.get("created_at", ""),
        "department": ", ".join(entry_departments(e)),
        "departments": entry_departments(e),
        "version": Path(version).name if version else "",
        "shot": e.get("shot", ""),
        "frames": _frames_label(e),
        "done": e.get("done"),
        "from_review": e.get("source") == REVIEW_SOURCE,
        # The validation role it was written under, "" the team's own.
        "role": e.get("role") or "",
    }


def _frames_label(e: dict) -> str:
    """ "f12-40" / "f12" for an entry tied to frames, "" otherwise."""
    start, end = e.get("frame_start"), e.get("frame_end")
    if start is None:
        return ""
    return f"f{start}-{end}" if end is not None else f"f{start}"


def _thread_closed(thread: dict) -> bool:
    """Done root and no reply still pending: what filter_review_boxes()'s
    hide_done drops (see its docstring)."""
    return thread["root"].get("done") is True and not any(
        r.get("done") is False for r in thread["replies"]
    )


def _thread_dict(item_name: str, thread: dict, closed: bool = False) -> dict:
    """A thread (root + replies) as the snapshot page shows it, tagged with
    its item and whether it's closed."""
    return {
        "item": item_name,
        **_entry_dict(thread["root"]),
        "replies": [_entry_dict(r) for r in thread["replies"]],
        "last_activity": thread["meta"]["date_end"],
        "closed": closed,
    }


class SnapshotJob:
    """Run fn(*args) on a thread, polled from the main thread (done/result/
    error). The export runs two: the disk read, then render+write -- only
    build_snapshot() runs on the main thread, memory only."""

    def __init__(self, fn, *args):
        self.started_at = now()
        self.result = None
        self.error = None
        self.done = False
        self._thread = threading.Thread(
            target=self._run, args=(fn, args), daemon=True, name="pipeline-snapshot"
        )
        self._thread.start()

    def _run(self, fn, args) -> None:
        try:
            with background_work():
                self.result = fn(*args)
        except Exception as e:  # reported by the caller
            self.error = repr(e)
        self.done = True


def write_snapshot(snapshot: dict, filepath: Path) -> Path:
    """render_html() written to filepath. Pure: thread-safe."""
    Path(filepath).write_text(render_html(snapshot), encoding="utf-8")
    return Path(filepath)


def snapshot_filename(snapshot: dict, ext: str = "html", kind: str = "snapshot") -> str:
    """<project>_<kind>_<YYYY-MM-DD>_<HH-MM>.<ext>, from the scan's start --
    several exports a day never overwrite each other."""
    meta = snapshot["meta"]
    project = (
        re.sub(r"[^\w\-]+", "_", meta.get("project") or "").strip("_") or "project"
    )
    stamp = (
        (meta.get("scan_started_at") or now())[:16].replace("T", "_").replace(":", "-")
    )
    return f"{project}_{kind}_{stamp}.{ext}"


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def _e(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _section(anchor: str, heading: str, body: str) -> str:
    """A page section, folded and unfolded by a click on its heading -- open
    at load (_JS opens it again for a link into it, and for printing)."""
    return (
        f'<section id="{anchor}"><details class="sec" open><summary><h2>{heading}'
        f"</h2></summary>{body}</details></section>"
    )


def render_html(snapshot: dict) -> str:
    """The whole snapshot as one offline HTML page (CSS/JS inline, review
    template embedded as a data: link)."""
    meta = snapshot["meta"]
    # Wrapped like a mail attachment: a URL's newlines are dropped by the
    # browser, the raw source stays readable.
    xlsx = base64.encodebytes(render_review_xlsx(snapshot)).decode("ascii").strip()
    xlsx_name = snapshot_filename(snapshot, "xlsx", "review")
    scan_date = (meta.get("scan_started_at") or "").replace("T", " ")
    weights = meta.get("progress_weights") or PROGRESS_WEIGHTS
    legend = "".join(
        f'<span class="pill {cls}">{_e(SHORT_STATES[k])}</span>'
        + (
            f'<span class="muted">{_e(label)}</span>'
            if label != SHORT_STATES[k]
            else ""
        )
        for k, (label, cls) in STATES.items()
    ) + (
        '<span class="pill st-none">Not required</span>'
        '<span class="pill st-todo rtk-open">Open RTK</span>'
        '<span class="muted">red outline, whatever the state</span>'
        '<span class="pill behind">⚠ Render older than the stable</span>'
        '<span class="pill tocheck">to check</span>'
        '<span class="muted">not checked yet</span>'
        '<span class="pill farm-waiting">queued</span>'
        '<span class="pill farm-running">rendering 45/120</span>'
        '<span class="pill farm-failed">failed</span>'
        '<span class="muted">in the farm</span>'
    )

    notes: dict[str, list] = {}
    for thread in snapshot["notes"]:
        notes.setdefault(thread["item"], []).append(thread)
    body = [
        "<header>",
        f"<h1>{_e(meta.get('project'))}</h1>",
        '<dl class="meta">',
        f"<div><dt>Snapshot</dt><dd>{_e(scan_date)}</dd></div>",
        f"<div><dt>Exported by</dt><dd>{_e(meta.get('exported_by'))}</dd></div>",
        f"<div><dt>Addon</dt><dd>Minimalist Pipeline {_e(meta.get('addon_version'))}</dd></div>",
        "</dl>",
        '<div class="review">',
        _review_bar(),
        # The spreadsheet, aside: for several reviewers or a shared drive.
        '<div class="rvside">'
        f'<a class="btn small ghost" download="{_e(xlsx_name)}" '
        f'href="data:{XLSX_MIME};base64,\n{xlsx}\n">Spreadsheet (.xlsx)</a>',
        "<p>Or offline, for several reviewers or a shared drive.</p></div>",
        "</div>",
        "</header>",
        # What the in-page review needs to write a file the import reads.
        '<script type="application/json" id="review-meta">'
        + json.dumps(
            {
                "project": meta.get("project") or "",
                "snapshot": meta.get("scan_started_at") or "",
                "roles": [r["name"] for r in meta.get("validation_roles", [])],
                "schema_version": SCHEMA_VERSION,
                "format": REVIEW_JSON_FORMAT,
                "file_name": snapshot_filename(snapshot, "json", "review"),
            }
        ).replace("</", "<\\/")
        + "</script>",
        _render_overview(snapshot),
        "<nav>",
        _render_filters(snapshot),
        "</nav>",
        f'<p class="legend">{legend}</p>',
        '<p class="legend muted">Done: each required department counts for an '
        f"equal share: work in progress {weights['wip']} %, done but "
        f"reworked since {weights['rework']} %, done with an open RTK "
        f"{weights['rtk']} %, done 100 %. Totals and groups average "
        "their assets/shots."
        + (
            f" Validated, apart: the share of the required departments "
            f"{_e(meta['validation_role'])} (or an equivalent role) validated at "
            "the stable shown -- a newer stable needs it again."
            if meta.get("validation_role")
            else ""
        )
        + "</p>",
        _render_table(
            "assets",
            "Assets",
            snapshot["assets"],
            meta["asset_departments"],
            notes,
            meta.get("validation_roles", []),
        ),
        _render_table(
            "shots",
            "Shots",
            snapshot["shots"],
            meta["shot_departments"],
            notes,
            meta.get("validation_roles", []),
        ),
    ]
    title = f"{meta.get('project') or 'Project'} snapshot {scan_date[:10]}"
    # Hover shows a thumbnail at its own size (the project setting), from
    # its 112 px wide cell.
    zoom = max(1.0, round((meta.get("thumbnail_size") or 240) / 112, 2))
    # One element per line: readable/diffable raw source, same rendering.
    nl = "\n"
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title>\n<style>{_CSS}:root{{--thumb-zoom:{zoom}}}</style>\n</head>"
        f"<body>\n{nl.join(body)}\n<script>{_JS}</script>\n</body></html>\n"
    )


# The overview's stacked bar of department tasks, in this order: their
# state, or "rtk" for one with an open RTK, whatever its state. Coloured as
# the table's pills (reworked: a lighter green); the order keeps green away
# from amber, a pair colour-blind readers can't tell apart.
_TASK_STATES = ("done", "rework", "rtk", "wip", "todo")
_TASK_LABELS = {**SHORT_STATES, "rtk": "Open RTK"}
_TASK_TIPS = {k: label for k, (label, _) in STATES.items()} | {
    "rtk": "Open RTK, whatever its state"
}
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _render_overview(snapshot: dict) -> str:
    """ "Progress" block between the header and the filters -- the whole
    project at export time, filters aside: stat tiles (each section's Done,
    against the schedule's expected progress when the project has one; the
    open RTKs), then a card per section: its departments' states, its Done
    by group and by department."""
    meta = snapshot["meta"]
    day = _day(meta.get("scan_started_at") or now())
    schedule = meta.get("schedule")
    expected = schedule["expected"] if schedule else None
    sections = (
        ("shot", "Shots", "By sequence", "shot", snapshot["shots"]),
        ("asset", "Assets & libraries", "By prefix", "file", snapshot["assets"]),
    )
    # Each section's Done, then apart what the top role accepted of it
    # (pre-1.1.2 snapshots lack it).
    role = meta.get("validation_role")
    validation = meta.get("validation") or {}
    tiles = []
    for kind, title, _, _, _ in sections:
        if meta["progress"][kind] is None:
            continue
        tiles.append(
            _stat_tile(
                f"{title} done",
                _pct(meta["progress"][kind]),
                _schedule_delta(meta["progress"][kind], expected),
            )
        )
        if role and validation.get(kind) is not None:
            tiles.append(
                _stat_tile(
                    f"{title} validated",
                    _pct(validation[kind]),
                    f'<span class="delta">by {_e(role)} (or equivalent)</span>',
                    "valid",
                )
            )
    if schedule:
        tiles.append(
            _stat_tile(
                f"Expected on {day}",
                _pct(expected),
                f'<span class="delta">{schedule["elapsed_days"]} of '
                f"{schedule['total_days']} working days, {_day(schedule['start'])} "
                f"→ {_day(schedule['end'])}</span>",
            )
        )
    everything = snapshot["assets"] + snapshot["shots"]
    rtk = sum(i["open_rtk"] for i in everything)
    files = sum(1 for i in everything if i["open_rtk"])
    on_files = f"on {files} file{'' if files == 1 else 's'}"
    tiles.append(
        _stat_tile(
            "Open RTKs",
            str(rtk),
            f'<span class="delta">{on_files}</span>' if rtk else "",
        )
    )
    cards = "".join(
        _overview_card(title, by, noun, items, meta[f"{kind}_departments"], expected)
        for kind, title, by, noun, items in sections
    )
    if cards:
        cards = f'<div class="cards">{cards}</div>'
    timeline = _render_timeline(meta, sections) if schedule else ""
    return _section(
        "overview",
        f'Progress<span class="sub">whole project on {day}, filters aside</span>',
        f'<div class="kpis">{"".join(tiles)}</div>{timeline}{cards}',
    )


def _short_day(iso: str, year: bool = False) -> str:
    """ "2026-10-20..." -> "20/10", "20/10/26" with the year."""
    return f"{datetime.fromisoformat(iso):{'%d/%m/%y' if year else '%d/%m'}}"


def _render_timeline(meta: dict, sections) -> str:
    """The schedule as one band per section, on a scale of planned progress
    (0 % at its start, 100 % at its end, in working days): today's
    expected progress a line across the bands, each section's Done the
    band's fill -- the stretch between the two light green when ahead,
    red when behind."""
    s = meta["schedule"]
    exp = s["expected"]
    line = f'<i class="exp" style="left:{exp * 100:.2f}%"></i>'
    week = ", ".join(_WEEKDAYS[d - 1] for d in s["worked_days"])
    off = len(s["days_off"])
    days_off = f", {off} day{'' if off == 1 else 's'} off" if off else ""
    sub = (
        f"{_day(s['start'])} → {_day(s['end'])}, {s['total_days']} working days "
        f"({week}{days_off})"
    )
    # The label is centred on its line, kept inside near either end.
    side = " l" if exp < 0.15 else " r" if exp > 0.85 else ""
    today = _short_day(meta.get("scan_started_at") or now())
    rows = [
        f'<span></span><span class="tl-mark"><b class="today{side}" '
        f'style="left:{exp * 100:.2f}%">Expected today ({today}): {_pct(exp)}</b>'
        "</span><span></span>"
    ]
    for kind, title, _, _, _ in sections:
        at = s["at"].get(kind)
        if not at:
            continue
        done = meta["progress"][kind]
        pts, days = round((done - exp) * 100), at["days"]
        # Coloured by the pace's band, as the Done tile's pill.
        band = _pace_band(done, exp)
        cls = band[0] if band else "ahead" if done > exp else ""
        if pts or days:
            word = "ahead" if done > exp else "behind"
            rel = (
                f"{'▲' if word == 'ahead' else '▼'} {abs(pts)} "
                f"pt{'' if abs(pts) == 1 else 's'}, {abs(days)} "
                f"working day{'' if abs(days) == 1 else 's'} {word}"
            )
        else:
            rel = "on schedule"
        low, high = min(done, exp), max(done, exp)
        gap = (
            f'<i class="gap {cls}" style="left:{low * 100:.2f}%;'
            f'width:{(high - low) * 100:.2f}%"></i>'
            if high > low
            else ""
        )
        tip = (
            f"{title}: {_pct(done)} done, {_pct(exp)} expected today -- an even "
            f"pace gets to {_pct(done)} on {_day(at['date'])}"
        )
        # Validated, over Done in the role's violet: never past it.
        valid = (meta.get("validation") or {}).get(kind) if meta.get("validation_role") else None
        over = vtext = ""
        if valid is not None:
            valid = min(valid, done)
            tip += f", {_pct(valid)} validated"
            over = f'<i class="v" style="width:{valid * 100:.2f}%"></i>'
            vtext = f'<small class="valid">{_pct(valid)} validated</small>'
        tip = _e(tip)
        rows.append(
            f'<span class="bl" title="{tip}">{_e(title)}</span><span class="bt" '
            f'title="{tip}"><i class="f" style="width:{low * 100:.2f}%"></i>{gap}{over}'
            f'{line}</span><span class="bv" title="{tip}">{_pct(done)}'
            f'<small class="{cls}">{rel}</small>{vtext}</span>'
        )
    years = s["start"][:4] != s["end"][:4]
    rows.append(
        f'<span></span><span class="tl-ends"><span>{_short_day(s["start"], years)}'
        f" · 0 %</span><span>{_short_day(s['end'], years)} · 100 %</span></span>"
        "<span></span>"
    )
    return (
        f'<div class="card tl"><h3>Schedule<span class="muted">{_e(sub)}</span></h3>'
        f'<div class="bars">{"".join(rows)}</div></div>'
    )


def _stat_tile(label: str, value: str, line: str = "", cls: str = "") -> str:
    """One figure of the overview: its label, its value, then a line (HTML).
    cls: an extra class ("valid": the role's violet)."""
    return (
        f'<div class="kpi{" " + cls if cls else ""}"><span class="kpi-label">{_e(label)}</span>'
        f'<span class="kpi-value">{_e(value)}</span>{line}</div>'
    )


# A Done's pace (done / expected) -> its band, a spreadsheet's colouring of
# its "efficiency": (lowest pace, css key, label), highest first.
_PACE_BANDS = (
    (1.05, "ahead", "ahead"),
    (1.0, "ontrack", "on track"),
    (0.9, "slip", "slightly behind"),
    (0.0, "behind", "behind"),
)
_PACE_TIP = (
    "Done / expected: 105 % and more ahead, 100 to 105 % on track, "
    "90 to 100 % slightly behind, under 90 % behind"
)


def _pace_band(done: float, expected: float) -> tuple[str, str] | None:
    """(css key, label) of done's pace against expected, None before the
    schedule's first working day (nothing expected yet)."""
    if expected <= 0:
        return None
    pace = done / expected
    return next((k, label) for floor, k, label in _PACE_BANDS if pace >= floor)


def _schedule_delta(progress: float, expected: float | None) -> str:
    """A Done tile's lines against the expected progress: points ahead or
    behind, then the pace (done / expected, a spreadsheet's "efficiency")
    as a pill in its band's colour. Nothing without a schedule."""
    if expected is None:
        return ""
    gap = round((progress - expected) * 100)
    pts = f"{abs(gap)} pt{'' if abs(gap) == 1 else 's'}"
    if gap > 0:
        text = f"▲ {pts} ahead of schedule"
    elif gap < 0:
        text = f"▼ {pts} behind schedule"
    else:
        text = "on schedule"
    line = f'<span class="delta">{text}</span>'
    band = _pace_band(progress, expected)
    if band:
        line += (
            f'<span class="pace p-{band[0]}" title="{_PACE_TIP}">Pace '
            f"{round(progress / expected * 100)} %, {band[1]}</span>"
        )
    return line


def _overview_card(
    title: str, by: str, noun: str, items: list, columns: list, expected
) -> str:
    """One section's charts: its department tasks (item x required
    department) by state, its Done by group and by department. Nothing when
    none of its items requires a department."""
    tasks = [
        "rtk" if d in i["rtk_departments"] else st
        for i in items
        for d, st in i["departments"].items()
    ]
    if not tasks:
        return ""
    total = len(tasks)
    counts = {s: tasks.count(s) for s in _TASK_STATES}
    # flex-grow, not a width: the 2px gaps come out of the bar, not on top.
    segments = "".join(
        f'<i class="s-{s}" style="flex:{counts[s]} 1 0" title="{_e(_TASK_TIPS[s])}: '
        f'{counts[s]} ({_pct(counts[s] / total)})"></i>'
        for s in _TASK_STATES
        if counts[s]
    )
    legend = "".join(
        f'<span title="{_e(_TASK_TIPS[s])}"><i class="sw s-{s}"></i>'
        f"{_e(_TASK_LABELS[s])} <b>{counts[s]}</b> "
        f'<span class="muted">{_pct(counts[s] / total)}</span></span>'
        for s in _TASK_STATES
    )
    label = ", ".join(f"{_TASK_LABELS[s]} {counts[s]}" for s in _TASK_STATES)
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(item["group"], []).append(item)
    by_group = [
        (g, average_progress(m), f"{len(m)} {noun}{'' if len(m) == 1 else 's'}")
        for g, m in groups.items()
    ]
    by_department = [
        (c.capitalize(), department_progress(items, c), "") for c in columns
    ]
    # The hairline on the bars, keyed in their panels' heading.
    key = (
        f'<span class="exp-key"><i></i>expected {_pct(expected)}</span>'
        if expected is not None
        else ""
    )
    grid = _heatmap(by.removeprefix("By ").capitalize(), groups, columns, noun)
    return (
        f'<div class="card"><h3>{_e(title)}<span class="muted">{len(items)} '
        f'{noun}{"" if len(items) == 1 else "s"}</span></h3><div class="panels">'
        f'<div class="panel"><h4>State of the {total} department '
        f"task{'' if total == 1 else 's'}</h4>"
        f'<div class="stack" role="img" aria-label="{_e(label)}">{segments}</div>'
        f'<div class="slegend">{legend}</div></div><div class="prow">'
        f'<div class="panel"><h4>{_e(by)}{key}</h4>{_bar_list(by_group, expected)}'
        f'</div><div class="panel"><h4>By department{key}</h4>'
        f"{_bar_list(by_department, expected)}</div>{grid}</div></div></div>"
    )


def _heatmap(axis: str, groups: dict, columns: list, noun: str) -> str:
    """Group x department grid of Done -- each cell shaded by its value, one
    green from light to dark, capped so its text stays readable; "–" where
    none of the group's items requires the department. Nothing when no item
    requires any."""
    columns = [
        c for c in columns if any(c in i["scores"] for m in groups.values() for i in m)
    ]
    rows = []
    for group, members in groups.items():
        cells = []
        for c in columns:
            values = [i["scores"][c] for i in members if c in i["scores"]]
            if not values:
                cells.append('<td class="na">–</td>')
                continue
            pct = round(sum(values) / len(values) * 100)
            n = len(values)
            tip = _e(
                f"{group}, {c.capitalize()}: {pct} % done "
                f"({n} {noun}{'' if n == 1 else 's'})"
            )
            shade = f"color-mix(in srgb,var(--done) {6 + pct * 0.44:.0f}%,var(--card))"
            cells.append(f'<td style="background:{shade}" title="{tip}">{pct} %</td>')
        if any(cell != '<td class="na">–</td>' for cell in cells):
            rows.append(f"<tr><th>{_e(group)}</th>{''.join(cells)}</tr>")
    if not rows:
        return ""
    head = "".join(f"<th>{_e(c.capitalize())}</th>" for c in columns)
    return (
        f'<div class="panel hm-p"><h4>{_e(axis)} × department</h4><div class="hm-wrap">'
        f'<table class="hm"><thead><tr><th></th>{head}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        '<p class="hm-key">0 %<i></i>100 %</p></div>'
    )


def _bar_list(rows: list, expected: float | None) -> str:
    """One bar per (label, progress, note) row -- the Done of a group or a
    department, rows without any required department left out -- the
    expected progress as a hairline across each."""
    mark = (
        f'<i class="exp" style="left:{expected * 100:.2f}%"></i>'
        if expected is not None
        else ""
    )
    cells = []
    for label, progress, note in rows:
        if progress is None:
            continue
        pct = round(progress * 100)
        tip = _e(f"{label}: {pct} % done" + (f" ({note})" if note else ""))
        small = f"<small>{_e(note)}</small>" if note else ""
        cells.append(
            f'<span class="bl" title="{tip}">{_e(label)}{small}</span>'
            f'<span class="bt" title="{tip}"><i class="f" style="width:{pct}%"></i>'
            f'{mark}</span><span class="bv" title="{tip}">{pct} %</span>'
        )
    if not cells:
        return '<p class="empty">No department required.</p>'
    return f'<div class="bars">{"".join(cells)}</div>'


def _render_filters(snapshot: dict) -> str:
    """Filter bar: name, group, department + state, RTK / notes toggles.
    Applied client-side to table rows and note cards alike (_JS)."""

    def options(values):
        return "".join(f'<option value="{_e(v)}">{_e(v)}</option>' for v in values)

    groups = "".join(
        f'<optgroup label="{label}">{options(dict.fromkeys(i["group"] for i in items))}</optgroup>'
        for label, items in (
            ("Assets", snapshot["assets"]),
            ("Shots", snapshot["shots"]),
        )
        if items
    )
    meta = snapshot["meta"]
    departments = dict.fromkeys(meta["asset_departments"] + meta["shot_departments"])
    states = "".join(
        f'<option value="{k}">{_e(label)}</option>' for k, (label, _) in STATES.items()
    )
    open_notes = sum(not n["closed"] for n in snapshot["notes"])
    # Three named groups -- where to go, what to keep, what to show -- the
    # toggles as chips that light up once on, Clear only while filtering.
    return (
        '<div class="navrow">'
        '<div class="grp links">'
        # On a phone: the header (title, details, review box) behind it.
        '<button type="button" id="nav-menu" class="chip navmenu" aria-expanded="false" '
        'aria-label="Project, review">☰</button><span class="gl">Go to</span>'
        f'<a href="#assets">Assets <span id="c-assets">{len(snapshot["assets"])}</span></a>'
        f'<a href="#shots">Shots <span id="c-shots">{len(snapshot["shots"])}</span></a>'
        # On a phone: the filters and Show folded behind it.
        '<button type="button" id="nav-more" class="chip navmore" aria-expanded="false">'
        "Filters ▾</button></div>"
        '<div class="grp filters"><span class="gl">Filter</span>'
        '<input id="f-name" type="search" placeholder="Name…" aria-label="Filter by name">'
        f'<select id="f-group" aria-label="Group"><option value="">All groups</option>{groups}</select>'
        '<select id="f-dep" aria-label="Department"><option value="">All departments</option>'
        f"{options(departments)}</select>"
        f'<select id="f-state" aria-label="State"><option value="">All states</option>{states}</select>'
        '<label class="chip"><input id="f-rtk" type="checkbox">Open RTK</label>'
        '<label class="chip"><input id="f-notes" type="checkbox">Open notes</label>'
        '<label class="chip" title="In the farm, or rendered and not checked yet">'
        '<input id="f-farm" type="checkbox">Farm</label>'
        '<button id="f-reset" type="button" title="Back to everything">✕ Clear</button></div>'
        '<div class="grp show"><span class="gl">Show</span>'
        '<button type="button" id="all-notes" class="chip" '
        'title="Unfold every note under its row, or fold them all">All notes '
        f'<span id="c-notes">{open_notes}</span></button>'
        '<label class="chip" title="Done todos/RTKs, kept in the snapshot but hidden">'
        '<input id="f-closed" type="checkbox">Closed notes</label>'
        f"{_columns_menu(departments, bool(snapshot['meta'].get('validation_role')))}"
        "</div>"
        '<div class="grp"><button type="button" id="view-one" class="chip" '
        'aria-pressed="false" title="One file at a time, as a page of its own -- '
        'a row\'s name opens it too">One file</button>'
        '<button type="button" id="rv-mode" class="chip rv-chip" '
        'aria-pressed="false" title="Validate departments and write retakes on '
        'this page, then download the review to send back">✎ Review</button></div>'
        "</div>"
    )


def _review_bar() -> str:
    """The in-page review's bar, in the header's review box next to the
    .xlsx (_JS): the switch, then while on who and as what, the changes so
    far, the file to send back."""
    return (
        '<div id="rv" class="rvmain"><div class="rv">'
        '<button type="button" id="rv-start" class="btn small" aria-pressed="false">'
        "✎ Review on this page</button>"
        '<span class="rvview"><button type="button" id="rv-v-table" class="chip" '
        'aria-pressed="true">Table</button><button type="button" id="rv-v-one" '
        'class="chip" aria-pressed="false" title="One file at a time, ← → to the '
        'next">One file</button></span>'
        '<span class="rvf rv">'
        '<label>Author <input id="rv-author" type="text" placeholder="your name" size="12"></label>'
        '<label>Role <select id="rv-role"><option value="">pick one</option></select></label>'
        '<label>Date <input id="rv-date" type="date"></label></span></div>'
        '<p class="rvhint">Validate (✓) or send back (✗) each department right '
        "on the page, a table or one file at a time; then download the review "
        "(.json) and send it.</p>"
        '<div class="rv rvf">'
        '<button type="button" id="rv-save" class="btn small">Download review (.json)</button>'
        '<label class="chip" title="Load a review downloaded earlier, to go on with it">'
        '<input id="rv-load" type="file" accept=".json,application/json">Load a review…</label>'
        '<button type="button" id="rv-clear" class="chip">Clear</button>'
        '<span id="rv-count" class="rv-count" title="Files with a change, departments '
        'validated, retakes written (one per line), validations withdrawn"></span>'
        '<span id="rv-saved" class="rv-saved"></span>'
        "</div></div>"
    )


def _columns_menu(departments, validated: bool = False) -> str:
    """ "Columns" drop-down: a checkbox per column that can be hidden (_JS
    hides every cell whose data-col is its data-key; the choice is kept
    per browser)."""
    columns = [
        ("thumb", "Thumbnail"),
        ("file", "Blender file"),
        ("render", "Last render"),
    ]
    columns += [(f"d:{d}", d.capitalize()) for d in departments]
    columns.append(("done", "Done"))
    if validated:
        columns.append(("valid", "Validated"))
    boxes = "".join(
        f'<label><input type="checkbox" data-key="{_e(key)}" checked> {_e(label)}</label>'
        for key, label in columns
    )
    return (
        f'<details class="cols"><summary>Columns</summary><div>{boxes}</div></details>'
    )


def _slug(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name)


def _item_attrs(item: dict) -> str:
    """data-* the filter script matches on -- same for a row and its notes
    card -- and what the in-page review writes back (data-file, -stable,
    -desc: a review row's filename, stable_version, description_exported;
    data-shots: a block's, for the [sh020] buttons)."""
    states = " ".join(f"{d}:{st}" for d, st in item["departments"].items())
    shots = " ".join(t[0] for t in item.get("shot_thumbnails") or [])
    if not shots and item["kind"] == "shot" and "-" in item["name"]:
        shots = " ".join(_owner_shots(Path(item["name"].split("_", 1)[-1])))
    validated = " ".join(d for d, v in (item.get("validated") or {}).items() if v)
    return (
        f'data-name="{_e(item["name"].lower())}" data-group="{_e(item["group"])}" '
        f'data-states="{_e(states)}" data-rtk="{item["open_rtk"]}" '
        f'data-notes="{item["open_notes"]}" '
        f'data-farm="{int(bool(item.get("farm") or item.get("to_check")))}" '
        f'data-file="{_e(_stem(item["current_version"]) or item["name"])}" '
        f'data-stable="{_e(_stem(item["stable_version"]) or "")}" '
        f'data-desc="{_e(item["description"])}" data-shots="{_e(shots)}" '
        f'data-valid="{_e(validated)}"'
    )


def _render_table(
    anchor: str, title: str, items: list, columns: list, notes: dict, roles: list = ()
) -> str:
    """One section's table, an item per row -- each followed by a row of its
    notes (notes: {item name: its threads}), folded at load (_JS)."""
    nl = "\n"
    if not items:
        return _section(anchor, title, '<p class="empty">Nothing tracked yet.</p>')
    role = top_validation_role(list(roles))
    title += f' <span class="pct">{_pct(average_progress(items))} done</span>'
    if role:
        title += (
            f' <span class="pct valid">{_pct(average_progress(items, "validation"))} '
            f"validated</span>"
        )
    with_thumbs = any(i.get("thumbnail") or i.get("shot_thumbnails") for i in items)
    head = (
        ('<th data-col="thumb"></th>' if with_thumbs else "")
        + "<th>Name</th>"
        + '<th data-col="file" title="Latest work-in-progress and stable versions '
        'of the .blend">Blender file</th>'
        + '<th data-col="render" title="Output folder of the last render: vXXX_YYY, '
        "XXX the Blender file version rendered, YYY the render increment -- then "
        'its farm state">Last render</th>'
        + "".join(
            f'<th data-col="d:{_e(c)}">{_e(c.capitalize())}</th>' for c in columns
        )
        + '<th data-col="done" title="Share of the required departments done '
        '(see the legend)">Done</th>'
        + (
            f'<th data-col="valid" title="Share of the required departments '
            f'validated by {_e(role)} (or an equivalent role) at the stable shown">'
            "Validated</th>"
            if role
            else ""
        )
    )
    span = len(columns) + 4 + with_thumbs + bool(role)
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(item["group"], []).append(item)
    rows = []
    group = None
    for item in items:
        if item["group"] != group:
            group = item["group"]
            done = _pct(average_progress(groups[group]))
            if role:
                done += (
                    f' · <span class="valid">'
                    f"{_pct(average_progress(groups[group], 'validation'))} validated</span>"
                )
            rows.append(
                f'<tr class="group" data-group="{_e(group)}">'
                f'<th colspan="{span}">{_e(group)}'
                f' <span class="pct">{done}</span></th></tr>'
            )
        cells = []
        for c in columns:
            state = item["departments"].get(c)
            if state is None:
                cells.append(
                    f'<td data-col="d:{_e(c)}"><span class="na" title="Not required">–</span></td>'
                )
            else:
                label, cls = STATES[state]
                if c in item["rtk_departments"]:
                    # Sent back: the RTK is the news, whatever the state.
                    cls += " rtk-open"
                    label += ", with an open RTK"
                cells.append(
                    f'<td data-col="d:{_e(c)}"><span class="pill {cls}" title="{_e(label)}">'
                    f"{_e(SHORT_STATES[state])}</span>{_approval_mark(item, c, roles)}</td>"
                )
        versions = " · ".join(
            label + _short_version(item["name"], v)
            for label, v in (
                (
                    "wip ",
                    item["wip_version"] if item.get("wip_after_stable", True) else None,
                ),
                ("stable ", item["stable_version"]),
            )
            if v
        )
        flags = (
            f'<span class="flag">{item["open_rtk"]} RTK</span>'
            if item["open_rtk"]
            else ""
        )
        threads = notes.get(item["name"], [])
        toggle = _notes_toggle(item["open_notes"], len(threads)) if threads else ""
        thumb = ""
        if with_thumbs:
            thumb = (
                f'<td class="th" data-col="thumb">{_thumb_img(item["thumbnail"])}'
                f"{_shot_buttons(item)}</td>"
                if item.get("thumbnail")
                else f'<td class="th" data-col="thumb"><div class="nothumb"></div>{_shot_buttons(item)}</td>'
            )
        rows.append(
            f'<tr class="item" id="i-{_e(_slug(item["name"]))}" {_item_attrs(item)} '
            f'data-threads="{len(threads)}">'
            f'{thumb}<td class="name"><b>{_e(item["name"])}</b>{flags}{toggle}'
            f"<small>{_e(item['description'])}</small></td>"
            f'<td class="ver" data-col="file">{_e(versions)}</td>'
            f'<td class="ver" data-col="render">{_render_cell(item)}</td>{"".join(cells)}'
            f'<td class="done" data-col="done">{_progress_cell(item["progress"])}</td>'
            + (
                f'<td class="done valid" data-col="valid">'
                f"{_progress_cell(item.get('validation'))}</td>"
                if role
                else ""
            )
            + "</tr>"
        )
        if threads:
            rows.append(_notes_row(_thread_lis(threads), span, with_thumbs))
    # Whole section, whatever the filters show.
    foot = (
        ('<td data-col="thumb"></td>' if with_thumbs else "")
        + '<td class="name"><b>All</b></td><td data-col="file"></td>'
        '<td data-col="render"></td>'
        + "".join(
            f'<td class="done" data-col="d:{_e(c)}">'
            f"{_progress_cell(department_progress(items, c))}</td>"
            for c in columns
        )
        + f'<td class="done" data-col="done">{_progress_cell(average_progress(items))}</td>'
        + (
            f'<td class="done valid" data-col="valid">'
            f"{_progress_cell(average_progress(items, 'validation'))}</td>"
            if role
            else ""
        )
    )
    return _section(
        anchor,
        title,
        '<p class="empty nomatch" hidden>Nothing matches the filters.</p>'
        '<div class="scroll"><table>'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>\n{nl.join(rows)}\n</tbody>"
        f'<tfoot title="Whole section, filters aside"><tr>{foot}</tr></tfoot>'
        "</table></div>",
    )


def _approval_mark(item: dict, department: str, roles: list) -> str:
    """After a department's pill: "✓ prod", its highest validation at the
    stable shown (each role in the tooltip, covered ones too), else the
    last one given to an earlier stable, greyed: to review again."""
    approvals = item["approvals"].get(department) or {}
    levels = {r["name"]: r["level"] for r in roles}
    known = sorted((levels[r], r) for r in approvals if r in levels)
    if known:
        lines = []
        for role in roles:
            cover = covering_role(approvals, role["name"], roles)
            info = approvals.get(cover) or {}
            if cover == role["name"]:
                lines.append(
                    f"{role['name']}: validated by {info.get('by', '?')} ({_day(info.get('at') or '')})"
                )
            elif cover:
                lines.append(f"{role['name']}: covered by {cover}")
            else:
                lines.append(f"{role['name']}: not validated")
        return f'<span class="ok" title="{_e(chr(10).join(lines))}">✓ {_e(known[-1][1])}</span>'
    previous = item["approvals_previous"].get(department) or {}
    old = sorted((levels[r], r) for r in previous if r in levels)
    if old:
        role = old[-1][1]
        seen = _short_version(item["name"], Path(previous[role].get("file") or "").name)
        return (
            f'<span class="ok prev" title="Validated by {_e(role)} on {_e(seen)}: a '
            f'newer stable since, to review again">{_e(role)} {_e(seen)}</span>'
        )
    return ""


# A thumbnail's box in the table: a fixed width, its height following the
# image up to a maximum -- a fixed 16:9 box letterboxed a panoramic render
# (600x54) into a thin line between two bands of the page's background.
# Too tall a render gets room on its sides instead (object-fit: contain).
# On hover: its own size, at most _THUMB_HOVER_MAX wide.
_THUMB_WIDTH, _THUMB_MAX_HEIGHT = 112, 63
_THUMB_HOVER_MAX = 640


def _thumb_img(b64: str) -> str:
    """A table thumbnail <img>: _THUMB_WIDTH wide, as tall as its aspect
    ratio needs (up to _THUMB_MAX_HEIGHT), with its hover zoom (--z) to
    its own size."""
    try:
        size = jpeg_size_of(base64.b64decode(b64[:87384]))  # its first 64 KB
    except ValueError:
        size = None
    style = ""
    if size and size[0] > 0 and size[1] > 0:
        w, h = size
        height = max(1, min(_THUMB_MAX_HEIGHT, round(_THUMB_WIDTH * h / w)))
        drawn = min(_THUMB_WIDTH, height * w / h)  # the picture, sides aside
        zoom = max(1.0, min(w, _THUMB_HOVER_MAX) / drawn)
        style = f' style="height:{height}px;--z:{zoom:.2f}"'
    return f'<img class="thumb" alt=""{style} src="data:image/jpeg;base64,{b64}">'


def _shot_buttons(item: dict) -> str:
    """Under a block's thumbnail: a small button per shot, its number
    (010, 020...) in the block's order, showing that shot's thumbnail on
    hover -- to find one's way in the edit, without a strip of eight
    images per row. Greyed for a shot not rendered yet. "" for anything
    else."""
    shots = item.get("shot_thumbnails") or []
    if not shots:
        return ""
    buttons = "".join(
        f'<span class="sb">{_e(label.lstrip("abcdefghijklmnopqrstuvwxyz_"))}'
        f'<img alt="{_e(label)}" src="data:image/jpeg;base64,{b64}"></span>'
        if b64
        else f'<span class="sb none" title="{_e(label)}: not rendered yet">'
        f"{_e(label.lstrip('abcdefghijklmnopqrstuvwxyz_'))}</span>"
        for label, b64 in shots
    )
    # data-col: the Columns menu's Thumbnail hides them with the column.
    return f'<div class="sbs" data-col="thumb">{buttons}</div>'


def _progress_cell(progress: float | None) -> str:
    """ "Done" cell: a bar and its percentage, "–" without any required
    department."""
    if progress is None:
        return '<span class="na" title="No department required">–</span>'
    width = round(progress * 100)
    return f'<span class="bar"><i style="width:{width}%"></i></span>{width} %'


def _render_cell(item: dict) -> str:
    """ "Last render" cell: one line per render (per shot when a block's
    shots differ), a status pill -- "to check", else _farm_pill() -- then
    its vXXX_YYY folder, red when older than the last stable. "not
    rendered" for a shot never rendered, nothing for such an asset."""
    renders = item.get("renders") or []
    to_check = list(item.get("to_check") or [])
    # [labels, pill, text, shot of a "not rendered" line]: labels as
    # render_to_check_label()'s.
    rows = []
    if any(r["folder"] for r in renders):
        stable = _short_version(item["name"], item["stable_version"] or "")
        block = len(renders) > 1  # a mono shot's labels carry no shot
        every = [r["shot"] for r in renders]
        for shots, r in group_renders(renders):
            label = shots_label(shots, every) if block else ""
            # A shot rendered with the whole block: said on hover.
            tip = ' title="Rendered with the whole block"' if r.get("whole") else ""
            shot = f'<span class="shot"{tip}>{_e(label)}</span> ' if label else ""
            labels = (
                {
                    r["folder"] if r.get("whole") or not block else f"{s} {r['folder']}"
                    for s in shots
                }
                if r["folder"]
                else set()
            )
            if not r["folder"]:
                text = f'{shot}<span class="norender">not rendered</span>'
                rows.append([labels, "", text, shots[0] if block else ""])
                continue
            if (
                r["file_number"] is not None
                and r["file_number"] < item["stable_number"]
            ):
                text = (
                    f'{shot}<span class="behind" title="Rendered from an older '
                    f'version than the last stable ({_e(stable)})">⚠ {_e(r["folder"])}</span>'
                )
            else:
                text = f"{shot}{_e(r['folder'])}"
            pill = _TO_CHECK_PILL if labels & set(to_check) else ""
            to_check = [label for label in to_check if label not in labels]
            rows.append([labels, pill, text, None])
    elif item["kind"] == "shot":
        rows.append([set(), "", '<span class="norender">not rendered</span>', ""])
    rows += [[{label}, _TO_CHECK_PILL, _e(label), None] for label in to_check]
    for job in item.get("farm") or []:
        label = f"{job['shot']} {job['version']}".strip()
        shot = f'<span class="shot">{_e(job["shot"])}</span> ' if job["shot"] else ""
        row = next((r for r in rows if label in r[0] and not r[1]), None)
        if row:
            row[1] = _farm_pill(job)
            continue
        # First render of that shot: it takes its "not rendered" line.
        row = next((r for r in rows if r[3] == job["shot"] and not r[1]), None)
        if row:
            row[:] = [{label}, _farm_pill(job), f"{shot}{_e(job['version'])}", None]
        else:
            rows.append([{label}, _farm_pill(job), f"{shot}{_e(job['version'])}", None])
    if not rows:
        return ""
    return (
        '<div class="rl">'
        + "".join(
            f"<span>{pill}</span><span>{text}</span>" for _, pill, text, _ in rows
        )
        + "</div>"
    )


_TO_CHECK_PILL = (
    '<span class="pill tocheck" title="Rendered, not checked by the team yet">'
    "to check</span>"
)


def _farm_pill(job: dict) -> str:
    """A job still in the farm: "queued" (grey) whatever it waits for,
    its step in blue ("rendering 45/120", "compiling"...), "failed" in red
    -- the exact step in the tooltip."""
    state = job["state"]
    text = {"waiting": "queued", "failed": "failed"}.get(state, job["text"])
    return (
        f'<span class="pill farm-{_e(state)}" title="In the farm: {_e(job["text"])}">'
        f"{_e(text)}</span>"
    )


def _short_version(name: str, filename: str) -> str:
    """ "ch_bob_v004-stable.blend" -> "v004" (the stable label says the rest)."""
    stem = filename.removesuffix(".blend")
    stem = stem[len(name) + 1 :] if stem.startswith(name + "_") else stem
    return stem.split("-", 1)[0]


def _render_entry(e: dict, reply: bool = False, closed: bool = False) -> str:
    """One entry's <li>: type pill (ticked once done), tags, author and date,
    text."""
    if e["done"] is True:
        # The type's own pill, green and ticked like "Validated" -- a
        # separate "done" tag read like one more department.
        tags = [f'<span class="type t-done" title="Done">✓ {_e(e["type"])}</span>']
    else:
        # An RTK red from a validation role, orange from the team.
        team = " team" if e["type"] == "rtk" and not e.get("role") else ""
        tags = [f'<span class="type t-{_e(e["type"])}{team}">{_e(e["type"])}</span>']
    if e.get("role"):
        tags.append(
            f'<span class="tag role" title="Written as {_e(e["role"])}">{_e(e["role"])}</span>'
        )
    if e["from_review"]:
        tags.append('<span class="tag">prod review</span>')
    for key in ("department", "shot", "frames", "version"):
        if e.get(key):
            tags.append(f'<span class="tag">{_e(e[key])}</span>')
    who = f"{_e(e['author'])} · {_e(e['date'][:10])}"
    cls = ("reply" if reply else "root") + (" closed" if closed else "")
    cls += " by-role" if e.get("role") else ""
    return (
        f'<li class="{cls}"><div class="head">'
        f'{"".join(tags)}<span class="who">{who}</span></div>'
        f"<p>{_e(e['text'])}</p></li>"
    )


def _notes_toggle(open_count: int, total: int) -> str:
    """ "2 notes" button unfolding an item's notes row (_JS) -- the count of
    its open threads, of all of them once "Show closed" is ticked."""

    def count(n: int) -> str:
        return f"{n} note{'' if n == 1 else 's'}"

    return (
        f'<button type="button" class="jump" aria-expanded="false" '
        f'data-open="{open_count}"><span class="n-open">{count(open_count)}</span>'
        f'<span class="n-all">{count(total)}</span></button>'
    )


def _thread_lis(threads: list) -> str:
    """An item's threads as list items, the most recently active first."""
    threads = sorted(threads, key=lambda t: t["last_activity"], reverse=True)
    return "\n".join(
        "\n".join(
            [_render_entry(t, closed=t["closed"])]
            + [_render_entry(r, True, t["closed"]) for r in t["replies"]]
        )
        for t in threads
    )


def _notes_row(lis: str, span: int, thumbs: bool = False) -> str:
    """The row under an item's own holding its notes, folded at load (_JS),
    lined up with the name: past a spacer as wide as the thumbnail column
    (thumbs), hidden with it from the Columns menu. Its text stays in view
    when a wide table is scrolled sideways."""
    spacer = '<i class="nspace" data-col="thumb"></i>' if thumbs else ""
    return (
        f'<tr class="notes" hidden><td colspan="{span}"><div class="nwrap">{spacer}'
        f'<div class="nbox"><ul class="threads">\n{lis}\n</ul></div></div></td></tr>'
    )


_CSS = """
:root{--page:1600px;--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e2e1dc;
--accent:#3d5afe;--done:#2e7d32;--done-bg:#e3f2e4;--wip:#8a5a00;--wip-bg:#fff1d6;
--todo:#6b6b66;--rtk:#c62828;--rtk-bg:#fde7e7;color-scheme:light dark;
--role:#7b3fbf;--role-bg:#f0e7fb;--team:#c2410c;--team-bg:#ffe9d9;
--t-rework:#7cb342;--t-wip:#c98a1a;--t-done:var(--done);--t-rtk:var(--rtk);
--track:color-mix(in srgb,var(--done) 16%,var(--card))}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;
--fg:#ecebe6;--muted:#a3a29c;--card:#20201e;--line:#34332f;--accent:#8c9eff;
--done:#81c784;--done-bg:#1d3320;--wip:#ffcc80;--wip-bg:#3a2c12;--todo:#a3a29c;
--rtk:#ef9a9a;--rtk-bg:#3a1c1c;--t-rework:#4c8c50;--t-wip:#b88e2e;
--role:#c9a3f5;--role-bg:#2d2140;--team:#ffb07a;--team-bg:#3a2414;
--track:color-mix(in srgb,var(--done) 16%,var(--card))}}
:root[data-theme="dark"]{--bg:#161615;--fg:#ecebe6;--muted:#a3a29c;--card:#20201e;
--line:#34332f;--accent:#8c9eff;--done:#81c784;--done-bg:#1d3320;--wip:#ffcc80;
--wip-bg:#3a2c12;--todo:#a3a29c;--rtk:#ef9a9a;--rtk-bg:#3a1c1c;--t-rework:#4c8c50;
--t-wip:#b88e2e;--role:#c9a3f5;--role-bg:#2d2140;--team:#ffb07a;--team-bg:#3a2414;
--track:color-mix(in srgb,var(--done) 16%,var(--card))}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header,section,.legend{max-width:var(--page);margin:0 auto;padding:0 16px}
header{padding-top:28px}
h1{margin:0 0 8px;font-size:26px}
h2{margin:32px 0 12px;font-size:19px}
h3{margin:0 0 8px;font-size:15px}
.meta{display:flex;flex-wrap:wrap;gap:6px 24px;margin:0 0 16px;color:var(--muted)}
.meta div{display:flex;gap:6px}.meta dt{font-weight:600}.meta dd{margin:0}
.review{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px 16px;display:grid;grid-template-columns:minmax(0,1fr) minmax(180px,280px);gap:14px 20px}
.review p{margin:8px 0 0;color:var(--muted)}
.rvside{border-left:1px dashed var(--line);padding-left:20px;font-size:12px}
.rvside p{margin-top:6px}
.btn.small.ghost{background:none;color:var(--accent);border:1px solid var(--accent)}
@media (max-width:700px){.review{grid-template-columns:minmax(0,1fr)}
.rvside{border-left:0;padding-left:0;border-top:1px dashed var(--line);padding-top:12px}}
.btn{display:inline-block;background:var(--accent);color:#fff;padding:8px 14px;
border-radius:7px;text-decoration:none;font-weight:600}
nav{z-index:2;display:flex;flex-direction:column;gap:8px;margin-top:20px;
padding:10px max(16px,calc((100% - var(--page))/2 + 16px));
background:var(--bg);border-bottom:1px solid var(--line)}
nav{position:sticky;top:0;transition:transform .2s ease}
/* A phone: a compact bar, the filters behind "Filters", out of the way
while scrolling down, back on the way up (_JS). */
.chip.navmore,.chip.navmenu{display:none}
/* One file: no Go to, no filters (Previous / Next keep to the files they
leave), from Show only Closed notes. */
body.one .grp.links>a,body.one .grp.links>.gl,body.one .grp.filters,body.one #all-notes,
body.one nav .cols,body.one .chip.navmore{display:none}
.chip.navmore[aria-expanded="true"]{color:#fff;background:var(--accent);border-color:var(--accent)}
@media (max-width:699px){nav{gap:6px;padding-top:8px;padding-bottom:8px}nav.away{transform:translateY(-110%)}
.chip.navmore,.chip.navmenu{display:inline-flex}
body:not(.hdr-open) header>:not(h1){display:none}body.one:not(.hdr-open) header{display:none}
header h1{display:flex;align-items:center;gap:10px}
/* ☰ at the top right, the header's and the bar's alike. */
header{padding-top:10px}header h1 .navmenu{margin-left:auto}nav{padding-right:60px}
nav .navmenu{position:absolute;right:16px;top:10px}
.chip.navmenu{width:40px;justify-content:center;font-size:14px}
body.one .grp.links{display:contents}
body.one nav .grp.show{display:flex}
body.hdr-open header{position:fixed;top:0;left:0;right:0;z-index:30;max-height:85vh;overflow:auto;
background:var(--bg);padding-bottom:16px;box-shadow:0 8px 24px rgba(0,0,0,.25)}
body.hdr-open::after{content:"";position:fixed;inset:0;z-index:29;background:rgba(0,0,0,.3)}
nav:not(.more) .grp.filters,nav:not(.more) .grp.show{display:none}
nav:has(.filters.active) .navmore{color:var(--accent);border-color:var(--accent)}
.navrow{gap:8px 16px}.filters select{max-width:46%}}
.links,.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
/* The bar: named groups side by side, a rule between them. */
.navrow{display:flex;flex-wrap:wrap;gap:8px 28px;align-items:center}
.grp{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.filters select{max-width:150px}
.gl{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;
color:var(--muted);margin-right:2px}
/* A toggle: a chip, lit once on (its checkbox hidden). */
.chip{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:999px;
border:1px solid var(--line);background:var(--card);color:var(--fg);font:inherit;
font-size:13px;cursor:pointer;white-space:nowrap;user-select:none}
.chip input{position:absolute;opacity:0;width:0;height:0;margin:0}
.chip:has(input:checked),.chip[aria-pressed="true"]{color:var(--accent);border-color:var(--accent);
background:color-mix(in srgb,var(--accent) 12%,var(--card));font-weight:600}
.chip:has(input:focus-visible){outline:2px solid var(--accent);outline-offset:2px}
.chip span{color:var(--muted);font-weight:400}
/* Counts at a fixed width: filtering changes them, the bar mustn't move. */
#c-assets,#c-shots,#c-notes{display:inline-block;min-width:3ch;text-align:right;
font-variant-numeric:tabular-nums}
/* A filter in use stands out; Clear shows only while one is. */
.filters input[type=search]:not(:placeholder-shown),
.filters select:has(option:checked:not([value=""])){border-color:var(--accent);
color:var(--accent);background:color-mix(in srgb,var(--accent) 8%,var(--card))}
.filters:not(.active) #f-reset{display:none}
.filters #f-reset{border-color:transparent;background:none}
.links a,.links button{color:var(--fg);text-decoration:none;padding:4px 10px;
border-radius:6px;border:1px solid var(--line);background:var(--card);font:inherit;
cursor:pointer}
.links a span,.links button span{color:var(--muted);margin-left:4px}
.filters input[type=search],.filters select,.filters button{font:inherit;min-width:0;
padding:4px 8px;border-radius:6px;border:1px solid var(--line);background:var(--card);
color:var(--fg)}
.filters input[type=search]{flex:0 1 140px}
.filters button{cursor:pointer;color:var(--muted)}
.cols{position:relative}
.cols summary{cursor:pointer;color:var(--muted);padding:4px 8px;border:1px solid var(--line);
border-radius:6px;background:var(--card);list-style:none}
.cols summary::-webkit-details-marker{display:none}
.cols summary::after{content:" ▾"}
.cols div{position:absolute;right:0;z-index:4;margin-top:4px;padding:8px 12px;display:grid;gap:4px;
width:max-content;
background:var(--card);border:1px solid var(--line);border-radius:8px;
box-shadow:0 4px 18px rgba(0,0,0,.18)}
.cols.hiding summary{color:var(--accent);border-color:var(--accent)}
.cols label{display:flex;gap:6px;align-items:center;white-space:nowrap;cursor:pointer}
.legend .muted{color:var(--muted);font-size:12px;margin:0 8px 0 -2px;align-self:center}
.filters.active button{color:var(--accent);border-color:var(--accent)}
[id]{scroll-margin-top:var(--nav-h,16px)}
tr:target td{background:color-mix(in srgb,var(--accent) 12%,transparent)}
.jump{display:inline-block;margin-left:8px;padding:0;border:0;background:none;
font:inherit;font-size:11px;color:var(--accent);white-space:nowrap;cursor:pointer}
.jump::after{content:" ▸"}.jump[aria-expanded="true"]::after{content:" ▾"}
.jump:hover{text-decoration:underline}
body:not(.show-closed) .jump[data-open="0"],body:not(.show-closed) .n-all,
body.show-closed .n-open{display:none}
.legend{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.scroll{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
/* A table's header, copied by _JS once the real one has scrolled under the
nav -- position:sticky can't: inside a scroll box it sticks to the box. */
.stuck{position:fixed;z-index:1;overflow:hidden;background:var(--card);
box-shadow:0 1px 0 var(--line),0 4px 10px rgba(0,0,0,.06)}
.stuck table{table-layout:fixed}
table{border-collapse:collapse;width:100%}
th,td{padding:6px 8px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
table{font-size:13px}
thead th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
/* A sequence's / prefix's band: it has to stand out from the rows. */
tr.group th{background:var(--line);font-size:14px;font-weight:700;color:var(--fg);
padding-top:9px;padding-bottom:9px}
tr.group .pct{font-size:13px}
td.name{min-width:200px}td.name small{display:block;color:var(--muted);white-space:pre-line}
td.ver{color:var(--muted);font-size:12px;white-space:nowrap}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;
white-space:nowrap;border:1px solid transparent}
.st-done{background:var(--done-bg);color:var(--done)}
.st-rework{background:var(--done-bg);color:var(--wip);border-color:var(--wip)}
.st-wip{background:var(--wip-bg);color:var(--wip)}
.st-todo{color:var(--todo);border-color:var(--line)}
.st-none{color:var(--muted);border:1px dashed var(--line)}
.na{color:var(--muted);opacity:.5}
.behind{color:var(--rtk);font-weight:600}.norender{opacity:.6}
.rl{display:grid;grid-template-columns:max-content max-content;gap:3px 6px;align-items:center}
.rl .pill{padding:0 7px;font-size:11px;font-weight:600}
.pill.tocheck{color:var(--wip);background:var(--wip-bg);border-color:var(--wip)}
.pill.farm-running{color:var(--accent);background:color-mix(in srgb,var(--accent) 14%,transparent);
border-color:var(--accent)}
.pill.farm-waiting{color:var(--muted);background:color-mix(in srgb,var(--muted) 14%,transparent)}
.pill.farm-failed{color:var(--rtk);background:var(--rtk-bg);border-color:var(--rtk)}
.pill.rtk-open{border-color:var(--rtk);box-shadow:0 0 0 1px var(--rtk) inset}
.pct{margin-left:8px;font-size:.8em;font-weight:600;color:var(--done)}
.pct .valid,.pct.valid{color:var(--role)}
.legend.muted{color:var(--muted);font-size:12px}
td.done{white-space:nowrap}
body:not(.show-closed) li.closed{display:none}
li.closed{opacity:.6}
tfoot td{border-top:2px solid var(--line);font-weight:600}
.bar{display:inline-block;width:56px;height:6px;margin-right:6px;vertical-align:middle;
border-radius:3px;background:var(--line);overflow:hidden}
.bar i{display:block;height:100%;background:var(--done)}
.valid .bar i{background:var(--role)}
td.ver .shot{font-weight:600}
/* Middle of its row: a panoramic thumbnail is shorter than a line of text. */
td.th{width:1px;padding-right:0;vertical-align:middle}
/* Any aspect ratio: shown whole inside a fixed box, never cropped. */
.thumb{display:block;width:112px;height:63px;object-fit:contain;border-radius:4px;
background:var(--bg);transition:transform .15s}
.nothumb{width:112px}
.sbs{display:flex;flex-wrap:wrap;gap:3px;width:112px;margin-top:4px}
.sb{position:relative;font-size:10px;line-height:16px;padding:0 4px;border-radius:3px;
background:var(--line);color:var(--fg);cursor:default}
.sb.none{opacity:.45}
.sb img{display:none}
.sb:hover{background:var(--role);color:#fff}
/* One shared preview, fixed: a table's scroll box would clip it. */
#sbpop{position:fixed;z-index:20;pointer-events:none;display:none;border-radius:4px;
width:auto;max-width:640px;box-shadow:0 4px 18px rgba(0,0,0,.35);background:var(--bg)}
img.thumb:hover{transform:scale(var(--z,var(--thumb-zoom,2.4)));transform-origin:left top;position:relative;
z-index:3;box-shadow:0 4px 18px rgba(0,0,0,.35);
/* Scaled with the image: 4 px once zoomed, as the shot buttons' preview. */
border-radius:calc(4px / var(--z,var(--thumb-zoom,2.4)))}
.flag{margin-left:8px;font-size:11px;font-weight:600;color:var(--rtk);
background:var(--rtk-bg);padding:1px 6px;border-radius:999px}
/* An item's notes, in the row under its own. */
tr.notes>td{padding:0 8px 8px;
background:color-mix(in srgb,var(--accent) 4%,var(--card))}
.nwrap{display:flex}
/* The thumbnail column: its cell's left padding + the thumbnail -- not on a
narrow screen, where it would push the notes out of it. */
.nspace{flex:0 0 120px}@media (max-width:640px){.nspace{display:none}}
/* The table's width (author and date at its right), never past the screen:
it stays in view when a wide table is scrolled sideways. */
.nbox{position:sticky;left:8px;flex:1 1 auto;min-width:0;
max-width:calc(100vw - 64px)}
.threads{list-style:none;margin:0;padding:0}
.threads li{padding:8px 0;border-top:1px solid var(--line)}
.threads li:first-child{border-top:0}
.threads li.reply{margin-left:24px}
/* A note's text keeps a reading width. */
.threads li p{margin:4px 0 0;max-width:60rem;white-space:pre-wrap;overflow-wrap:anywhere}
.head{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.who{margin-left:auto;color:var(--muted);font-size:12px}
.type,.tag{font-size:10px;line-height:15px;padding:0 6px;border-radius:999px;
border:1px solid var(--line)}
.type{font-weight:600;text-transform:uppercase}
.t-rtk{color:var(--rtk);background:var(--rtk-bg);border-color:transparent}
.t-rtk.team{color:var(--team);background:var(--team-bg)}
.tag.role{color:var(--role);background:var(--role-bg);border-color:transparent;font-weight:600}
.threads li.by-role{border-left:3px solid var(--role);padding-left:8px}
.ok{display:inline-block;margin-left:4px;font-size:11px;font-weight:600;color:var(--role)}
.ok.prev{color:var(--muted);font-weight:400}
.t-todo{color:var(--wip);background:var(--wip-bg);border-color:transparent}
.t-done{color:var(--done);background:var(--done-bg);border-color:transparent}
.empty{color:var(--muted)}
section:last-of-type{padding-bottom:40px}
details.sec>summary{list-style:none;cursor:pointer}
details.sec>summary::-webkit-details-marker{display:none}
/* A chevron drawn as two borders of a square: it turns on its own centre. */
details.sec>summary h2::before{content:"";display:inline-block;width:.4em;height:.4em;
margin:0 .6em 0 .15em;border:solid var(--muted);border-width:0 2px 2px 0;
vertical-align:.18em;transform:rotate(45deg);transition:transform .15s}
details.sec:not([open])>summary h2::before{transform:rotate(-45deg)}
details.sec:not([open])>summary h2{margin-bottom:0}
/* Overview: department tasks in the page's colours -- --done and --rtk as
everywhere else; WIP an amber and reworked a second green, stepped so that
colour-blind readers still tell neighbours apart; not started grey. */
#overview h2 .sub,.card h3 .muted{margin-left:8px;font-size:12px;font-weight:400;
color:var(--muted)}
.kpis{display:flex;flex-wrap:wrap;gap:12px}
.kpi{flex:1 1 200px;display:flex;flex-direction:column;gap:2px;background:var(--card);
border:1px solid var(--line);border-radius:10px;padding:12px 16px}
.kpi-label{font-size:12px;color:var(--muted)}
.kpi-value{font-size:28px;font-weight:600;line-height:1.2}
.kpi.valid{background:var(--role-bg);border-color:var(--role)}
.kpi.valid .kpi-value,.kpi.valid .kpi-label{color:var(--role)}
.delta{font-size:12px;color:var(--muted)}
/* Pace bands: a solid green, a light one, amber, red -- each with its label. */
.pace{align-self:flex-start;margin-top:6px;padding:1px 8px;border-radius:999px;
font-size:12px;font-weight:600}
.p-ahead{background:var(--done);color:var(--card)}
.p-ontrack{background:var(--done-bg);color:var(--done)}
.p-slip{background:var(--wip-bg);color:var(--wip)}
.p-behind{background:var(--rtk-bg);color:var(--rtk)}
.cards{display:grid;grid-template-columns:minmax(0,1fr);gap:12px;margin-top:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px 16px}
.card h4{margin:14px 0 8px;font-size:12px;font-weight:600;color:var(--muted);
text-transform:uppercase;letter-spacing:.04em}
.stack{display:flex;gap:2px;height:16px}
.stack i{min-width:2px}.stack i:last-child{border-radius:0 4px 4px 0}
.s-done{background:var(--t-done)}.s-rework{background:var(--t-rework)}
.s-rtk{background:var(--t-rtk)}.s-wip{background:var(--t-wip)}.s-todo{background:var(--line)}
.slegend{display:flex;flex-wrap:wrap;gap:4px 16px;margin-top:8px;font-size:12px}
.slegend .muted{color:var(--muted)}
.sw{display:inline-block;width:10px;height:10px;margin-right:6px;border-radius:2px;
vertical-align:-1px}
/* One panel per chart, on the page's background inside the card. */
.panels{display:grid;grid-template-columns:minmax(0,1fr);gap:12px;margin-top:12px}
.panel{min-width:0;padding:12px 16px 14px;border-radius:8px;background:var(--bg)}
.card .panel h4{display:flex;justify-content:space-between;gap:12px;margin:0 0 10px}
/* Bars by group, by department and the grid side by side; the grid goes
under them when it doesn't fit (many departments, narrow screen), and
scrolls sideways past the screen's width. */
.prow{display:flex;flex-wrap:wrap;gap:12px}
.prow>.panel{flex:1 1 260px}
.prow>.hm-p{flex:1 0 auto;max-width:100%}
.bars{display:grid;grid-template-columns:max-content minmax(60px,1fr) max-content;
gap:6px 10px;align-items:center;font-size:12px}
.bl small{margin-left:6px;color:var(--muted)}
.bt{position:relative;height:10px;background:var(--track);border-radius:0 4px 4px 0}
.bt .f{display:block;height:100%;background:var(--done);border-radius:0 4px 4px 0}
.bt .exp{position:absolute;top:-3px;bottom:-3px;width:2px;margin-left:-1px;
background:var(--fg);opacity:.55;border-radius:1px}
.bv{text-align:right;font-variant-numeric:tabular-nums}
.exp-key{font-size:11px;font-weight:400;color:var(--muted);text-transform:none;
letter-spacing:0;white-space:nowrap}
.exp-key i{display:inline-block;width:2px;height:12px;margin-right:6px;
background:var(--fg);opacity:.55;vertical-align:-2px}
.hm-wrap{overflow-x:auto}
.hm{width:auto;border-collapse:separate;border-spacing:2px;font-size:12px}
.hm th,.hm td{padding:4px 10px;border:0;text-align:center;white-space:nowrap}
.hm tbody th{text-align:left;font-weight:600}
.hm td{min-width:4.5em;border-radius:6px;font-variant-numeric:tabular-nums}
.hm td.na{color:var(--muted);opacity:.5}
.hm-key{margin:6px 0 0;font-size:11px;color:var(--muted)}
.hm-key i{display:inline-block;width:80px;height:8px;margin:0 6px;border-radius:4px;
vertical-align:middle;background:linear-gradient(to right,
color-mix(in srgb,var(--done) 6%,var(--card)),color-mix(in srgb,var(--done) 50%,var(--card)))}
.card.tl{margin-top:12px}
.tl .bars{row-gap:10px}
.bv small{display:block;color:var(--muted)}
.bv small.ahead,.bv small.ontrack{color:var(--done)}.bv small.slip{color:var(--wip)}
.bv small.behind{color:var(--rtk)}
.tl .bt{height:12px}.tl .bt .f{border-radius:0}
.tl .bt .gap{position:absolute;top:0;bottom:0}
.tl .bt .v{position:absolute;left:0;top:0;bottom:0;background:var(--role)}
.bv small.valid{color:var(--role)}
.gap.ahead,.gap.ontrack{background:color-mix(in srgb,var(--done) 40%,var(--card));
border-radius:0 4px 4px 0}
.gap.slip{background:color-mix(in srgb,var(--wip) 40%,var(--card))}
.gap.behind{background:color-mix(in srgb,var(--rtk) 40%,var(--card))}
.tl .bt .exp{top:-5px;bottom:-5px}
.tl-mark{position:relative;height:16px}
.today{position:absolute;bottom:0;font-size:11px;font-weight:600;white-space:nowrap;
transform:translateX(-50%)}.today.l{transform:none}.today.r{transform:translateX(-100%)}
.tl-ends{display:flex;justify-content:space-between;font-size:11px;color:var(--muted)}
/* Narrow: the timeline's bands stack (label, band, value). */
@media (max-width:640px){.tl .bars{grid-template-columns:1fr;row-gap:4px}
.tl .bars>span:empty{display:none}.tl .bv{text-align:left;margin-bottom:8px}}
/* In-page review: its bar in the review box, a ✓ and a ✗ by each
department's pill. */
.rvmain{display:grid;gap:10px;align-content:start}.rvmain p.rvhint{margin:0}
.rv{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center}
body:not(.reviewing) .rvf,body.reviewing .rvhint{display:none}
#rv-start{background:var(--role)}#rv-start[aria-pressed="true"]{background:var(--fg);color:var(--bg)}
.rv label{display:flex;gap:6px;align-items:center;color:var(--muted);font-size:13px}
.rv input[type=text],.rv input[type=date],.rv select{font:inherit;font-size:13px;padding:3px 8px;
border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
#rv-role{border-color:var(--role)}
.btn.small{padding:5px 12px;font-size:13px;border:0;cursor:pointer;font-family:inherit}
.rv-count{font-size:13px;color:var(--role);font-weight:600}
.rvview{display:inline-flex}.rvview .chip:first-child{border-radius:999px 0 0 999px}
.rvview .chip:last-child{border-radius:0 999px 999px 0;margin-left:-1px}
.rvview .chip[aria-pressed="true"]{color:var(--bg);background:var(--fg);border-color:var(--fg)}
.rv-saved{font-size:12px;color:var(--muted)}
.rv-chip[aria-pressed="true"]{color:#fff;background:var(--role);border-color:var(--role)}
body:not(.reviewing) .rvc,body:not(.reviewing) .rvg,body:not(.reviewing) .rvt,
body:not(.reviewing) .rvtags{display:none}
.rvg{display:flex;flex-wrap:wrap;gap:4px;margin-top:5px;align-items:center}
td.name>b{cursor:pointer;text-decoration:underline dotted var(--muted);text-underline-offset:3px}
td.name>b:hover{color:var(--accent);text-decoration-color:var(--accent)}
body.reviewing td.name>b:hover{color:var(--role);text-decoration-color:var(--role)}
/* The card outside a review: a file's page, read only. */
body:not(.reviewing) .orow,body:not(.reviewing) .ofl{display:none}
.rvc{display:inline-flex;gap:3px;margin-left:6px;vertical-align:middle}
body.reviewing td[data-col^="d:"]{white-space:nowrap}body.reviewing td.name{min-width:290px}
.rvb{font:inherit;font-size:11px;line-height:16px;padding:1px 8px;border-radius:999px;
border:1px solid var(--line);background:var(--card);color:var(--muted);cursor:pointer}
.rvb:hover:not(:disabled){border-color:var(--fg);color:var(--fg)}
.rvb:disabled{opacity:.3;cursor:default}
.rvc .rvb{padding:1px 6px}
/* A validation is the role's: violet, as its marks. */
.rvb.yes[aria-pressed="true"],.rvb.all[aria-pressed="true"]{color:#fff;background:var(--role);
border-color:var(--role)}
.rvb.yes.via{color:var(--role);background:var(--role-bg);border-color:var(--role)}
.rvb.rt[aria-pressed="true"],.rvb.gen[aria-pressed="true"]{color:#fff;background:var(--rtk);
border-color:var(--rtk)}
.rvb.desc[aria-pressed="true"]{color:#fff;background:var(--accent);border-color:var(--accent)}
/* As wide as its cell, never wider: the table keeps its width. */
.rvt,.rvo{display:block;box-sizing:border-box;width:0;min-width:100%;margin-top:4px;font:inherit;
font-size:12px;padding:4px 6px;border:1px solid var(--rtk);border-radius:6px;
background:var(--card);color:var(--fg);resize:none;overflow:hidden;white-space:pre-wrap}
.rvt.rvdesc{border-color:var(--accent)}
.rvt::placeholder,.rvo::placeholder{color:var(--muted);opacity:.55}
/* One file at a time (_JS openOne()): a card under the nav, the tables
hidden, built from the row itself -- nothing more in the page. */
body.one section,body.one .legend{display:none}
.one{max-width:var(--page);margin:16px auto;padding:0 16px}.one[hidden]{display:none}
.ocard{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px}
.ocard.changed{box-shadow:inset 3px 0 var(--role)}
.otop{display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding-bottom:12px;
margin-bottom:14px;border-bottom:1px solid var(--line)}
.otop .chip:disabled{opacity:.35;cursor:default}
.oname{font-size:18px;font-weight:700;overflow-wrap:anywhere}.opos{font-size:12px;color:var(--muted)}
.obtns{display:flex;gap:6px;flex-wrap:wrap}.owho{flex:0 1 auto;min-width:0}
.ojump{margin-left:auto;max-width:260px;font:inherit;font-size:13px;padding:3px 8px;border-radius:6px;
border:1px solid var(--line);background:var(--card);color:var(--fg)}
@media (max-width:700px){.owho{flex-basis:100%;order:-1}.ojump{max-width:100%;flex:1 1 100%}}
.opair{display:contents}.opair[hidden]{display:none}.oshb{grid-column:1 / -1;align-items:center}
.oshb>span{font-size:12px;color:var(--muted);margin-right:2px}.oshb .rvtag[hidden]{display:none}
.oinfo .bar{width:90px}
.ostats>*{margin-top:0}.ostats .card{box-shadow:none}
.okeys{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:6px;font-size:12px;color:var(--muted)}
.okeys kbd{font:inherit;font-size:11px;font-weight:600;padding:0 5px;border:1px solid var(--line);
border-bottom-width:2px;border-radius:4px;background:var(--card);color:var(--fg)}
@media (max-width:700px){.okeys{display:none}}
.ortk{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px;margin-top:6px;font-size:13px}
.opill{font:inherit;font-size:11px;font-weight:600;line-height:16px;padding:0 7px;border-radius:999px;
border:0;background:var(--rtk);color:#fff;cursor:pointer;white-space:nowrap}
.opill.team{background:var(--team)}.otx{flex:1 1 200px;min-width:0}.ometa{display:none;flex-basis:100%;color:var(--muted);font-size:11px}
.ortk.open .ometa{display:block}
.obody{display:grid;grid-template-columns:minmax(0,560px) minmax(0,1fr);gap:22px}
@media (max-width:900px){.obody{grid-template-columns:minmax(0,1fr)}}
.obig{display:block;width:100%;border-radius:6px;background:var(--line)}
.oshots{display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:6px;margin-top:8px}
.oshots button{font:inherit;font-size:11px;padding:0 0 2px;border:2px solid transparent;
border-radius:5px;background:none;color:var(--muted);cursor:pointer;text-align:center}
.oshots button[aria-pressed="true"]{border-color:var(--role);color:var(--fg)}
.oshots img{display:block;width:100%;border-radius:3px;margin-bottom:2px}
.oinfo{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:12px 0 0;font-size:12px}
.oinfo dt{color:var(--muted)}.oinfo dd{margin:0}
.odesc{margin:0 0 6px;white-space:pre-line}.odesc.none{color:var(--muted)}
.orow{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:8px 0}
.odep{border-top:1px solid var(--line);padding:9px 0}
.odh{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.odh>b{min-width:110px}
.odh .rvc{margin-left:auto}.odh .rvb{font-size:13px;padding:2px 10px}
.ofl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:5px 10px;align-items:start;margin-top:8px}
.ofl[hidden]{display:none}.ofl>span{font-size:12px;color:var(--muted);padding-top:5px}
.ofl .rvo,.one .rvt{margin:0;width:100%;min-width:0}
.rvo{border-color:var(--line)}.rvo:focus,.rvo:not(:placeholder-shown){border-color:var(--rtk)}
.obot{display:flex;justify-content:space-between;margin-top:12px;padding-top:12px;
border-top:1px solid var(--line)}
.ogen{border-top:1px solid var(--line);padding-top:9px}
.onotes h3{margin:14px 0 6px;font-size:13px;color:var(--muted)}
.rvtags{display:flex;flex-wrap:wrap;gap:3px;margin-top:4px;width:0;min-width:100%}
.rvtag{font:inherit;font-size:10px;line-height:15px;padding:0 5px;border-radius:3px;border:0;
background:var(--line);color:var(--fg);cursor:pointer}
.rvtag:hover{background:var(--rtk);color:#fff}
tr.item.rv-changed>td.name{box-shadow:inset 3px 0 var(--role)}
.rvt[hidden],.rvtags[hidden]{display:none}
/* A wide table's scrollbar, kept at the bottom of the screen (_JS): the
box's own is at the bottom of the table, maybe far below. */
.scroll.proxied{scrollbar-width:none}.scroll.proxied::-webkit-scrollbar{display:none}
.hbar{position:sticky;bottom:0;z-index:1;overflow-x:auto;overflow-y:hidden;
background:var(--bg)}.hbar>div{height:1px}.hbar[hidden]{display:none}
@media print{nav,.review,.jump,.stuck,.hbar{display:none}.scroll{overflow:visible}}
"""

_JS = """
(function(){
var $=function(id){return document.getElementById(id);};
// A block's shot buttons: that shot's thumbnail, beside the button --
// above it when there's no room below.
var pop=document.createElement('img');pop.id='sbpop';pop.alt='';document.body.appendChild(pop);
document.querySelectorAll('.sb img').forEach(function(img){
var sb=img.parentNode;
sb.addEventListener('mouseenter',function(){pop.src=img.src;pop.style.display='block';
var r=sb.getBoundingClientRect(),h=pop.offsetHeight,w=pop.offsetWidth;
pop.style.left=Math.max(4,Math.min(r.left,innerWidth-w-4))+'px';
pop.style.top=(r.bottom+4+h<innerHeight?r.bottom+4:Math.max(4,r.top-4-h))+'px';});
sb.addEventListener('mouseleave',function(){pop.style.display='none';});});
var nav=document.querySelector('nav'),bar=document.querySelector('.filters');
var ctl=['f-name','f-group','f-dep','f-state','f-rtk','f-notes','f-closed','f-farm'].map($);
function navHeight(){var sticky=getComputedStyle(nav).position==='sticky',
h=sticky?nav.offsetHeight:0,root=document.documentElement.style;
root.setProperty('--nav-h',h+16+'px');navTop=nav.classList.contains('away')?0:h;
var m=$('nav-menu'),first=[].filter.call(nav.querySelectorAll('.chip,.links a'),function(c){
return c!==m&&c.offsetParent;})[0];if(m&&first)m.style.top=first.offsetTop+'px';}
// A phone's header: a sheet over the page from ☰, shut by a click
// outside it, Esc, or starting the review.
function sheet(on){document.body.classList.toggle('hdr-open',on);
$('nav-menu').setAttribute('aria-expanded',on);if($('hdr-menu'))$('hdr-menu').setAttribute('aria-expanded',on);}
var hm=$('nav-menu').cloneNode(true);hm.id='hdr-menu';document.querySelector('header h1').appendChild(hm);
[$('nav-menu'),hm].forEach(function(b){b.addEventListener('click',function(ev){ev.stopPropagation();
sheet(!document.body.classList.contains('hdr-open'));});});
document.addEventListener('click',function(ev){if(document.body.classList.contains('hdr-open')&&
!ev.target.closest('header'))sheet(false);});
document.addEventListener('keydown',function(ev){if(ev.key==='Escape'&&
document.body.classList.contains('hdr-open')){sheet(false);ev.stopImmediatePropagation();}});
// Unfolding the bar shifts the page (the browser keeps what's in view):
// that scroll is no reader's, the next 500 ms of them are ignored.
var navLock=0;
$('nav-more').addEventListener('click',function(){var on=nav.classList.toggle('more');navLock=Date.now();
this.setAttribute('aria-expanded',on);navHeight();place();});
var lastY=window.scrollY;window.addEventListener('scroll',function(){var y=window.scrollY,
away=nav.classList.contains('away');if(Date.now()-navLock<500){lastY=y;return;}
// Scrolling down folds the filters too: they come back with the bar.
if(window.innerWidth>=700||y<80||document.querySelector('header').getBoundingClientRect().bottom>0)away=false;
else if(y>lastY+6){away=true;if(nav.classList.contains('more')){nav.classList.remove('more');
$('nav-more').setAttribute('aria-expanded',false);}}else if(y<lastY-6)away=false;
if(away!==nav.classList.contains('away')){nav.classList.toggle('away',away);navHeight();place();}
lastY=y;},{passive:true});
var navTop=0,heads=[].map.call(document.querySelectorAll('.scroll'),function(box){
var table=box.querySelector('table'),stuck=document.createElement('div'),
copy=table.cloneNode(false);copy.appendChild(table.tHead.cloneNode(true));
stuck.className='stuck';stuck.hidden=true;stuck.setAttribute('aria-hidden','true');
stuck.appendChild(copy);document.body.appendChild(stuck);
var bar=document.createElement('div');bar.className='hbar';bar.hidden=true;
bar.appendChild(document.createElement('div'));box.after(bar);
bar.addEventListener('scroll',function(){if(box.scrollLeft!==bar.scrollLeft)box.scrollLeft=bar.scrollLeft;},{passive:true});
box.addEventListener('scroll',function(){if(bar.scrollLeft!==box.scrollLeft)bar.scrollLeft=box.scrollLeft;
place();},{passive:true});
if(window.ResizeObserver)new ResizeObserver(function(){size();}).observe(table);
return{box:box,table:table,stuck:stuck,copy:copy,bar:bar};});
function size(){heads.forEach(function(h){var wide=h.box.scrollWidth>h.box.clientWidth+1;
h.bar.hidden=!wide;h.box.classList.toggle('proxied',wide);
if(wide){h.bar.firstChild.style.width=h.box.scrollWidth+'px';h.bar.scrollLeft=h.box.scrollLeft;}var src=h.table.tHead.rows[0].cells,
dst=h.copy.tHead.rows[0].cells,w=function(el){return el.getBoundingClientRect().width+'px';};
h.copy.style.width=w(h.table);for(var i=0;i<src.length;i++)dst[i].style.width=w(src[i]);});
place();}
function place(){heads.forEach(function(h){var b=h.box.getBoundingClientRect(),
head=h.table.tHead.getBoundingClientRect();
var show=b.width>0&&head.top<navTop&&b.bottom>navTop+head.height;
h.stuck.hidden=!show;if(!show)return;
h.stuck.style.top=navTop+'px';h.stuck.style.left=b.left+h.box.clientLeft+'px';
h.stuck.style.width=h.box.clientWidth+'px';
h.copy.style.transform='translateX('+(-h.box.scrollLeft)+'px)';});}
function match(el){
var q=ctl[0].value.trim().toLowerCase(),g=ctl[1].value,d=ctl[2].value,st=ctl[3].value;
if(q&&el.dataset.name.indexOf(q)<0)return false;
if(g&&el.dataset.group!==g)return false;
if(ctl[4].checked&&el.dataset.rtk==='0')return false;
if(ctl[5].checked&&el.dataset.notes==='0')return false;
if(ctl[7].checked&&el.dataset.farm==='0')return false;
if(d||st){var states=el.dataset.states.split(' ').filter(Boolean).map(function(x){
return x.split(':');});
if(!states.some(function(p){return(!d||p[0]===d)&&(!st||p[1]===st);}))return false;}
return true;}
function apply(){
var on=ctl.some(function(c,i){return i!==6&&(c.type==='checkbox'?c.checked:c.value);});
bar.classList.toggle('active',on);
var closed=ctl[6].checked,notes=0;
document.body.classList.toggle('show-closed',closed);
['assets','shots'].forEach(function(id){
var sec=$(id),n=0,items=sec.querySelectorAll('tr.item');
items.forEach(function(el){el.hidden=!match(el);
var shown=+(closed?el.dataset.threads:el.dataset.notes),row=el.nextElementSibling,
b=el.querySelector('button.jump');
if(row&&row.classList.contains('notes'))row.hidden=el.hidden||!shown||
!(printing||b.getAttribute('aria-expanded')==='true');
if(!el.hidden){n++;notes+=shown;}});
sec.querySelectorAll('tr.group').forEach(function(row){
var next=row.nextElementSibling,any=false;
while(next&&!next.classList.contains('group')){
if(!next.hidden&&next.classList.contains('item'))any=true;next=next.nextElementSibling;}
row.hidden=!any;});
var none=sec.querySelector('.nomatch'),table=sec.querySelector('.scroll');
if(none)none.hidden=!items.length||n>0;if(table)table.hidden=items.length&&!n;
$('c-'+id).textContent=n;});$('c-notes').textContent=notes;size();}
var printing=false;
document.addEventListener('click',function(e){var b=e.target.closest('button.jump');
if(!b)return;b.setAttribute('aria-expanded',b.getAttribute('aria-expanded')!=='true');
apply();});
$('all-notes').addEventListener('click',function(){
var bs=[].filter.call(document.querySelectorAll('button.jump'),function(b){
return b.offsetParent;}),open=bs.some(function(b){
return b.getAttribute('aria-expanded')!=='true';});
bs.forEach(function(b){b.setAttribute('aria-expanded',open);});
$('all-notes').setAttribute('aria-pressed',open);apply();});
ctl.forEach(function(c){c.addEventListener('input',apply);
c.addEventListener('change',apply);});
$('f-reset').addEventListener('click',function(){ctl.forEach(function(c,i){
if(i===6)return;if(c.type==='checkbox')c.checked=false;else c.value='';});apply();});
var cols=[].slice.call(document.querySelectorAll('.cols input')),
colStyle=document.createElement('style'),colKey='mp-snapshot-hidden-cols';
document.head.appendChild(colStyle);
// While reviewing, Blender file and Last render are hidden (their ticks
// as before kept in data-before, put back after, the one saved).
function applyCols(save){var hidden=cols.filter(function(c){return!c.checked;})
.map(function(c){return c.dataset.key;});
var kept=cols.filter(function(c){return c.dataset.before?c.dataset.before!=='1':!c.checked;})
.map(function(c){return c.dataset.key;});
colStyle.textContent=hidden.map(function(k){
return '[data-col="'+CSS.escape(k)+'"]{display:none}';}).join('');
document.querySelector('.cols').classList.toggle('hiding',hidden.length>0);
if(save){try{localStorage.setItem(colKey,JSON.stringify(kept));}catch(e){}}
eqCols(document.body.classList.contains('reviewing'));size();}
try{var saved=JSON.parse(localStorage.getItem(colKey)||'[]');
cols.forEach(function(c){if(saved.indexOf(c.dataset.key)>=0)c.checked=false;});}catch(e){}
cols.forEach(function(c){c.addEventListener('change',function(){applyCols(true);});});
applyCols(false);
var menu=document.querySelector('.cols');
document.addEventListener('click',function(e){if(!menu.contains(e.target))menu.open=false;});
function unfold(hash){var el=hash&&document.getElementById(hash.slice(1));
if(!el)return;var own=el.querySelector(':scope>details.sec');if(own)own.open=true;
for(var d=el.closest('details.sec');d;d=d.parentElement.closest('details.sec'))
d.open=true;}
document.addEventListener('click',function(e){var a=e.target.closest('a[href^="#"]');
if(a)unfold(a.getAttribute('href'));});
window.addEventListener('hashchange',function(){unfold(location.hash);});
window.addEventListener('beforeprint',function(){printing=true;
document.querySelectorAll('details.sec').forEach(function(d){d.open=true;});apply();});
window.addEventListener('afterprint',function(){printing=false;apply();});
unfold(location.hash);
document.querySelectorAll('details.sec').forEach(function(d){
d.addEventListener('toggle',size);});
window.addEventListener('scroll',place,{passive:true});
window.addEventListener('resize',function(){navHeight();size();});navHeight();apply();
// In-page review (the Review chip): a box per department on each row, a
// file the addon's Import review reads (REVIEW_JSON_FORMAT: a v4 template's
// rows), the work in progress kept in this browser.
var rvMeta=JSON.parse($('review-meta').textContent),
rvKey='mp-review:'+rvMeta.project+':'+rvMeta.snapshot,
OKS=['ok','yes','oui','v','x','✓','✔','valid','validé','valide'],NOS=['no','non'],
FIXED=['group','filename','description','description_exported','stable_version','wip_version','global'],
rv={author:'',role:'',date:'',files:{}},rvBuilt=false,rows={};
document.querySelectorAll('tr.item').forEach(function(el){rows[el.dataset.file]=el;});
function states(el){var o={};el.dataset.states.split(' ').filter(Boolean).forEach(function(x){
var p=x.split(':');o[p[0]]=p[1];});return o;}
function done(st){return st==='done'||st==='rework';}
function entry(f){return rv.files[f]||(rv.files[f]={deps:{},all:false,text:'',desc:null});}
function changes(e){var n=Object.keys(e.deps).length+(e.all?1:0)+(e.text.trim()?1:0);
var el=rows[arguments[1]];if(e.desc!==null&&el&&e.desc.trim()&&e.desc.trim()!==el.dataset.desc)n++;
return n;}
function count(){var n=0,files=0;Object.keys(rv.files).forEach(function(f){
var c=changes(rv.files[f],f);n+=c;if(c)files++;});return[n,files];}
function save(){try{localStorage.setItem(rvKey,JSON.stringify(rv));
var d=new Date();$('rv-saved').textContent='Kept in this browser ('+
('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2)+') -- download it to send it';
}catch(e){$('rv-saved').textContent='Not kept by this browser: download it before closing';}}
function tagButtons(el,ta){var shots=el.dataset.shots.split(' ').filter(Boolean);
if(shots.length<2)return null;var box=document.createElement('div');box.className='rvtags';
shots.forEach(function(s){var b=document.createElement('button');b.type='button';
b.className='rvtag';b.textContent='['+s+']';b.title='A new line for a retake of that shot only';
b.addEventListener('click',function(){addTag(ta,s);});box.appendChild(b);});return box;}
// A shot's tag: on the line the cursor is on while it is empty (or only
// tags), else on a new line at the end -- one retake per shot, in a row.
function addTag(ta,s){var NL=String.fromCharCode(10),v=ta.value,at=ta.selectionStart,
start=v.lastIndexOf(NL,at-1)+1,end=v.indexOf(NL,at),t='['+s+'] ';if(end<0)end=v.length;
var bare=v.slice(start,end).split(' ').every(function(w){return!w||w.charAt(0)==='[';});
if(!bare){start=end=v.length;if(v)t=NL+t;}
ta.value=v.slice(0,start)+t+v.slice(end);ta.focus();
ta.selectionStart=ta.selectionEnd=start+t.length;ta.dispatchEvent(new Event('input',{bubbles:true}));}
function area(cls,ph){var t=document.createElement('textarea');t.className='rvt '+cls;
t.rows=1;t.placeholder=ph;t.hidden=true;return t;}
function grow(t){if(t.hidden)return;t.style.height='auto';t.style.height=t.scrollHeight+2+'px';}
var RT='One retake per line. [sh020] [f12-40] at its start for a shot / frames, note: for a remark';
function build(){rvBuilt=true;
Object.keys(rows).forEach(function(f){var el=rows[f],st=states(el),
valid=el.dataset.valid.split(' ');
el.querySelectorAll('td[data-col^="d:"]').forEach(function(td){var d=td.dataset.col.slice(2);
if(!(d in st))return;var box=document.createElement('div');box.className='rvc';
var ok=document.createElement('button');ok.type='button';ok.className='rvb yes';ok.textContent='✓';
ok.dataset.f=f;ok.dataset.d=d;ok.dataset.act='ok';ok.disabled=!done(st[d]);
ok.title=done(st[d])?(valid.indexOf(d)>=0?'Already validated -- validate it again as your role':
'Validate it as your role'):'Not done: nothing to validate yet';
var rt=document.createElement('button');rt.type='button';rt.className='rvb rt';
rt.textContent='✗';rt.dataset.f=f;rt.dataset.d=d;rt.dataset.act='rt';
rt.title='Retake: write what to fix (or nothing, to just withdraw a validation)';
var ta=area('dep',RT);ta.dataset.f=f;ta.dataset.d=d;
box.appendChild(ok);box.appendChild(rt);td.appendChild(box);
var tags=tagButtons(el,ta);if(tags){tags.hidden=true;tags.dataset.for=d;td.appendChild(tags);}
td.appendChild(ta);});
var name=el.querySelector('td.name'),g=document.createElement('div');g.className='rvg';
var any=Object.keys(st).some(function(d){return done(st[d]);});
[['all','✓ all done',!any,'Validate every department done so far (V, on One file)'],
['gen','+ general retake',false,'A retake for no department in particular (X, on One file)'],
['desc','✎ description',false,'Change the description']].forEach(function(a){
var b=document.createElement('button');b.type='button';b.className='rvb '+a[0];
b.textContent=a[1];b.disabled=a[2];b.title=a[3];b.dataset.f=f;b.dataset.act=a[0];g.appendChild(b);});
name.appendChild(g);var gt=area('gen',RT);gt.dataset.f=f;gt.dataset.g='text';
var tags=tagButtons(el,gt);if(tags){tags.hidden=true;tags.dataset.for='-gen';name.appendChild(tags);}
name.appendChild(gt);var dt=area('desc','The new description');dt.dataset.f=f;dt.dataset.g='desc';
dt.classList.add('rvdesc');name.appendChild(dt);});paint();}
function paint(){if(!rvBuilt)return;
Object.keys(rows).forEach(function(f){var el=rows[f],e=rv.files[f]||{deps:{},all:false,text:'',desc:null},
st=states(el);
el.querySelectorAll('.rvc').forEach(function(box){var d=box.querySelector('.yes').dataset.d,
v=e.deps[d],td=box.parentNode,ta=td.querySelector('textarea.dep'),tags=td.querySelector('.rvtags');
box.querySelector('.yes').setAttribute('aria-pressed',!!(v&&v.ok));
box.querySelector('.yes').classList.toggle('via',!v&&e.all&&done(st[d]));
box.querySelector('.rt').setAttribute('aria-pressed',!!(v&&v.no));
ta.hidden=!(v&&v.no);if(tags)tags.hidden=ta.hidden;if(v&&v.no&&ta.value!==v.text)ta.value=v.text;
grow(ta);});
var g=el.querySelector('.rvg');if(!g)return;
g.querySelector('.all').setAttribute('aria-pressed',e.all);
var gt=el.querySelector('textarea.gen'),dt=el.querySelector('textarea.rvdesc'),
gtags=el.querySelector('.rvtags[data-for="-gen"]');
if(gt.dataset.open!=='1')gt.hidden=!e.text;if(gt.value!==e.text)gt.value=e.text;
if(gtags)gtags.hidden=gt.hidden;grow(gt);grow(dt);
g.querySelector('.gen').setAttribute('aria-pressed',!gt.hidden);
if(e.desc===null)dt.hidden=true;else{dt.hidden=false;if(dt.value!==e.desc)dt.value=e.desc;grow(dt);}
g.querySelector('.desc').setAttribute('aria-pressed',!dt.hidden);
el.classList.toggle('rv-changed',changes(e,f)>0||!gt.hidden);});
var c=summary();$('rv-count').textContent=c.files?c.files+' reviewed · '+c.ok+' validated · '+
c.rt+' retake'+(c.rt>1?'s':'')+(c.out?' · '+c.out+' withdrawn':''):'';
$('rv-mode').textContent='✎ Review'+(c.files?' · '+c.files:'');
paintOne();size();}
// The header's summary: files changed, validations (all done's
// included), retake lines (notes aside), empty ✗ (withdrawn).
function retakes(t){return t.split(String.fromCharCode(10)).filter(function(l){
var w=l.trim().split(' ').filter(function(x){return x&&x.charAt(0)!=='[';});
return w.length&&w[0].toLowerCase().indexOf('note:')!==0;}).length;}
function summary(){var c={files:0,ok:0,rt:0,out:0};Object.keys(rv.files).forEach(function(f){
var e=rv.files[f],el=rows[f];if(!el||!changes(e,f))return;var st=states(el);c.files++;
Object.keys(e.deps).forEach(function(d){var v=e.deps[d];if(v.ok)c.ok++;
else if(v.text.trim())c.rt+=retakes(v.text);else c.out++;});
if(e.all)Object.keys(st).forEach(function(d){if(done(st[d])&&!e.deps[d])c.ok++;});
c.rt+=retakes(e.text);});return c;}
document.addEventListener('click',function(ev){var b=ev.target.closest('.rvb');if(!b||b.disabled)return;
var e=entry(b.dataset.f),d=b.dataset.d,act=b.dataset.act,focus=null;
if(act==='ok'){if(e.deps[d]&&e.deps[d].ok)delete e.deps[d];else e.deps[d]={ok:1};}
else if(act==='rt'){if(e.deps[d]&&e.deps[d].no)delete e.deps[d];
else{e.deps[d]={no:1,text:''};focus=function(){return oneField('d:'+d)||rows[b.dataset.f].querySelector(
'textarea.dep[data-d="'+CSS.escape(d)+'"]');};}}
else if(act==='all')e.all=!e.all;
else if(act==='gen'){var gt=rows[b.dataset.f].querySelector('textarea.gen');
if(gt.hidden){gt.dataset.open='1';gt.hidden=false;focus=function(){return oneField('g')||gt;};}
else{gt.dataset.open='';e.text='';}}
else if(act==='desc'){e.desc=e.desc===null?rows[b.dataset.f].dataset.desc:null;}
paint();save();var t=focus&&focus();if(t)t.focus();});
// A row's name opens it on its own (One file), reviewing or not.
document.addEventListener('click',function(ev){
var n=ev.target.closest('td.name>b');if(!n)return;oneF=n.closest('tr.item').dataset.file;setView(true);});
document.addEventListener('input',function(ev){var t=ev.target;
if(t.classList.contains('rvo')){oneInput(t);return;}if(!t.classList.contains('rvt'))return;
grow(t);
var e=entry(t.dataset.f);if(t.dataset.d){var v=e.deps[t.dataset.d];if(v)v.text=t.value;}
else if(t.dataset.g==='text')e.text=t.value;else if(t.dataset.g==='desc')e.desc=t.value;
paint();save();});
['author','role','date'].forEach(function(k){$('rv-'+k).addEventListener('input',function(){
rv[k]=$('rv-'+k).value;save();});});
rvMeta.roles.forEach(function(r){var o=document.createElement('option');o.value=r;o.textContent=r;
$('rv-role').appendChild(o);});
var RVHIDE=['file','render','done','valid'];
function setMode(on){if(on===document.body.classList.contains('reviewing'))return;
document.body.classList.toggle('reviewing',on);
$('rv-mode').setAttribute('aria-pressed',on);$('rv-start').setAttribute('aria-pressed',on);
$('rv-start').textContent=on?'Stop reviewing':'✎ Review on this page';
cols.forEach(function(c){if(RVHIDE.indexOf(c.dataset.key)<0)return;
if(on){c.dataset.before=c.checked?'1':'0';c.checked=false;}
else{c.checked=c.dataset.before==='1';delete c.dataset.before;}});
if(on&&!rvBuilt)build();applyCols(false);navHeight();size();
if(one&&!one.hidden)openOne(oneF);}
// While reviewing, the name column as narrow as it goes and the table's
// width shared out evenly between its department columns: room for the
// retakes, the ✓ ✗ lined up.
function eqCols(on){heads.forEach(function(h){var cells=[].slice.call(h.table.tHead.rows[0].cells),
ths=cells.filter(function(c){return(c.dataset.col||'').indexOf('d:')===0&&
getComputedStyle(c).display!=='none';}),
name=cells.filter(function(c){return!c.dataset.col;})[0];
if(name)name.style.width=on?'1px':'';
ths.forEach(function(c){c.style.width=on?(100/ths.length).toFixed(3)+'%':'';});});}
['rv-mode','rv-start'].forEach(function(id){$(id).addEventListener('click',function(){
var on=!document.body.classList.contains('reviewing');setMode(on);
if(on&&window.innerWidth<700)setView(true);sheet(false);});});
function fields(){$('rv-author').value=rv.author;$('rv-role').value=rv.role;$('rv-date').value=rv.date;}
function exportRows(){var out=[];Object.keys(rv.files).forEach(function(f){var e=rv.files[f],el=rows[f];
if(!el||!changes(e,f))return;var st=states(el),row={filename:f,stable_version:el.dataset.stable,
description_exported:el.dataset.desc};
Object.keys(e.deps).forEach(function(d){var v=e.deps[d];row[d]=v.ok?'ok':(v.text.trim()||'no');});
if(e.all)Object.keys(st).forEach(function(d){if(done(st[d])&&!(d in row))row[d]='ok';});
if(e.text.trim())row.global=e.text.trim();
if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==el.dataset.desc)row.description=e.desc.trim();
out.push(row);});return out;}
// <project>_review_<YYYY-MM-DD_HH-MM>_<role>_<author>.json: two reviewers'
// files side by side on a drive, never one over the other.
function slug(t){return String(t||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase()
.replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');}
function reviewName(){var d=new Date(),two=function(n){return('0'+n).slice(-2);},
stamp=d.getFullYear()+'-'+two(d.getMonth()+1)+'-'+two(d.getDate())+'_'+two(d.getHours())+'-'+two(d.getMinutes());
return[rvMeta.file_name.split('_review_')[0]+'_review_'+stamp,slug(rv.role),slug(rv.author)]
.filter(Boolean).join('_')+'.json';}
$('rv-save').addEventListener('click',function(){var r=exportRows();
if(!r.length){alert('Nothing to send yet: validate or write a retake first.');return;}
var needsRole=r.some(function(row){return Object.keys(row).some(function(k){return FIXED.indexOf(k)<0||k==='global';});});
if(needsRole&&!rv.role){alert('Pick your role first: your validations and retakes are recorded under it.');
$('rv-role').focus();return;}
var data={format:rvMeta.format,schema_version:rvMeta.schema_version,project:rvMeta.project,
snapshot:rvMeta.snapshot,author:rv.author,role:rv.role,review_date:rv.date,
written_at:new Date().toISOString().slice(0,19),rows:r};
var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],
{type:'application/json'}));a.download=reviewName();document.body.appendChild(a);a.click();
setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},1000);});
$('rv-load').addEventListener('change',function(){var file=this.files[0];this.value='';if(!file)return;
var reader=new FileReader();reader.onload=function(){var data;
try{data=JSON.parse(reader.result);}catch(e){alert('Not a review file.');return;}
if(data.format!==rvMeta.format){alert('Not a review downloaded from a snapshot page.');return;}
if(data.project!==rvMeta.project&&!confirm('This review is for '+data.project+', not '+rvMeta.project+'. Load it anyway?'))return;
rv={author:data.author||'',role:data.role||'',date:data.review_date||'',files:{}};var unknown=0;
(data.rows||[]).forEach(function(row){var f=row.filename,el=rows[f];if(!el){unknown++;return;}
var e=entry(f),st=states(el);Object.keys(row).forEach(function(k){if(FIXED.indexOf(k)>=0)return;
var v=String(row[k]).trim(),l=v.toLowerCase();
if(OKS.indexOf(l)>=0)e.deps[k]={ok:1};else if(NOS.indexOf(l)>=0)e.deps[k]={no:1,text:''};
else e.deps[k]={no:1,text:v};});
var gv=String(row.global||'').trim(),gl=gv.toLowerCase();
if(OKS.indexOf(gl)>=0)e.all=true;else if(NOS.indexOf(gl)>=0)Object.keys(st).forEach(function(d){
if(done(st[d])&&!e.deps[d])e.deps[d]={no:1,text:''};});else e.text=gv;
if(row.description)e.desc=row.description;});
fields();setMode(true);paint();save();
if(unknown)alert(unknown+' file(s) of that review are not on this page (renamed, or another snapshot).');};
reader.readAsText(file);});
$('rv-clear').addEventListener('click',function(){if(!count()[0]||confirm('Clear this review? What you wrote here is lost (a downloaded file is kept).')){
rv={author:rv.author,role:rv.role,date:rv.date,files:{}};
document.querySelectorAll('textarea.rvt').forEach(function(t){t.value='';t.dataset.open='';});paint();save();}});
// One file at a time (▣ One file): a card under the nav in place of the
// tables, built on demand from the row itself -- its cells, its data-*,
// its images' sources -- so the page carries nothing more. Its buttons are
// the row's own (cloned: the click handler above serves both); a block's
// retakes get a field per shot, put back together as [sh020] lines.
var NL=String.fromCharCode(10),one=document.createElement('div'),oneF=null,
ALL=[].slice.call(document.querySelectorAll('tr.item'));
one.id='one';one.className='one';one.hidden=true;nav.after(one);
ALL.forEach(function(r){var b=r.querySelector('td.name>b');if(b)b.title='Open this file on its own page (One file)';});
function shotsOf(f){return rows[f].dataset.shots.split(' ').filter(Boolean);}
function splitText(t,shots){var o={'':[]};shots.forEach(function(s){o[s]=[];});
t.split(NL).forEach(function(l){var w=l.trim().split(' '),k=w[0].slice(1,-1);
if(!l.trim())return;if(w[0].charAt(0)==='['&&w[0].slice(-1)===']'&&k&&o[k])o[k].push(w.slice(1).join(' '));
else o[''].push(l.trim());});return o;}
function oneField(k,s){return one.hidden?null:[].filter.call(one.querySelectorAll('.rvo'),
function(t){return t.dataset.k===k&&(s==null||t.dataset.shot===s);})[0];}
function oneInput(t){grow(t);var f=t.dataset.f,k=t.dataset.k,shots=shotsOf(f),out=[];
['' ].concat(shots).forEach(function(s){[].forEach.call(one.querySelectorAll('.rvo'),function(x){
if(x.dataset.k!==k||x.dataset.shot!==s)return;x.value.split(NL).forEach(function(l){
if(l.trim())out.push((s?'['+s+'] ':'')+l.trim());});});});
var e=entry(f);if(k==='g')e.text=out.join(NL);else if(e.deps[k.slice(2)])e.deps[k.slice(2)].text=out.join(NL);
paint();save();}
// A block: the field for all its shots, a button per shot, and a shot's
// field only once its button is clicked (oneOpen) or it holds a retake.
var oneOpen={};
// The card's keys, under its name: each one a <kbd>, then what it does.
function keys(parent,list){var p=add(parent,'div','okeys');list.forEach(function(k){
var s=add(p,'span');add(s,'kbd',null,k[0]);s.appendChild(document.createTextNode(' '+k[1]));});}
function oneFields(box,f,k,shots,ph){var list=shots.length>1?[''].concat(shots):[''];
if(list.length>1){var tags=add(box,'div','rvtags oshb');add(tags,'span',null,'A shot:');
shots.forEach(function(s){var b=add(tags,'button','rvtag','['+s+']');b.type='button';
b.dataset.shot=s;b.title='A retake for '+s+' only';b.addEventListener('click',function(){
oneOpen[k+' '+s]=1;paintOne();var t=oneField(k,s);if(t)t.focus();});});}
list.forEach(function(s){var pair=add(box,'div','opair');pair.dataset.shot=s;
if(list.length>1)add(pair,'span',null,s||'all shots');
var t=add(pair,'textarea','rvo');t.rows=1;t.dataset.f=f;t.dataset.k=k;
t.dataset.shot=s;t.placeholder=s?'Retakes on '+s+' only, one per line':ph;
if(list.length<2)t.style.gridColumn='1 / -1';});}
function add(parent,tag,cls,text){var x=document.createElement(tag);if(cls)x.className=cls;
if(text!=null)x.textContent=text;parent.appendChild(x);return x;}
// '#stats': the Progress block as a card of its own, before the first file.
function openOne(f){if(f!==oneF)oneOpen={};oneF=f;var el=f==='#stats'?null:rows[f];
one.textContent='';var card=add(one,'div','ocard'),top=add(card,'div','otop'),btns=add(top,'div','obtns');
var back=add(btns,'button','chip','← Table'),prev=add(btns,'button','chip','‹ Previous'),
next=add(btns,'button','chip','Next ›'),who=add(top,'div','owho'),jump=add(top,'select','ojump');
// Straight to another file: the ones the filters keep, by group, ✎ the
// ones reviewed already.
jump.setAttribute('aria-label','Go to a file');var og=null,last='';
var so=add(jump,'option',null,'Progress (stats)');so.value='#stats';so.selected=!el;
ALL.forEach(function(r){if(r.hidden&&r!==el)return;
var lab=(r.closest('section').id==='assets'?'Assets':'Shots')+' · '+r.dataset.group;
if(lab!==last){og=add(jump,'optgroup');og.label=last=lab;}
var o=add(og,'option',null,(r.classList.contains('rv-changed')?'✎ ':'')+r.querySelector('td.name b').textContent);
o.value=r.dataset.file;o.selected=r===el;});
jump.addEventListener('change',function(){openOne(jump.value);keepView();});
back.type=prev.type=next.type='button';back.dataset.go='0';prev.dataset.go='-1';next.dataset.go='1';
back.title='Back to the table (Esc)';prev.title='Previous file (←)';next.title='Next file (→)';
prev.disabled=!step(-1);next.disabled=!step(1);
if(!el){add(who,'div','oname','Progress');add(who,'div','opos','The whole project, filters aside');
keys(who,[['→','first file'],['Esc','table']]);var ov=document.getElementById('overview'),
sc=add(card,'div','ostats');if(ov)[].forEach.call(ov.querySelector('details').children,function(x){
if(x.tagName==='SUMMARY')return;var k=x.cloneNode(true);k.removeAttribute('id');
k.querySelectorAll('[id]').forEach(function(y){y.removeAttribute('id');});sc.appendChild(k);});
var sb=add(card,'div','obot');sb.appendChild(prev.cloneNode(true));sb.appendChild(next.cloneNode(true));return;}
var st=states(el),shots=shotsOf(f);
add(who,'div','oname',el.querySelector('td.name b').textContent);
add(who,'div','opos',(el.closest('section').id==='assets'?'Asset':'Shot')+' · '+el.dataset.group+' · '+
(ALL.filter(function(r){return!r.hidden;}).indexOf(el)+1)+' / '+ALL.filter(function(r){return!r.hidden;}).length+
(bar.classList.contains('active')?' (filtered)':''));
keys(who,[['← →','files'],['Esc','table']].concat(document.body.classList.contains('reviewing')?
[['V','all done'],['X','general retake'],['Ctrl+Enter','leave a box']]:[]));
var body=add(card,'div','obody'),left=add(body,'div'),right=add(body,'div'),
img=el.querySelector('img.thumb'),big=null;
if(img){big=add(left,'img','obig');big.src=img.src;big.alt='';}
var sbs=el.querySelectorAll('.sbs .sb');if(sbs.length&&big){var strip=add(left,'div','oshots');
[[img.src,'block']].concat([].map.call(sbs,function(sb){var im=sb.querySelector('img');
return[im?im.src:'',sb.firstChild.textContent];})).forEach(function(s,n){
var b=add(strip,'button');b.type='button';b.disabled=!s[0];b.setAttribute('aria-pressed',n===0);
if(s[0]){var im=add(b,'img');im.src=s[0];im.alt='';}add(b,'span',null,s[1]);
b.addEventListener('click',function(){big.src=s[0];strip.querySelectorAll('button').forEach(function(x){
x.setAttribute('aria-pressed',x===b);});});});}
var dl=add(left,'dl','oinfo');[['done','Done'],['valid','Validated'],['file','Blender file'],
['render','Last render']].forEach(function(c){
var td=el.querySelector('td[data-col="'+c[0]+'"]');if(!td)return;add(dl,'dt',null,c[1]);
add(dl,'dd',td.className).innerHTML=td.innerHTML;});
add(right,'p','odesc'+(el.dataset.desc?'':' none'),el.dataset.desc||'No description');
var acts=add(right,'div','orow');el.querySelectorAll('.rvg .rvb').forEach(function(b){
if(b.dataset.act!=='one')acts.appendChild(b.cloneNode(true));});
var dt=add(right,'textarea','rvt rvdesc');dt.rows=1;dt.dataset.f=f;dt.dataset.g='desc';
dt.placeholder='The new description';
var gen=add(right,'div','ofl ogen');gen.dataset.k='g';
oneFields(gen,f,'g',shots,'A general retake per line, note: for a remark');
el.querySelectorAll('td[data-col^="d:"]').forEach(function(td){var d=td.dataset.col.slice(2);
if(!(d in st))return;var dep=add(right,'div','odep'),h=add(dep,'div','odh');add(h,'b',null,d);
[].forEach.call(td.children,function(x){if(x.matches('.pill,.ok'))h.appendChild(x.cloneNode(true));});
var rvc=td.querySelector('.rvc');if(rvc)h.appendChild(rvc.cloneNode(true));
rtksOf(el,d).forEach(function(li){dep.appendChild(rtkLine(li,d));});
var box=add(dep,'div','ofl');box.dataset.k='d:'+d;
oneFields(box,f,'d:'+d,shots,'One retake per line, [f12-40] at its start for frames, note: for a remark');});
var notes=el.nextElementSibling;if(notes&&notes.classList.contains('notes')){
// The threads not shown under a department already (their replies with them).
var ul=notes.querySelector('.threads').cloneNode(true),skip=false,mine=placed(el);
[].slice.call(ul.children).forEach(function(li,i){var src=notes.querySelector('.threads').children[i];
if(li.classList.contains('root'))skip=mine.indexOf(src)>=0;if(skip)li.remove();});
var shown=[].filter.call(ul.children,function(li){return document.body.classList.contains('show-closed')||
!li.classList.contains('closed');}).length;
if(shown){var nb=add(right,'div','onotes');add(nb,'h3',null,mine.length?'Other notes':'Notes');nb.appendChild(ul);}}
var bot=add(card,'div','obot');bot.appendChild(prev.cloneNode(true));bot.appendChild(next.cloneNode(true));
paintOne();}
// A department's open RTKs: the row's threads, roots not closed, of type
// rtk, with that department among their tags.
function threadsOf(el){var n=el.nextElementSibling;return n&&n.classList.contains('notes')?
[].slice.call(n.querySelector('.threads').children):[];}
function rtksOf(el,d){return threadsOf(el).filter(function(li){
return li.classList.contains('root')&&!li.classList.contains('closed')&&li.querySelector('.type.t-rtk')&&
[].some.call(li.querySelectorAll('.tag'),function(t){return t.textContent.split(', ').indexOf(d)>=0;});});}
function placed(el){var st=states(el),out=[];Object.keys(st).forEach(function(d){
rtksOf(el,d).forEach(function(li){if(out.indexOf(li)<0)out.push(li);});});return out;}
// One line: an RTK pill (its shot in it) holding the rest -- who, when,
// role, frames -- in its tooltip, or under it once tapped (a phone).
function rtkLine(li,d){var line=document.createElement('div');line.className='ortk';
var tags=[].map.call(li.querySelectorAll('.tag'),function(t){return t.textContent;}).filter(function(t){return t!==d;}),
shot=tags.filter(function(t){return/^[0-9]{2,4}[a-z]?$/.test(t);})[0],
meta=tags.concat([li.querySelector('.who').textContent]).join(' · ');
var b=add(line,'button','opill'+(li.querySelector('.type.team')?' team':''),shot?'RTK '+shot:'RTK');
b.type='button';b.title=meta;
var tx=add(line,'span','otx',li.querySelector('p').textContent);add(line,'small','ometa',meta);
b.addEventListener('click',function(){line.classList.toggle('open');});return line;}
function paintOne(){if(!one||one.hidden||!oneF||oneF==='#stats')return;var f=oneF,el=rows[f],
e=rv.files[f]||{deps:{},all:false,text:'',desc:null},shots=shotsOf(f);
one.querySelector('.ocard').classList.toggle('changed',el.classList.contains('rv-changed'));
if(!rvBuilt)return;  // a file's page, no review yet: nothing of it to show
one.querySelectorAll('.rvb').forEach(function(b){var twin=b.dataset.d?
el.querySelector('td[data-col="d:'+CSS.escape(b.dataset.d)+'"] .rvb.'+b.className.split(' ')[1]):
el.querySelector('.rvg .rvb.'+b.dataset.act);
if(twin){b.className=twin.className;b.setAttribute('aria-pressed',twin.getAttribute('aria-pressed'));}});
one.querySelectorAll('.ofl').forEach(function(box){var k=box.dataset.k,v=e.deps[k.slice(2)],
open=k==='g'?!el.querySelector('textarea.gen').hidden:!!(v&&v.no),o=splitText(k==='g'?e.text:(v&&v.text)||'',shots);
box.hidden=!open;box.querySelectorAll('.opair').forEach(function(pair){var t=pair.querySelector('.rvo'),
sh=pair.dataset.shot;if(t!==document.activeElement)t.value=(o[sh]||[]).join(NL);
pair.hidden=!!sh&&!t.value&&!oneOpen[k+' '+sh]&&t!==document.activeElement;grow(t);
var b=box.querySelector('.oshb button[data-shot="'+CSS.escape(sh)+'"]');if(b)b.hidden=!pair.hidden;});});
var dt=one.querySelector('textarea.rvdesc');dt.hidden=e.desc===null;
if(e.desc!==null&&dt!==document.activeElement)dt.value=e.desc;grow(dt);}
function step(n){if(oneF==='#stats')return n>0?ALL.filter(function(r){return!r.hidden;})[0]||null:null;
var i=ALL.indexOf(rows[oneF]);for(var j=i+n;j>=0&&j<ALL.length;j+=n)
if(!ALL[j].hidden)return ALL[j];return n<0?'#stats':null;}
function go(n){if(!n){setView(false);return;}var r=step(n);if(!r)return;openOne(r==='#stats'?r:r.dataset.file);
if(one.getBoundingClientRect().top<navTop)window.scrollBy(0,one.getBoundingClientRect().top-navTop-8);keepView();}
function keepView(){try{localStorage.setItem(rvKey+':view',JSON.stringify({one:!one.hidden,f:oneF}));}catch(e){}}
function setView(on){document.body.classList.toggle('one',on);one.hidden=!on;
$('view-one').setAttribute('aria-pressed',on);
$('rv-v-one').setAttribute('aria-pressed',on);$('rv-v-table').setAttribute('aria-pressed',!on);
if(on){var shown=ALL.filter(function(r){return!r.hidden;});
if(!oneF||!rows[oneF]&&oneF!=='#stats')oneF=(shown[0]||ALL[0]).dataset.file;openOne(oneF);
window.scrollBy(0,one.getBoundingClientRect().top-navTop-8);}
else{one.textContent='';if(oneF&&rows[oneF]){
var r=rows[oneF];setTimeout(function(){r.scrollIntoView({block:'center'});});}}
navHeight();keepView();size();}
one.addEventListener('click',function(ev){var b=ev.target.closest('[data-go]');if(b)go(+b.dataset.go);});
$('rv-v-one').addEventListener('click',function(){setView(true);});
$('rv-v-table').addEventListener('click',function(){setView(false);});
$('view-one').addEventListener('click',function(){setView(one.hidden);});
$('view-one').title+=' (Esc)';$('rv-v-one').title+=' (Esc)';$('rv-v-table').title='The table (Esc)';
$('f-closed').addEventListener('change',function(){if(!one.hidden)openOne(oneF);});
// Keys: ← → files, Esc table ⇄ one file; while reviewing V all done, X
// the general retake. Esc or Ctrl+Enter in a box just leaves it.
document.addEventListener('keydown',function(ev){
var t=ev.target;if(t.matches&&t.matches('input,textarea,select')){if(ev.key==='Escape'){t.blur();ev.preventDefault();}
else if(ev.key==='Enter'&&(ev.ctrlKey||ev.metaKey)){t.blur();ev.preventDefault();}return;}
if(ev.altKey||ev.ctrlKey||ev.metaKey)return;
if(one.hidden){if(ev.key==='Escape'){setView(true);ev.preventDefault();}return;}
var k=ev.key.toLowerCase(),rev=document.body.classList.contains('reviewing');
if(k==='arrowleft')go(-1);else if(k==='arrowright')go(1);else if(k==='escape')go(0);
else if(rev&&k==='v'){var a=one.querySelector('.orow .rvb.all');if(a&&!a.disabled)a.click();}
else if(rev&&k==='x'){var g=oneField('g');if(g&&!g.closest('.ofl').hidden)g.focus();
else{var gb=one.querySelector('.orow .rvb.gen');if(gb)gb.click();}}
else return;ev.preventDefault();});
try{var kept=JSON.parse(localStorage.getItem(rvKey)||'null');if(kept&&kept.files){rv=kept;
if(count()[0]){setMode(true);$('rv-saved').textContent='Your review in progress was restored';}}}catch(e){}
if(!rv.date)rv.date=new Date().toISOString().slice(0,10);fields();paint();
try{var vw=JSON.parse(localStorage.getItem(rvKey+':view')||'null');if(vw&&vw.one&&(rows[vw.f]||vw.f==='#stats')){
oneF=vw.f;setView(true);}}catch(e){}
// A phone opens on One file: the tables are no place to read there.
if(one.hidden&&window.innerWidth<700&&!location.hash){oneF='#stats';setView(true);}
})();
"""


# ---------------------------------------------------------------------------
# Review template (XLSX)
# ---------------------------------------------------------------------------

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
_REVIEW_HIDDEN = ("wip_version", "stable_version", "description_exported")
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
    by the top role at the stable shown), red-bordered with an open RTK."""
    state = item["departments"][department]
    key = "validated" if item.get("validated", {}).get(department) else state
    return _S_STATE[key] + (department in item["rtk_departments"])


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
            f'showErrorMessage="1" sqref="B4"><formula1>"{xml_escape(",".join(roles))}"'
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


# ---------------------------------------------------------------------------
# Review import (XLSX)
# ---------------------------------------------------------------------------

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
    "description"?, <department>: "ok" / "no" / retakes, "global"?}]}."""
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
        "columns": {k for row in rows for k in row},
        "rows": rows,
    }


def read_review(path: Path) -> dict:
    """A filled review: the snapshot page's .json, or the .xlsx template."""
    if Path(path).suffix.lower() == ".json":
        return read_review_json(path)
    return read_review_xlsx(path)


def read_review_xlsx(path: Path) -> dict:
    """{"schema_version", "author", "role", "review_date", "columns", "rows"}
    from a filled review template, every sheet's rows (v4: Shots, Assets)
    keyed by their own header row's names; Author, Review date and Role
    from the label cells above any header (v4: the front sheet)."""
    schema = None
    author = date = role = ""
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
_REVIEW_FIXED = {"group", "filename", "description", REVIEW_GLOBAL, *_REVIEW_HIDDEN}
_NOTE_PREFIX = re.compile(r"^note\s*:\s*", re.IGNORECASE)


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
        if column in _REVIEW_FIXED:
            continue
        choice = _cell_choice(value)
        if choice == "ok":
            wanted[column] = "yes"
        elif choice in ("no", "text"):
            wanted[column] = "no"  # a retake withdraws the validation
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
        (_NOTE_PREFIX.sub("", line), deps, "note")
        if _NOTE_PREFIX.match(line)
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
    confirm dialog: {"role", "author", "notes" (lines to import, duplicates
    included), "validations": [{"name", "filepath", "department",
    "approved", "stable"}], "refused": [(label, reason)]}. A template from
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
    }
    wanted_any = any(wanted or every for _, wanted, every, _ in actions)
    # Anything under the role: it must be one (descriptions don't need it).
    if schema >= 3 and (plan["notes"] or wanted_any):
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


def _note_key(text, shot, f_start, f_end, departments) -> tuple:
    """What makes an imported review line the same as one already there."""
    return (
        text,
        shot or None,
        f_start,
        f_end if f_start is not None else None,
        frozenset(d for d in departments or () if d),
    )


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
    Returns {"imported", "duplicates", "validated", "skipped": [(label, reason)]}."""
    review = read_review(path)
    plan = review_import_plan(path, review)
    role = plan["role"] or None
    author = review["author"] or "prod"
    date = review["review_date"]
    created_at = date.isoformat(timespec="seconds") if date else None
    review_id = hashlib.sha1(f"{now()}{Path(path).name}".encode()).hexdigest()[:5]
    result = {
        "imported": 0,
        "duplicates": 0,
        "validated": 0,
        "skipped": list(plan["refused"]),
    }
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
        known = {
            _note_key(
                e.get("text"),
                e.get("shot"),
                e.get("frame_start"),
                e.get("frame_end"),
                e.get("departments") or [e.get("department")],
            )
            for e in (read_json_quiet(tracking_json_path(filepath)) or {}).get(
                "entries", []
            )
            if e.get("source") == REVIEW_SOURCE and e.get("author") == author
        }
        shots = _file_shots(filepath)
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
            key = _note_key(
                line, shot, *(frames or (None, None)), departments
            )
            if key in known:
                result["duplicates"] += 1
                continue
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
                    referenced_version=str(filepath),
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
