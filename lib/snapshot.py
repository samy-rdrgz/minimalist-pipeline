"""Production snapshot: one self-contained HTML page of the project's state
for people outside the studio, with a review spreadsheet embedded in it that
they fill in and send back (see NOTES.md, "Production snapshot")."""

import base64
import hashlib
import html
import io
import os
import re
import threading
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from .core import json_get, now, read_json_quiet
from .errors import PipelineError
from .preview import latest_render_dir, render_root
from .tracking import (
    _DATA_ROOTS,
    _collect_folder,
    _pipeline_entries,
    _status_from_raw,
    _walk_owner_dirs,
    create_entry,
    find_file_by_name,
    owner_key,
    render_to_check_label,
    tracking_json_path,
    valid_department,
)
from .thumbnails import (
    owner_render_dir,
    run_thumbnail_jobs,
    thumbnail_jobs,
    thumbnail_path,
    thumbnail_size,
)

# Bumped whenever the review template's columns change -- the import refuses
# a template made by a newer addon.
SCHEMA_VERSION = 2  # 2: hidden description_exported column

ENTRY_TYPES = ("note", "todo", "rtk")

# Department state -> (label, css class). "rework" is validated at the last
# stable AND worked since: never shown as plain "validated".
STATES = {
    "done": ("Validated", "st-done"),
    "rework": ("Validated, reworked since", "st-rework"),
    "wip": ("Work in progress", "st-wip"),
    "todo": ("Not started", "st-todo"),
}
# What a table cell shows: six departments of full labels don't fit a page.
# The full label is its tooltip and in the legend.
SHORT_STATES = {"done": "Validated", "rework": "Reworked", "wip": "WIP", "todo": "Not started"}

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
    has several, anything else one): [{"shot", "file", "folder", "path"}],
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
    out = []
    for shot in shots:
        # A block's history holds every shot it rendered, told apart by
        # shot_override; a mono shot's or an asset's is all its own.
        mine = [
            i
            for i, e in enumerate(finished)
            if e.get("source_file") and (not block or e.get("shot_override") == shot)
        ]
        # An older version's entry (no source_file, no shot_override) after
        # it may be a newer render of this shot: the folder name knows.
        if mine and all(e.get("source_file") for e in finished[mine[-1] + 1 :]):
            last = finished[mine[-1]]
            output = last.get("output_path")
            folder = (Path(root) / output).parent if output else None
            out.append(
                {
                    "shot": shot,
                    "file": Path(last["source_file"]).name,
                    "folder": folder.name if folder else None,
                    "path": str(folder) if folder else None,
                }
            )
            continue
        latest = latest_render_dir(base.with_name(shot) if shot else base, v_prefix)
        out.append(
            {
                "shot": shot,
                "file": None,
                "folder": latest.name if latest else None,
                "path": str(latest) if latest else None,
            }
        )
    return out


def read_snapshot_data(
    root: Path, thumbnails: dict | None = None, v_prefix: str = "v"
) -> dict:
    """read_snapshot_raw() plus each folder's last render
    (read_render_state()) and thumbnails: those missing or older than
    their latest render are remade first (one headless Blender, waited on
    -- run this on a thread). thumbnails: {"size", "blender", "ffmpeg"},
    None to skip them. Returns {"raws", "renders": {owner:
    [...]}, "thumbs": {owner: base64 JPEG}, "thumb_warnings": [...]}."""
    raws = read_snapshot_raw(root)
    renders = {
        str(owner): read_render_state(root, kind, owner, v_prefix)
        for kind, owner, raw, _ in raws
        if not raw["tracking"].get("archived")
    }
    thumbs, warnings = {}, []
    if thumbnails is not None:
        dirs = {}
        for _, owner, raw, _ in raws:
            if not raw["tracking"].get("archived"):
                dirs[str(owner)] = owner_render_dir(root, owner)
        size = thumbnails.get("size") or thumbnail_size({})
        jobs = thumbnail_jobs(dirs.values(), v_prefix, size=size)
        results = run_thumbnail_jobs(
            jobs, thumbnails["blender"], thumbnails.get("ffmpeg"), size=size
        )
        for owner, d in dirs.items():
            dst = thumbnail_path(d)
            if results.get(str(dst), "ok") != "ok":
                warnings.append(f"{dst.name}: {results[str(dst)]}")
            try:  # an older thumbnail still beats none
                thumbs[owner] = base64.b64encode(dst.read_bytes()).decode("ascii")
            except OSError:
                pass
    return {
        "raws": raws,
        "renders": renders,
        "thumbs": thumbs,
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
            (int(m[1]), b)
            for b in blends
            if (m := version_re.search(b)) and not m[2]
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
            "stable_version": stable_name,
            # What the prod sees and what its notes get anchored on: the
            # most recent of the two (a stable can be newer than any wip).
            "current_version": wip_name if wip_n > stable_n else stable_name or wip_name,
            "thumbnail": data["thumbs"].get(str(owner)),
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
            e["department"]
            for t in open_threads
            for e in [t, *t["replies"]]
            if e["type"] == "rtk" and e["done"] is False
        }
        item["rtk_departments"] = sorted(rtk_departments)
        # Per department, then their mean: the footer averages the first.
        item["scores"] = {
            d: _department_score(st, d in rtk_departments, weights)
            for d, st in item["departments"].items()
        }
        scores = list(item["scores"].values())
        item["progress"] = sum(scores) / len(scores) if scores else None
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
    schedule = project_schedule(config)
    if schedule:
        today = datetime.fromisoformat(meta.get("scan_started_at") or now()).date()
        meta["schedule"] = {
            "start": schedule["start"].isoformat(),
            "end": schedule["end"].isoformat(),
            **schedule_progress(schedule, today),
        }
    meta["asset_departments"] = _columns(
        json_get(config, "assets_departments", []), items["asset"]
    )
    meta["shot_departments"] = _columns(
        json_get(config, "shots_departments", []), items["shot"]
    )
    return {"meta": meta, "assets": items["asset"], "shots": items["shot"], "notes": notes}


def collect_snapshot(
    root: Path, config: dict, meta: dict, thumbnails: dict | None = None
) -> dict:
    """read_snapshot_data() + build_snapshot() in one go (no thread)."""
    meta = {"scan_started_at": now(), **meta}
    v_prefix = json_get(config, "naming.version.prefix", "v")
    return build_snapshot(read_snapshot_data(root, thumbnails, v_prefix), config, meta)


def _department_state(status: dict, department: str) -> str:
    validated = department in status.get("validated_departments", {})
    worked = department in status.get("worked_departments", {})
    if validated:
        return "rework" if worked else "done"
    return "wip" if worked else "todo"


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


def department_progress(items: list, department: str) -> float | None:
    """Mean of one department over the items requiring it, None if none
    does -- the snapshot table's per-department footer."""
    values = [i["scores"][department] for i in items if department in i["scores"]]
    return sum(values) / len(values) if values else None


def average_progress(items: list) -> float | None:
    """Mean progress of items, each weighing the same; those without any
    required department left out. None if none is left."""
    values = [i["progress"] for i in items if i.get("progress") is not None]
    return sum(values) / len(values) if values else None


def parse_day(value: str) -> date:
    """A date typed day first -- 20/10/2026, 20-10-2026, 20.10.2026 -- or ISO
    (2026-10-20). Raises PipelineError otherwise."""
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise PipelineError(f"'{value}' is not a date (DD/MM/YYYY).")


def project_schedule(config: dict) -> dict | None:
    """The project's "snapshot.schedule" (Edit project) as dates: {"start",
    "end", "days_off"}. None unless start and end are both set, in order."""
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
    return {"start": start, "end": end, "days_off": days_off}


def working_days(start: date, end: date, days_off) -> int:
    """Monday to Friday from start to end, both included, days_off left out
    -- a spreadsheet's NETWORKDAYS(). 0 when end is before start."""
    count, day = 0, start
    while day <= end:
        if day.weekday() < 5 and day not in days_off:
            count += 1
        day += timedelta(days=1)
    return count


def schedule_progress(schedule: dict, today: date) -> dict:
    """Where the project should be on today at an even pace: {"expected"
    (0..1), "worked_days", "total_days"} -- worked days so far over the
    schedule's, today included."""
    total = working_days(schedule["start"], schedule["end"], schedule["days_off"])
    worked = working_days(
        schedule["start"], min(today, schedule["end"]), schedule["days_off"]
    )
    expected = worked / total if total else float(today >= schedule["end"])
    return {"expected": expected, "worked_days": worked, "total_days": total}


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
    version = e.get("referenced_version")
    return {
        "type": e.get("type", "note"),
        "text": e.get("text", ""),
        "author": e.get("author", ""),
        "date": e.get("created_at", ""),
        "department": e.get("department", ""),
        "version": Path(version).name if version else "",
        "shot": e.get("shot", ""),
        "done": e.get("done"),
        "from_review": e.get("source") == REVIEW_SOURCE,
    }


def _thread_closed(thread: dict) -> bool:
    """Done root and no reply still pending: what filter_review_boxes()'s
    hide_done drops (see its docstring)."""
    return thread["root"].get("done") is True and not any(
        r.get("done") is False for r in thread["replies"]
    )


def _thread_dict(item_name: str, thread: dict, closed: bool = False) -> dict:
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
    project = re.sub(r"[^\w\-]+", "_", meta.get("project") or "").strip("_") or "project"
    stamp = (meta.get("scan_started_at") or now())[:16].replace("T", "_").replace(":", "-")
    return f"{project}_{kind}_{stamp}.{ext}"


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def _e(value) -> str:
    return html.escape(str(value or ""), quote=True)


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
        + (f'<span class="muted">{_e(label)}</span>' if label != SHORT_STATES[k] else "")
        for k, (label, cls) in STATES.items()
    ) + (
        '<span class="pill st-none">Not required</span>'
        '<span class="pill st-done rtk-open">Validated, open RTK</span>'
        '<span class="pill behind">⚠ Render older than the stable</span>'
        '<span class="pill tocheck">to check</span>'
        '<span class="muted">not checked yet</span>'
        '<span class="pill farm-waiting">queued</span>'
        '<span class="pill farm-running">rendering 45/120</span>'
        '<span class="pill farm-failed">failed</span>'
        '<span class="muted">in the farm</span>'
    )

    body = [
        "<header>",
        f"<h1>{_e(meta.get('project'))}</h1>",
        '<dl class="meta">',
        f"<div><dt>Snapshot</dt><dd>{_e(scan_date)}</dd></div>",
        f"<div><dt>Exported by</dt><dd>{_e(meta.get('exported_by'))}</dd></div>",
        f"<div><dt>Addon</dt><dd>Minimalist Pipeline {_e(meta.get('addon_version'))}</dd></div>",
        "</dl>",
        '<div class="review">',
        f'<a class="btn" download="{_e(xlsx_name)}" '
        f'href="data:{XLSX_MIME};base64,\n{xlsx}\n">Download the review template (.xlsx)</a>',
        "<p>Fill in your name and the review date at the top, write your notes "
        "in the <b>text</b> column of each asset/shot — <b>one line per note</b>, "
        "Alt+Enter for the next one — pick a department and a type, then send "
        "the file back as is.</p>",
        "</div>",
        "</header>",
        _render_overview(snapshot),
        "<nav>",
        '<div class="links"><a href="#assets">Assets <span id="c-assets">'
        f'{len(snapshot["assets"])}</span></a><a href="#shots">Shots <span id="c-shots">'
        f'{len(snapshot["shots"])}</span></a><a href="#notes">Notes <span id="c-notes">'
        f'{sum(not n["closed"] for n in snapshot["notes"])}</span></a></div>',
        _render_filters(snapshot),
        "</nav>",
        f'<p class="legend">{legend}</p>',
        '<p class="legend muted">Done: each required department counts for an '
        f"equal share: work in progress {weights['wip']} %, validated but "
        f"reworked since {weights['rework']} %, validated with an open RTK "
        f"{weights['rtk']} %, validated 100 %. Totals and groups average "
        "their assets/shots.</p>",
        _render_table("assets", "Assets", snapshot["assets"], meta["asset_departments"]),
        _render_table("shots", "Shots", snapshot["shots"], meta["shot_departments"]),
        _render_notes(snapshot["notes"], snapshot["assets"] + snapshot["shots"]),
    ]
    title = f"{meta.get('project') or 'Project'} snapshot {scan_date[:10]}"
    # Hover shows a thumbnail at its own size (the project setting), from
    # its 112 px wide cell.
    zoom = max(1.0, round((meta.get("thumbnail_size") or 240) / 112, 2))
    # One element per line: readable/diffable raw source, same rendering.
    nl = "\n"
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title>\n<style>{_CSS}:root{{--thumb-zoom:{zoom}}}</style>\n</head>"
        f"<body>\n{nl.join(body)}\n<script>{_JS}</script>\n</body></html>\n"
    )


# Department states in the overview's stacked bar, most done first -- "todo"
# is drawn as the bar's bare track.
_STATE_ORDER = ("done", "rework", "wip", "todo")


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
    tiles = [
        _stat_tile(
            f"{title} done",
            _pct(meta["progress"][kind]),
            _schedule_delta(meta["progress"][kind], expected),
        )
        for kind, title, _, _, _ in sections
        if meta["progress"][kind] is not None
    ]
    if schedule:
        tiles.append(
            _stat_tile(
                f"Expected on {day}",
                _pct(expected),
                f'<span class="delta">{schedule["worked_days"]} of '
                f'{schedule["total_days"]} working days, {_day(schedule["start"])} '
                f'→ {_day(schedule["end"])}</span>',
            )
        )
    everything = snapshot["assets"] + snapshot["shots"]
    rtk = sum(i["open_rtk"] for i in everything)
    files = sum(1 for i in everything if i["open_rtk"])
    on_files = f'on {files} file{"" if files == 1 else "s"}'
    tiles.append(
        _stat_tile(
            "Open RTKs", str(rtk), f'<span class="delta">{on_files}</span>' if rtk else ""
        )
    )
    cards = "".join(
        _overview_card(title, by, noun, items, meta[f"{kind}_departments"], expected)
        for kind, title, by, noun, items in sections
    )
    if cards:
        cards = f'<div class="cards">{cards}</div>'
    return (
        f'<section id="overview"><h2>Progress<span class="sub">whole project on '
        f'{day}, filters aside</span></h2><div class="kpis">{"".join(tiles)}</div>'
        f"{cards}</section>"
    )


def _stat_tile(label: str, value: str, line: str = "") -> str:
    """One figure of the overview: its label, its value, then a line (HTML)."""
    return (
        f'<div class="kpi"><span class="kpi-label">{_e(label)}</span>'
        f'<span class="kpi-value">{_e(value)}</span>{line}</div>'
    )


def _schedule_delta(progress: float, expected: float | None) -> str:
    """A Done tile's line against the expected progress: points ahead or
    behind, then the pace (done / expected, a spreadsheet's "efficiency").
    Nothing without a schedule."""
    if expected is None:
        return ""
    gap = round((progress - expected) * 100)
    if gap > 0:
        cls, text = "ahead", f"▲ {gap} pts ahead of schedule"
    elif gap < 0:
        cls, text = "behind", f"▼ {-gap} pts behind schedule"
    else:
        cls, text = "", "on schedule"
    if expected > 0:
        text += f" · pace {round(progress / expected * 100)} %"
    return f'<span class="delta {cls}">{text}</span>'


def _overview_card(
    title: str, by: str, noun: str, items: list, columns: list, expected
) -> str:
    """One section's charts: its department tasks (item x required
    department) by state, its Done by group and by department. Nothing when
    none of its items requires a department."""
    states = [(i, d, st) for i in items for d, st in i["departments"].items()]
    if not states:
        return ""
    total = len(states)
    counts = {s: sum(1 for _, _, st in states if st == s) for s in _STATE_ORDER}
    rtk = sum(1 for i, d, st in states if st == "done" and d in i["rtk_departments"])
    # flex-grow, not a width: the 2px gaps come out of the bar, not on top.
    segments = "".join(
        f'<i class="s-{s}" style="flex:{counts[s]} 1 0" title="{_e(STATES[s][0])}: '
        f'{counts[s]} ({_pct(counts[s] / total)})"></i>'
        for s in _STATE_ORDER
        if counts[s]
    )
    legend = []
    for s in _STATE_ORDER:
        share = _pct(counts[s] / total)
        if s == "done" and rtk:
            share += f", {rtk} with an open RTK"
        legend.append(
            f'<span><i class="sw s-{s}"></i>{_e(SHORT_STATES[s])} <b>{counts[s]}</b> '
            f'<span class="muted">{share}</span></span>'
        )
    label = ", ".join(f"{SHORT_STATES[s]} {counts[s]}" for s in _STATE_ORDER)
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(item["group"], []).append(item)
    by_group = [
        (g, average_progress(m), f'{len(m)} {noun}{"" if len(m) == 1 else "s"}')
        for g, m in groups.items()
    ]
    by_department = [
        (c.capitalize(), department_progress(items, c), "") for c in columns
    ]
    key = (
        f'<p class="exp-key"><i></i>Expected at an even pace: {_pct(expected)}</p>'
        if expected is not None
        else ""
    )
    return (
        f'<div class="card"><h3>{_e(title)}<span class="muted">{len(items)} '
        f'{noun}{"" if len(items) == 1 else "s"}</span></h3><h4>State of the '
        f'{total} department task{"" if total == 1 else "s"}</h4>'
        f'<div class="stack" role="img" aria-label="{_e(label)}">{segments}</div>'
        f'<div class="slegend">{"".join(legend)}</div><div class="split">'
        f"<div><h4>{_e(by)}</h4>{_bar_list(by_group, expected)}</div>"
        f"<div><h4>By department</h4>{_bar_list(by_department, expected)}</div>"
        f"</div>{key}</div>"
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
        for label, items in (("Assets", snapshot["assets"]), ("Shots", snapshot["shots"]))
        if items
    )
    meta = snapshot["meta"]
    departments = dict.fromkeys(meta["asset_departments"] + meta["shot_departments"])
    states = "".join(
        f'<option value="{k}">{_e(label)}</option>' for k, (label, _) in STATES.items()
    )
    return (
        '<div class="filters">'
        '<input id="f-name" type="search" placeholder="Name…" aria-label="Filter by name">'
        f'<select id="f-group" aria-label="Group"><option value="">All groups</option>{groups}</select>'
        '<select id="f-dep" aria-label="Department"><option value="">Any department</option>'
        f"{options(departments)}</select>"
        f'<select id="f-state" aria-label="State"><option value="">Any state</option>{states}</select>'
        '<label><input id="f-rtk" type="checkbox"> Open RTK</label>'
        '<label><input id="f-notes" type="checkbox"> Has open notes</label>'
        '<label title="In the farm, or rendered and not checked yet">'
        '<input id="f-farm" type="checkbox"> Farm</label>'
        '<label title="Done todos/RTKs, kept in the snapshot but hidden">'
        '<input id="f-closed" type="checkbox"> Show closed</label>'
        '<button id="f-reset" type="button">Reset</button>'
        f"{_columns_menu(departments)}"
        "</div>"
    )


def _columns_menu(departments) -> str:
    """ "Columns" drop-down: a checkbox per column that can be hidden (_JS
    hides every cell whose data-col is its data-key; the choice is kept
    per browser)."""
    columns = [("thumb", "Thumbnail"), ("file", "Blender file"), ("render", "Last render")]
    columns += [(f"d:{d}", d.capitalize()) for d in departments]
    columns.append(("done", "Done"))
    boxes = "".join(
        f'<label><input type="checkbox" data-key="{_e(key)}" checked> {_e(label)}</label>'
        for key, label in columns
    )
    return f'<details class="cols"><summary>Columns</summary><div>{boxes}</div></details>'



def _slug(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name)


def _item_attrs(item: dict) -> str:
    """data-* the filter script matches on -- same for a row and its notes card."""
    states = " ".join(f"{d}:{st}" for d, st in item["departments"].items())
    return (
        f'data-name="{_e(item["name"].lower())}" data-group="{_e(item["group"])}" '
        f'data-states="{_e(states)}" data-rtk="{item["open_rtk"]}" '
        f'data-notes="{item["open_notes"]}" '
        f'data-farm="{int(bool(item.get("farm") or item.get("to_check")))}"'
    )


def _render_table(anchor: str, title: str, items: list, columns: list) -> str:
    nl = "\n"
    if not items:
        return (
            f'<section id="{anchor}"><h2>{title}</h2>'
            '<p class="empty">Nothing tracked yet.</p></section>'
        )
    title += f' <span class="pct">{_pct(average_progress(items))} done</span>'
    with_thumbs = any(i.get("thumbnail") for i in items)
    head = (
        ('<th data-col="thumb"></th>' if with_thumbs else "")
        + "<th>Name</th>"
        + '<th data-col="file" title="Latest work-in-progress and stable versions '
        'of the .blend">Blender file</th>'
        + '<th data-col="render" title="Output folder of the last render: vXXX_YYY, '
        "XXX the Blender file version rendered, YYY the render increment -- then "
        'its farm state">Last render</th>'
        + "".join(f'<th data-col="d:{_e(c)}">{_e(c.capitalize())}</th>' for c in columns)
        + '<th data-col="done" title="Share of the required departments done '
        '(see the legend)">Done</th>'
    )
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(item["group"], []).append(item)
    rows = []
    group = None
    for item in items:
        if item["group"] != group:
            group = item["group"]
            done = _pct(average_progress(groups[group]))
            rows.append(
                f'<tr class="group" data-group="{_e(group)}">'
                f'<th colspan="{len(columns) + 4 + with_thumbs}">{_e(group)}'
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
                if state == "done" and c in item["rtk_departments"]:
                    # Validated, then sent back: the RTK is the news.
                    cls += " rtk-open"
                    label = "Validated, then an RTK was opened on it"
                cells.append(
                    f'<td data-col="d:{_e(c)}"><span class="pill {cls}" title="{_e(label)}">'
                    f"{_e(SHORT_STATES[state])}</span></td>"
                )
        versions = " · ".join(
            label + _short_version(item["name"], v)
            for label, v in (("wip ", item["wip_version"]), ("stable ", item["stable_version"]))
            if v
        )
        flags = (
            f'<span class="flag">{item["open_rtk"]} RTK</span>' if item["open_rtk"] else ""
        )
        n = item["open_notes"]
        jump = (
            f'<a class="jump" href="#n-{_e(_slug(item["name"]))}">'
            f'{n} note{"" if n == 1 else "s"} ↓</a>'
            if n
            else ""
        )
        thumb = ""
        if with_thumbs:
            thumb = (
                f'<td class="th" data-col="thumb"><img class="thumb" alt="" '
                f'src="data:image/jpeg;base64,{item["thumbnail"]}"></td>'
                if item.get("thumbnail")
                else '<td class="th" data-col="thumb"><div class="nothumb"></div></td>'
            )
        rows.append(
            f'<tr class="item" id="i-{_e(_slug(item["name"]))}" {_item_attrs(item)}>'
            f'{thumb}<td class="name"><b>{_e(item["name"])}</b>{flags}{jump}'
            f'<small>{_e(item["description"])}</small></td>'
            f'<td class="ver" data-col="file">{_e(versions)}</td>'
            f'<td class="ver" data-col="render">{_render_cell(item)}</td>{"".join(cells)}'
            f'<td class="done" data-col="done">{_progress_cell(item["progress"])}</td></tr>'
        )
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
    )
    return (
        f'<section id="{anchor}"><h2>{title}</h2>'
        '<p class="empty nomatch" hidden>Nothing matches the filters.</p>'
        '<div class="scroll"><table>'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>\n{nl.join(rows)}\n</tbody>"
        f'<tfoot title="Whole section, filters aside"><tr>{foot}</tr></tfoot>'
        "</table></div></section>"
    )


def _progress_cell(progress: float | None) -> str:
    """ "Done" cell: a bar and its percentage, "–" without any required
    department."""
    if progress is None:
        return '<span class="na" title="No department required">–</span>'
    width = round(progress * 100)
    return f'<span class="bar"><i style="width:{width}%"></i></span>{width} %'


def _render_cell(item: dict) -> str:
    """ "Last render" cell, one line per render: its status pill on the left
    -- so every status lines up down the table -- then its output folder,
    vXXX_YYY (XXX the .blend version rendered, YYY the render increment),
    in red when XXX is older than the last stable. Pills: "to check" until
    the team checked it, then the farm's (_farm_pill()) for the jobs still
    in it -- on their render's line when it's already listed. One line per
    shot when a block's shots differ. "not rendered" for a shot never
    rendered, nothing for an asset never rendered (most never are)."""
    renders = item.get("renders") or []
    to_check = list(item.get("to_check") or [])
    # [labels, pill, text, shot of a "not rendered" line]: labels as
    # render_to_check_label()'s.
    rows = []
    if any(r["folder"] for r in renders):
        stable = _short_version(item["name"], item["stable_version"] or "")
        same = len({r["folder"] for r in renders}) == 1
        block = len(renders) > 1  # a mono shot's labels carry no shot
        for r in renders[:1] if same else renders:
            shot = "" if same else f'<span class="shot">{_e(r["shot"])}</span> '
            labels = {
                f"{x['shot'] if block else ''} {x['folder']}".strip()
                for x in (renders if same else [r])
            }
            if not r["folder"]:
                text = f'{shot}<span class="norender">not rendered</span>'
                rows.append([labels, "", text, r["shot"] if block else ""])
                continue
            if r["file_number"] is not None and r["file_number"] < item["stable_number"]:
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
        + "".join(f"<span>{pill}</span><span>{text}</span>" for _, pill, text, _ in rows)
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
    """"ch_bob_v004-stable.blend" -> "v004" (the stable label says the rest)."""
    stem = filename[: -len(".blend")] if filename.endswith(".blend") else filename
    stem = stem[len(name) + 1 :] if stem.startswith(name + "_") else stem
    return stem.split("-", 1)[0]


def _render_entry(e: dict, reply: bool = False, closed: bool = False) -> str:
    if e["done"] is True:
        # The type's own pill, green and ticked like "Validated" -- a
        # separate "done" tag read like one more department.
        tags = [f'<span class="type t-done" title="Done">✓ {_e(e["type"])}</span>']
    else:
        tags = [f'<span class="type t-{_e(e["type"])}">{_e(e["type"])}</span>']
    if e["from_review"]:
        tags.append('<span class="tag">prod review</span>')
    for key in ("department", "shot", "version"):
        if e[key]:
            tags.append(f'<span class="tag">{_e(e[key])}</span>')
    who = f'{_e(e["author"])} · {_e(e["date"][:10])}'
    cls = ("reply" if reply else "root") + (" closed" if closed else "")
    return (
        f'<li class="{cls}"><div class="head">'
        f'{"".join(tags)}<span class="who">{who}</span></div>'
        f'<p>{_e(e["text"])}</p></li>'
    )


def _render_notes(notes: list, items: list) -> str:
    if not notes:
        return (
            '<section id="notes"><h2>Notes</h2>'
            '<p class="empty">No notes.</p></section>'
        )
    attrs = {i["name"]: _item_attrs(i) for i in items}
    by_item: dict[str, list] = {}
    for n in notes:
        by_item.setdefault(n["item"], []).append(n)
    cards = []
    for name, threads in by_item.items():
        threads = sorted(threads, key=lambda t: t["last_activity"], reverse=True)
        lis = "\n".join(
            "\n".join(
                [_render_entry(t, closed=t["closed"])]
                + [_render_entry(r, True, t["closed"]) for r in t["replies"]]
            )
            for t in threads
        )
        slug = _e(_slug(name))
        open_count = sum(not t["closed"] for t in threads)
        cards.append(
            f'<article class="item" id="n-{slug}" data-threads="{len(threads)}" '
            f'data-open="{open_count}" {attrs.get(name, "")}><h3>{_e(name)}'
            f'<a class="back" href="#i-{slug}" title="Back to its row">↑</a></h3>'
            f"<ul>\n{lis}\n</ul></article>"
        )
    return (
        '<section id="notes"><h2>Notes</h2>'
        '<p class="empty nomatch" hidden>Nothing matches the filters '
        '(closed notes are hidden: tick "Show closed").</p>'
        + "\n".join(cards)
        + "</section>"
    )


_CSS = """
:root{--page:1600px;--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e2e1dc;
--accent:#3d5afe;--done:#2e7d32;--done-bg:#e3f2e4;--wip:#8a5a00;--wip-bg:#fff1d6;
--todo:#6b6b66;--rtk:#c62828;--rtk-bg:#fde7e7;color-scheme:light dark;
--g-rework:#4f9a54;--g-wip:#76b87a;--track:color-mix(in srgb,var(--done) 16%,var(--card))}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;
--fg:#ecebe6;--muted:#a3a29c;--card:#20201e;--line:#34332f;--accent:#8c9eff;
--done:#81c784;--done-bg:#1d3320;--wip:#ffcc80;--wip-bg:#3a2c12;--todo:#a3a29c;
--rtk:#ef9a9a;--rtk-bg:#3a1c1c;--g-rework:#5ea463;--g-wip:#3f8245;
--track:color-mix(in srgb,var(--done) 16%,var(--card))}}
:root[data-theme="dark"]{--bg:#161615;--fg:#ecebe6;--muted:#a3a29c;--card:#20201e;
--line:#34332f;--accent:#8c9eff;--done:#81c784;--done-bg:#1d3320;--wip:#ffcc80;
--wip-bg:#3a2c12;--todo:#a3a29c;--rtk:#ef9a9a;--rtk-bg:#3a1c1c;--g-rework:#5ea463;
--g-wip:#3f8245;--track:color-mix(in srgb,var(--done) 16%,var(--card))}
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
padding:14px 16px}
.review p{margin:8px 0 0;color:var(--muted)}
.btn{display:inline-block;background:var(--accent);color:#fff;padding:8px 14px;
border-radius:7px;text-decoration:none;font-weight:600}
nav{z-index:2;display:flex;flex-direction:column;gap:8px;margin-top:20px;
padding:10px max(16px,calc((100% - var(--page))/2 + 16px));
background:var(--bg);border-bottom:1px solid var(--line)}
@media (min-width:700px){nav{position:sticky;top:0}}
.links,.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.links a{color:var(--fg);text-decoration:none;padding:4px 10px;border-radius:6px;
border:1px solid var(--line);background:var(--card)}
.links a span{color:var(--muted);margin-left:4px}
.filters input[type=search],.filters select,.filters button{font:inherit;min-width:0;
padding:4px 8px;border-radius:6px;border:1px solid var(--line);background:var(--card);
color:var(--fg)}
.filters input[type=search]{flex:0 1 180px}
.filters label{display:flex;gap:4px;align-items:center;color:var(--muted);white-space:nowrap}
.filters button{cursor:pointer;color:var(--muted)}
.cols{position:relative}
.cols summary{cursor:pointer;color:var(--muted);padding:4px 8px;border:1px solid var(--line);
border-radius:6px;background:var(--card);list-style:none}
.cols summary::-webkit-details-marker{display:none}
.cols summary::after{content:" ▾"}
.cols div{position:absolute;right:0;z-index:4;margin-top:4px;padding:8px 12px;display:grid;gap:4px;
background:var(--card);border:1px solid var(--line);border-radius:8px;
box-shadow:0 4px 18px rgba(0,0,0,.18)}
.cols.hiding summary{color:var(--accent);border-color:var(--accent)}
.legend .muted{color:var(--muted);font-size:12px;margin:0 8px 0 -2px;align-self:center}
.filters.active button{color:var(--accent);border-color:var(--accent)}
[id]{scroll-margin-top:var(--nav-h,16px)}
tr:target td{background:color-mix(in srgb,var(--accent) 12%,transparent)}
article:target{outline:2px solid var(--accent);outline-offset:-1px}
.jump{display:inline-block;margin-left:8px;font-size:11px;color:var(--accent);
text-decoration:none;white-space:nowrap}
.jump:hover,.back:hover{text-decoration:underline}
.back{margin-left:8px;font-weight:400;color:var(--accent);text-decoration:none}
.legend{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.scroll{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%}
th,td{padding:6px 8px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
table{font-size:13px}
thead th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr.group th{background:var(--bg);font-size:12px;color:var(--muted)}
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
.legend.muted{color:var(--muted);font-size:12px}
td.done{white-space:nowrap}
body:not(.show-closed) li.closed{display:none}
li.closed{opacity:.6}
tfoot td{border-top:2px solid var(--line);font-weight:600}
.bar{display:inline-block;width:56px;height:6px;margin-right:6px;vertical-align:middle;
border-radius:3px;background:var(--line);overflow:hidden}
.bar i{display:block;height:100%;background:var(--done)}
td.ver .shot{font-weight:600}
td.th{width:1px;padding-right:0}
/* Any aspect ratio: shown whole inside a fixed box, never cropped. */
.thumb{display:block;width:112px;height:63px;object-fit:contain;border-radius:4px;
background:var(--bg);transition:transform .15s}
.nothumb{width:112px}
img.thumb:hover{transform:scale(var(--thumb-zoom,2.4));transform-origin:left top;position:relative;
z-index:3;box-shadow:0 4px 18px rgba(0,0,0,.35)}
.flag{margin-left:8px;font-size:11px;font-weight:600;color:var(--rtk);
background:var(--rtk-bg);padding:1px 6px;border-radius:999px}
article{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px 16px;margin-bottom:12px}
article ul{list-style:none;margin:0;padding:0}
article li{padding:8px 0;border-top:1px solid var(--line)}
article li.reply{margin-left:24px}
article li p{margin:4px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}
.head{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.who{margin-left:auto;color:var(--muted);font-size:12px}
.type,.tag{font-size:11px;padding:1px 7px;border-radius:999px;border:1px solid var(--line)}
.type{font-weight:600;text-transform:uppercase}
.t-rtk{color:var(--rtk);background:var(--rtk-bg);border-color:transparent}
.t-todo{color:var(--wip);background:var(--wip-bg);border-color:transparent}
.t-done{color:var(--done);background:var(--done-bg);border-color:transparent}
.empty{color:var(--muted)}
section:last-of-type{padding-bottom:40px}
/* Overview: the departments' states are an ordinal green ramp (validated
darkest; dark mode flips it), not started the bare track. */
#overview h2 .sub,.card h3 .muted{margin-left:8px;font-size:12px;font-weight:400;
color:var(--muted)}
.kpis{display:flex;flex-wrap:wrap;gap:12px}
.kpi{flex:1 1 200px;display:flex;flex-direction:column;gap:2px;background:var(--card);
border:1px solid var(--line);border-radius:10px;padding:12px 16px}
.kpi-label{font-size:12px;color:var(--muted)}
.kpi-value{font-size:28px;font-weight:600;line-height:1.2}
.delta{font-size:12px;color:var(--muted)}
.delta.ahead{color:var(--done)}.delta.behind{color:var(--rtk)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));
gap:12px;margin-top:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px 16px}
.card h4{margin:14px 0 8px;font-size:12px;font-weight:600;color:var(--muted);
text-transform:uppercase;letter-spacing:.04em}
.stack{display:flex;gap:2px;height:16px}
.stack i{min-width:2px}.stack i:last-child{border-radius:0 4px 4px 0}
.s-done{background:var(--done)}.s-rework{background:var(--g-rework)}
.s-wip{background:var(--g-wip)}.s-todo{background:var(--track)}
.slegend{display:flex;flex-wrap:wrap;gap:4px 16px;margin-top:8px;font-size:12px}
.slegend .muted{color:var(--muted)}
.sw{display:inline-block;width:10px;height:10px;margin-right:6px;border-radius:2px;
vertical-align:-1px}
.split{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));
gap:0 24px}
.bars{display:grid;grid-template-columns:max-content minmax(60px,1fr) max-content;
gap:6px 10px;align-items:center;font-size:12px}
.bl small{margin-left:6px;color:var(--muted)}
.bt{position:relative;height:10px;background:var(--track);border-radius:0 4px 4px 0}
.bt .f{display:block;height:100%;background:var(--done);border-radius:0 4px 4px 0}
.bt .exp{position:absolute;top:-3px;bottom:-3px;width:2px;margin-left:-1px;
background:var(--fg);opacity:.55;border-radius:1px}
.bv{text-align:right;font-variant-numeric:tabular-nums}
.exp-key{margin:12px 0 0;font-size:12px;color:var(--muted)}
.exp-key i{display:inline-block;width:2px;height:12px;margin-right:6px;
background:var(--fg);opacity:.55;vertical-align:-2px}
@media print{nav,.review,.jump,.back{display:none}.scroll{overflow:visible}}
"""

_JS = """
(function(){
var $=function(id){return document.getElementById(id);};
var nav=document.querySelector('nav'),bar=document.querySelector('.filters');
var ctl=['f-name','f-group','f-dep','f-state','f-rtk','f-notes','f-closed','f-farm'].map($);
function navHeight(){var sticky=getComputedStyle(nav).position==='sticky';
document.documentElement.style.setProperty('--nav-h',
(sticky?nav.offsetHeight:0)+16+'px');}
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
var on=ctl.some(function(c){return c.type==='checkbox'?c.checked:c.value;});
bar.classList.toggle('active',on);
var closed=ctl[6].checked;document.body.classList.toggle('show-closed',closed);
['assets','shots','notes'].forEach(function(id){
var sec=$(id),n=0,items=sec.querySelectorAll('.item');
items.forEach(function(el){var notes=id==='notes';
el.hidden=!match(el)||(notes&&!closed&&el.dataset.open==='0');
if(!el.hidden)n+=notes?+(closed?el.dataset.threads:el.dataset.open):1;});
sec.querySelectorAll('tr.group').forEach(function(row){
var next=row.nextElementSibling,any=false;
while(next&&!next.classList.contains('group')){if(!next.hidden)any=true;
next=next.nextElementSibling;}row.hidden=!any;});
var none=sec.querySelector('.nomatch'),table=sec.querySelector('.scroll');
if(none)none.hidden=!items.length||n>0;if(table)table.hidden=items.length&&!n;
$('c-'+id).textContent=n;});}
ctl.forEach(function(c){c.addEventListener('input',apply);
c.addEventListener('change',apply);});
$('f-reset').addEventListener('click',function(){ctl.forEach(function(c){
if(c.type==='checkbox')c.checked=false;else c.value='';});apply();});
var cols=[].slice.call(document.querySelectorAll('.cols input')),
colStyle=document.createElement('style'),colKey='mp-snapshot-hidden-cols';
document.head.appendChild(colStyle);
function applyCols(save){var hidden=cols.filter(function(c){return!c.checked;})
.map(function(c){return c.dataset.key;});
colStyle.textContent=hidden.map(function(k){
return '[data-col="'+CSS.escape(k)+'"]{display:none}';}).join('');
document.querySelector('.cols').classList.toggle('hiding',hidden.length>0);
if(save){try{localStorage.setItem(colKey,JSON.stringify(hidden));}catch(e){}}}
try{var saved=JSON.parse(localStorage.getItem(colKey)||'[]');
cols.forEach(function(c){if(saved.indexOf(c.dataset.key)>=0)c.checked=false;});}catch(e){}
cols.forEach(function(c){c.addEventListener('change',function(){applyCols(true);});});
applyCols(false);
var menu=document.querySelector('.cols');
document.addEventListener('click',function(e){if(!menu.contains(e.target))menu.open=false;});
window.addEventListener('resize',navHeight);navHeight();apply();
})();
"""


# ---------------------------------------------------------------------------
# Review template (XLSX)
# ---------------------------------------------------------------------------

# Columns of the review sheet, in order. Hidden ones are written by the
# addon for the import, never meant to be edited.
_REVIEW_COLUMNS = (
    # (header, width, hidden)
    ("group", 13, False),
    ("filename", 30, False),
    ("description", 30, False),
    ("department", 14, False),
    ("type", 8, False),
    ("shot", 8, False),
    ("text", 70, False),
    ("wip_version", 10, True),
    ("stable_version", 10, True),
    # The description as exported: a cell differing from it is the prod's
    # edit; one equal to it is no change, even if the file's moved on since.
    ("description_exported", 30, True),
)
_COL = {h: chr(65 + i) for i, (h, _, _) in enumerate(_REVIEW_COLUMNS)}
_HEADER_ROW = 6
_META_COL = chr(65 + len(_REVIEW_COLUMNS))  # hidden cell holding schema_version=N

# cellXfs indexes in _STYLES_XML
_S_TITLE, _S_LABEL, _S_HINT, _S_HEADER, _S_LOCKED = 1, 2, 3, 4, 5
# 6: locked and muted, the description's until it became editable -- kept
# in _STYLES_XML so the indexes below don't move.
_S_INPUT, _S_INPUT_DATE, _S_INPUT_TEXT, _S_GROUP = 7, 8, 9, 10

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
    if value in (None, ""):
        return f'<c r="{ref}" s="{style}"/>'
    text = xml_escape(_XML_ILLEGAL.sub("", str(value)))
    return (
        f'<c r="{ref}" s="{style}" t="inlineStr">'
        f'<is><t xml:space="preserve">{text}</t></is></c>'
    )


def _stem(filename: str | None) -> str | None:
    """"ch_bob_v004.blend" -> "ch_bob_v004" (the import adds .blend back)."""
    return filename[: -len(".blend")] if filename and filename.endswith(".blend") else filename


def render_review_xlsx(snapshot: dict) -> bytes:
    """Review template: one row per asset/shot, grouped by prefix/sequence
    in a merged left column, filename and known versions locked in,
    description editable (imported, see review_description_changes()),
    department/type dropdowns, Author/Review date at the top."""
    meta = snapshot["meta"]
    items = snapshot["assets"] + snapshot["shots"]
    first = _HEADER_ROW + 1
    last = _HEADER_ROW + max(1, len(items))

    title = f"{meta.get('project') or ''} review".strip()
    scan_date = (meta.get("scan_started_at") or "").replace("T", " ")
    intro = (
        f"Snapshot of {scan_date}. Write in the white cells. One line of text "
        "= one note (Alt+Enter for the next one); rows with an empty text are "
        "ignored. Edit a description to change it."
    )
    rows = [
        '<row r="1">'
        + _cell("A1", title, _S_TITLE)
        + _cell(f"{_META_COL}1", f"schema_version={SCHEMA_VERSION}")
        + "</row>",
        '<row r="2">'
        + _cell("A2", "Author", _S_LABEL)
        + _cell("B2", "", _S_INPUT)
        + _cell("C2", 'Empty: "prod"', _S_HINT)
        + "</row>",
        '<row r="3">'
        + _cell("A3", "Review date", _S_LABEL)
        + _cell("B3", "", _S_INPUT_DATE)
        + _cell("C3", "Empty: the day the file is imported", _S_HINT)
        + "</row>",
        '<row r="4">' + _cell("A4", intro, _S_HINT) + "</row>",
        f'<row r="{_HEADER_ROW}">'
        + "".join(
            _cell(f"{_COL[h]}{_HEADER_ROW}", h, _S_HEADER) for h, _, _ in _REVIEW_COLUMNS
        )
        + "</row>",
    ]
    styles = {
        "group": _S_GROUP,
        "filename": _S_LOCKED,
        "description": _S_INPUT,  # edits are imported (confirm dialog)
        "department": _S_INPUT,
        "type": _S_INPUT,
        "shot": _S_INPUT_TEXT,
        "text": _S_INPUT,
        "wip_version": _S_LOCKED,
        "stable_version": _S_LOCKED,
        "description_exported": _S_LOCKED,
    }
    dep_lists: dict[str, list[str]] = {}
    merges = []
    group_start = None
    for n, item in enumerate(items):
        r = first + n
        new_group = n == 0 or item["group"] != items[n - 1]["group"]
        if new_group:
            if group_start is not None and r - 1 > group_start:
                merges.append(f"A{group_start}:A{r - 1}")
            group_start = r
        values = {
            # Only the merge's top cell holds the value.
            "group": item["group"] if new_group else None,
            "filename": _stem(item["current_version"]) or item["name"],
            "description": item["description"],
            "type": "rtk",
            "wip_version": _stem(item["wip_version"]),
            "stable_version": _stem(item["stable_version"]),
            "description_exported": item["description"],
        }
        cells = "".join(
            _cell(f"{_COL[h]}{r}", values.get(h), styles[h]) for h, _, _ in _REVIEW_COLUMNS
        )
        rows.append(f'<row r="{r}">{cells}</row>')
        deps = ",".join(item["departments_required"])
        if deps and len(deps) <= 255:  # Excel's inline list limit
            dep_lists.setdefault(deps, []).append(f"{_COL['department']}{r}")
    if group_start is not None and last > group_start:
        merges.append(f"A{group_start}:A{last}")

    t = _COL["type"]
    validations = [
        f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" '
        f'sqref="{t}{first}:{t}{last}"><formula1>"{",".join(ENTRY_TYPES)}"</formula1>'
        "</dataValidation>"
    ] + [
        f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" '
        f'sqref="{" ".join(refs)}"><formula1>"{xml_escape(deps)}"</formula1>'
        "</dataValidation>"
        for deps, refs in dep_lists.items()
    ]
    cols = "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"'
        + (' hidden="1"' if hidden else "")
        + "/>"
        for i, (_, w, hidden) in enumerate(_REVIEW_COLUMNS)
    )
    meta_n = len(_REVIEW_COLUMNS) + 1
    cols += f'<col min="{meta_n}" max="{meta_n}" width="8" hidden="1"/>'
    filter_ref = f"A{_HEADER_ROW}:{_COL['text']}{last}"
    merge_xml = (
        f'<mergeCells count="{len(merges)}">'
        + "".join(f'<mergeCell ref="{m}"/>' for m in merges)
        + "</mergeCells>"
        if merges
        else ""
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'
        f'<dimension ref="A1:{_META_COL}{last}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        f'<pane ySplit="{_HEADER_ROW}" topLeftCell="A{first}" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="B2" sqref="B2"/>'
        "</sheetView></sheetViews>"
        f"<cols>{cols}</cols>"
        f"<sheetData>{''.join(rows)}</sheetData>"
        # No password: this only stops accidental edits of the locked columns.
        '<sheetProtection sheet="1" objects="1" scenarios="1" formatCells="0" '
        'formatColumns="0" formatRows="0" autoFilter="0"/>'
        f'<autoFilter ref="{filter_ref}"/>'
        f"{merge_xml}"
        f'<dataValidations count="{len(validations)}">{"".join(validations)}</dataValidations>'
        '<pageMargins left="0.5" right="0.5" top="0.5" bottom="0.5" header="0.3" footer="0.3"/>'
        # Printed landscape, one page wide.
        '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>'
        "</worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Review" sheetId="1" r:id="rId1"/></sheets>'
        '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" '
        f'hidden="1">Review!$A${_HEADER_ROW}:${_COL["text"]}${last}</definedName></definedNames>'
        "</workbook>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        z.writestr("_rels/.rels", _RELS_XML)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS_XML)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/styles.xml", _STYLES_XML)
    return buf.getvalue()


_CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    "</Types>"
)
_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)
_WORKBOOK_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)
# One font, one size: weight and grey only. Grey fill = locked, white =
# to fill in. cellXfs: 0 default, 1 title, 2 label, 3 hint, 4 header,
# 5 locked, 6 locked muted, 7 input, 8 input date, 9 input text-format
# (keeps "045" a string), 10 group (merged left column).
_UNLOCK = '<protection locked="0"/>'
_TOP = '<alignment vertical="top"/>'
_TOP_WRAP = '<alignment vertical="top" wrapText="1"/>'
_STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/></numFmts>'
    '<fonts count="3">'
    '<font><sz val="11"/><color rgb="FF1F2328"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><color rgb="FF1F2328"/><name val="Calibri"/></font>'
    '<font><sz val="11"/><color rgb="FF6E7781"/><name val="Calibri"/></font>'
    "</fonts>"
    '<fills count="5">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFDDE3EA"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFF3F4F6"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFE9EDF2"/></patternFill></fill>'
    "</fills>"
    '<borders count="2"><border/>'
    '<border><left style="thin"><color rgb="FFC8CED6"/></left><right style="thin"><color rgb="FFC8CED6"/></right>'
    '<top style="thin"><color rgb="FFC8CED6"/></top><bottom style="thin"><color rgb="FFC8CED6"/></bottom></border>'
    "</borders>"
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="11">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>'
    f'<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1">{_TOP}</xf>'
    f'<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">{_TOP_WRAP}</xf>'
    f'<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1" applyProtection="1">{_TOP_WRAP}{_UNLOCK}</xf>'
    f'<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1" applyProtection="1"><alignment horizontal="left"/>{_UNLOCK}</xf>'
    f'<xf numFmtId="49" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1" applyProtection="1">{_TOP}{_UNLOCK}</xf>'
    '<xf numFmtId="0" fontId="1" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
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


def _first_sheet_path(z: zipfile.ZipFile) -> str:
    """Zip path of the workbook's first sheet (not always sheet1.xml once
    a spreadsheet app has re-saved it)."""
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rid = wb.find(f"{_NS}sheets/{_NS}sheet").get(f"{_REL_NS}id")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        for rel in rels.iter(f"{_PKG_REL_NS}Relationship"):
            if rel.get("Id") == rid:
                target = rel.get("Target")
                return target.lstrip("/") if target.startswith("/") else f"xl/{target}"
    except (KeyError, AttributeError, ET.ParseError):
        pass
    return "xl/worksheets/sheet1.xml"


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


def read_xlsx_grid(path: Path) -> dict[int, dict[str, str]]:
    """First sheet of an .xlsx as {row number: {column letters: text}}.
    Text cells resolved through sharedStrings (t="s") or inline; numbers
    (dates included) kept as their raw text."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            shared = []
            if "xl/sharedStrings.xml" in names:
                sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
                shared = [_string_item(si) for si in sst.iter(f"{_NS}si")]
            sheet = ET.fromstring(z.read(_first_sheet_path(z)))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as e:
        raise PipelineError(f"Could not read {Path(path).name} as a spreadsheet: {e}")

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
                col_n = sum((ord(ch) - 64) * 26**i for i, ch in enumerate(reversed(col))) - 1
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
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise PipelineError(f"Review date '{value}' not understood (use YYYY-MM-DD).")


def read_review_xlsx(path: Path) -> dict:
    """{"schema_version", "author", "review_date", "columns", "rows"} from a
    filled review template; rows keyed by the header row's names."""
    grid = read_xlsx_grid(path)
    schema = None
    author = date = ""
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
        elif any(v.strip().lower() == "filename" for v in cells.values()):
            header_row = r
            break
    if schema is None or header_row is None:
        raise PipelineError(
            f"{Path(path).name} isn't a review template exported by this addon."
        )
    if schema > SCHEMA_VERSION:
        raise PipelineError(
            f"{Path(path).name} comes from a newer addon version (template "
            f"v{schema}); update the addon to import it."
        )
    header = {col: name.strip().lower() for col, name in grid[header_row].items()}
    rows = [
        {header[col]: v.strip() for col, v in grid[r].items() if col in header}
        for r in sorted(grid)
        if r > header_row
    ]
    return {
        "schema_version": schema,
        "author": author.strip(),
        "review_date": parse_review_date(date),
        "columns": set(header.values()),
        "rows": rows,
    }


_BULLET = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+")


def import_review_xlsx(path: Path) -> dict:
    """Create one entry per line of each filled text cell of a review
    template, all sharing one review_id, stamped with the template's Author
    ("prod" if empty) and Review date (import time if empty), anchored on
    the version the snapshot showed. A line already imported (same file,
    text and author, from a review) is skipped, so re-importing a file --
    or a re-sent one with notes added -- never duplicates.
    Returns {"imported", "duplicates", "skipped": [(label, reason)]}."""
    review = read_review_xlsx(path)
    author = review["author"] or "prod"
    date = review["review_date"]
    created_at = date.isoformat(timespec="seconds") if date else None
    review_id = hashlib.sha1(f"{now()}{Path(path).name}".encode("utf-8")).hexdigest()[:5]
    result = {"imported": 0, "duplicates": 0, "skipped": []}
    for row in review["rows"]:
        if not row.get("filename"):
            continue
        # One line of a text cell = one entry (see NOTES.md, "Batched review
        # input, still one entry each"); a typed bullet is dropped.
        lines = [
            line
            for line in (_BULLET.sub("", l).strip() for l in row.get("text", "").split("\n"))
            if line
        ]
        if not lines:
            continue
        name = row["filename"]
        try:
            filepath = find_file_by_name(
                name if name.endswith(".blend") else f"{name}.blend"
            )
        except PipelineError:  # unknown prefix...
            filepath = None
        if not filepath:
            result["skipped"].extend(
                (f"{name}: {line[:40]}", "file not found (renamed, branched or archived?)")
                for line in lines
            )
            continue
        known = {
            e.get("text")
            for e in (read_json_quiet(tracking_json_path(filepath)) or {}).get("entries", [])
            if e.get("source") == REVIEW_SOURCE and e.get("author") == author
        }
        department = (row.get("department") or "").lower()
        try:
            department = valid_department(filepath, department) if department else ""
        except PipelineError:
            department = ""
        entry_type = (row.get("type") or "").lower()
        for line in lines:
            if line in known:
                result["duplicates"] += 1
                continue
            try:
                create_entry(
                    filepath,
                    text=line,
                    department=department,
                    author=author,
                    type=entry_type if entry_type in ENTRY_TYPES else "note",
                    shot=row.get("shot") or None,
                    review_id=review_id,
                    created_at=created_at,
                    referenced_version=str(filepath),
                    source=REVIEW_SOURCE,
                )
                known.add(line)
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
    review = read_review_xlsx(path)
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
