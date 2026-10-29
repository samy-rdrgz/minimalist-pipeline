"""Production snapshot: one self-contained HTML page of the project's state
for people outside the studio, with a review spreadsheet embedded in it that
they fill in and send back (see NOTES.md, "Production snapshot")."""

import base64
import hashlib
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
    get_active_project_root,
    parse_filename,
    shots_in_segment,
    validation_roles,
)
from .core import json_get, now, read_json_quiet
from .errors import PipelineError
from .preview import latest_render_dir, render_root
from .thumbnails import (
    owner_shot_render_dirs,
    owner_thumbnail_dirs,
    run_thumbnail_jobs,
    thumbnail_jobs,
    thumbnail_path,
    thumbnail_size,
)
from .tracking import (
    APPROVAL_SOURCE,
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
SCHEMA_VERSION = 5  # 2: hidden description_exported column; 3: role, "valid <dept>"; 4: a sheet per section, a cell per department; 5: the render watched

ENTRY_TYPES = ("note", "todo", "rtk")

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


def _render_ref(renders: list, per_shot: bool = False) -> str:
    """The last render a review row was made on, as its "render" field:
    "v007-stable_001", or per shot when a block's differ (or per_shot) --
    "sh110=v007-stable_001 sh120=v006_002". "" if never rendered."""
    done = [r for r in renders if r.get("folder")]
    if len({r["folder"] for r in done}) == 1 and not per_shot:
        return done[0]["folder"]
    return " ".join(f"{r['shot']}={r['folder']}" for r in done)


def render_of_note(render: str, shot: str | None) -> str | None:
    """The render folder a review note is about, from its row's "render"
    (_render_ref()): its shot's ("110" matches "sh110"), else the row's
    one render; a note on the whole block, the newest of its shots'. None
    for a shot of a block with no render of its own there (never
    rendered, or rendered again after the snapshot), or without any (a
    review from before schema 5)."""
    default, per_shot = None, {}
    for token in (render or "").split():
        label, _, folder = token.rpartition("=")
        if label:
            digits = re.sub(r"\D", "", label)
            per_shot[int(digits) if digits else label] = folder
        else:
            default = folder
    if default:
        return default
    if shot is not None:
        return per_shot.get(int(shot)) if shot.isdigit() else None
    return max(per_shot.values(), key=_render_order, default=None)


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
            # assets/, library/ or shots/: the page's tab, the videos zip's folder.
            "root": next((p for p in reversed(owner.parts) if p in _DATA_ROOTS), kind),
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
        open_rtks = [
            e
            for t in open_threads
            for e in [t, *t["replies"]]
            if e["type"] == "rtk" and e["done"] is False
        ]
        rtk_departments = {d for e in open_rtks for d in e["departments"]}
        item["rtk_departments"] = sorted(rtk_departments)
        # On no department (a general retake): the "n RTK" flag by the name
        # is red-outlined; it weighs on every department's Done (_rtk_on()).
        item["general_rtk"] = any(not e["departments"] for e in open_rtks)
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
            d: _department_score(st, _rtk_on(item, d), weights)
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


def _rtk_on(item: dict, department: str) -> bool:
    """An open RTK on that department, or on none (a general retake)."""
    return department in item["rtk_departments"] or item.get("general_rtk", False)


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
        # The render a review note was written on (v007-stable_001).
        "render": e.get("render", ""),
        "shot": e.get("shot", ""),
        "frames": _frames_label(e),
        "done": e.get("done"),
        "from_review": e.get("source") == REVIEW_SOURCE,
        # The validation role it was written under, "" the team's own.
        "role": e.get("role") or "",
        # Written by a validation, for the record: no note to read.
        "approval": e.get("source") == APPROVAL_SOURCE,
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


def render_html(snapshot: dict) -> str:
    """The whole snapshot as one offline HTML page (lib/snapshot_page.py)."""
    from .snapshot_page import render_html as page  # it imports this module

    return page(snapshot)


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
# render: what the reviewer watched (_render_ref()) -- the notes' version.
_REVIEW_HIDDEN = ("wip_version", "stable_version", "description_exported", "render")
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
            _cell(f"{col['render']}{r}", _render_ref(item["renders"]), _S_LOCKED),
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
    "render"? (schema 5: _render_ref()), "description"?, <department>:
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


def read_review(path: Path) -> dict:
    """A filled review: the snapshot page's .json, or the .xlsx template."""
    if Path(path).suffix.lower() == ".json":
        return read_review_json(path)
    return read_review_xlsx(path)


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
    Returns {"imported", "duplicates", "validated", "skipped": [(label, reason)]}."""
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
        row_render = ""
        if filepath:
            row_render = row.get("render") or _render_at_snapshot(filepath, seen_at)
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
            key = _note_key(line, shot, *(frames or (None, None)), departments)
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
