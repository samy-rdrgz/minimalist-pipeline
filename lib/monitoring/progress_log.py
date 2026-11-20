"""The project's progress over time: one point a day in
config/logs/progress.json, {"days": {"YYYY-MM-DD": {"shots", "assets",
"at"}}, "checked": "YYYY-MM-DD"} -- each kind's Done and Validated, and
each department's (figures(): the snapshot's own numbers).

Written, never by a check run on purpose:
- today's point, when a snapshot is exported and while the live page runs
  (each time its figures change: a write only then);
- the day before's, once a day, at the first Blender of the day on the
  project (check_yesterday()): the project as it is then, put on the day
  of its last change (the newest .pipeline folder's date) -- Monday's first
  launch writes Friday evening's, whatever was logged during Friday.
Today's point may lag behind the day; the past ones are exact.

The page draws it (Breakdown, Over time). Memory and one small file: the
scan itself is the snapshot's or the live page's, or check_yesterday()'s
own on a thread."""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path

from ..core import locked_json, now, read_json_quiet
from ..logs import log

NAME = "progress.json"


def path_of(root: Path) -> Path:
    return Path(root) / "config" / "logs" / NAME


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def figures(snapshot: dict) -> dict:
    """build_snapshot()'s numbers, for a point: {"shots"|"assets": {"done",
    "validated", "departments": {d: {"done", "validated"}}}}."""
    meta = snapshot.get("meta") or {}
    out = {}
    for kind, key in (("shots", "shot"), ("assets", "asset")):
        items = [i for i in snapshot.get(kind) or [] if not i.get("omit")]
        deps = {}
        for d in dict.fromkeys(d for i in items for d in i.get("departments") or {}):
            mine = [i for i in items if d in (i.get("departments") or {})]
            deps[d] = {
                "done": _mean((i.get("scores") or {}).get(d) for i in mine),
                "validated": _mean(float(bool((i.get("validated") or {}).get(d))) for i in mine),
            }
        out[kind] = {
            "done": (meta.get("progress") or {}).get(key),
            "validated": (meta.get("validation") or {}).get(key),
            "departments": deps,
        }
    return out


def read(root: Path) -> dict:
    data = read_json_quiet(path_of(root))
    return data if isinstance(data, dict) else {}


def days(root: Path) -> dict:
    """{day: point}, for the page."""
    return dict(sorted((read(root).get("days") or {}).items()))


_last: dict[str, tuple] = {}  # root: (day, figures) last written by this Blender


def record(root: Path, day: str, point: dict, checked: str | None = None) -> bool:
    """day's point set to point (figures()). False, nothing written, when
    it holds those figures already."""
    key = str(root)
    if checked is None and _last.get(key) == (day, point):
        return False
    try:
        path_of(root).parent.mkdir(parents=True, exist_ok=True)
        with locked_json(path_of(root)) as box:
            data = box["data"] if isinstance(box["data"], dict) else {}
            known = (data.get("days") or {}).get(day) or {}
            same = {k: v for k, v in known.items() if k != "at"} == point
            if same and not checked:
                _last[key] = (day, point)
                return False
            data.setdefault("days", {})[day] = {**point, "at": now()}
            if checked:
                data["checked"] = checked
            box["data"], box["action"] = data, "to_write"
        _last[key] = (day, point)
        return True
    except Exception as e:  # never in an artist's way
        log("WARNING", "progress", f"Progress not logged: {e}")
        return False


def record_today(root: Path, snapshot: dict) -> None:
    """Today's point from a snapshot just built (export, live page)."""
    record(root, datetime.now().date().isoformat(), figures(snapshot))


def _last_change_day(root: Path, before: str) -> str | None:
    """The day of the project's last change before `before` (a day): its
    newest .pipeline folder's (a write replaces a file there: the folder's
    date moves). None if none before it."""
    from .tracking import _DATA_ROOTS, _walk_owner_dirs

    newest = 0.0
    limit = datetime.fromisoformat(before).timestamp()
    for top in _DATA_ROOTS:
        for owner in _walk_owner_dirs(Path(root) / top):
            try:
                t = os.stat(owner / ".pipeline").st_mtime
            except OSError:
                continue
            if newest < t < limit:
                newest = t
    return datetime.fromtimestamp(newest).date().isoformat() if newest else None


_job: dict = {}
_memo: dict[str, str] = {}  # root: the day this Blender checked it


def check_yesterday(root: Path) -> None:
    """Once a day per project (the first Blender of the day): the project
    read on a thread, its figures put on the day of its last change, before
    today. Main thread: the snapshot's build (ConfigCache) on a timer."""
    import bpy

    today = datetime.now().date().isoformat()
    if _memo.get(str(root)) == today:
        return  # this Blender saw it done today: not even the file read
    _memo[str(root)] = today
    if read(root).get("checked") == today:
        return
    _job.clear()
    _job["root"] = str(root)

    def work():
        from .snapshot import read_snapshot_raw

        try:
            _job["raws"] = read_snapshot_raw(Path(root))
            _job["day"] = _last_change_day(Path(root), today)
        except Exception as e:
            _job["error"] = str(e)
        _job["done"] = True

    threading.Thread(target=work, name="pipeline-progress", daemon=True).start()

    def apply():
        if not _job.get("done"):
            return 1.0
        if _job.get("error"):
            log("WARNING", "progress", f"Yesterday's progress not checked: {_job['error']}")
            return None
        from ..config import ConfigCache
        from .snapshot import build_snapshot

        day = _job.get("day")
        try:
            if day:
                snap = build_snapshot(_job["raws"], ConfigCache.get() or {}, {})
                if record(Path(root), day, figures(snap), checked=today):
                    log("INFO", "progress", f"Progress of {day} logged")
            else:
                _mark_checked(Path(root), today)
        except Exception as e:
            log("WARNING", "progress", f"Yesterday's progress not checked: {e}")
        return None

    bpy.app.timers.register(apply, first_interval=1.0)


def _mark_checked(root: Path, today: str) -> None:
    try:
        path_of(root).parent.mkdir(parents=True, exist_ok=True)
        with locked_json(path_of(root)) as box:
            data = box["data"] if isinstance(box["data"], dict) else {}
            data["checked"] = today
            box["data"], box["action"] = data, "to_write"
    except Exception as e:
        log("WARNING", "progress", f"Progress not checked: {e}")


# ---------------------------------------------------------------------------
# The days before the log: rebuilt once, by Migrate old data
# ---------------------------------------------------------------------------
# The one place every .stablemeta and .wipmeta of the project is read
# (lib/migration.py reads them all anyway): each folder as it stood at the
# end of each day something changed in it -- its stables made by then and
# the validations given by then, the sessions saved by then, the notes
# written by then and still open then -- through the state engine and the
# snapshot's own figures. A day nothing changed holds the day before's
# figures. The days the log holds already are kept as logged.
# See NOTES.md, "Progress over time: the days before the log".


_seen_at: dict = {}  # a date as written: parsed once (rebuild() reads each many times)


def _at(value) -> datetime | None:
    from ..core import parse_iso

    if not isinstance(value, str):
        return parse_iso(value)
    if value not in _seen_at:
        _seen_at[value] = parse_iso(value)
    return _seen_at[value]


def _end_of(day: str) -> datetime:
    from datetime import time

    return datetime.combine(datetime.fromisoformat(day).date(), time(23, 59, 59)).astimezone()


def _day_of(value) -> str | None:
    t = _at(value)
    return t.date().isoformat() if t else None


def _folder_at(kind: str, tracking: dict, stables: list, wipmetas: list, end: datetime) -> dict | None:
    """_collect_folder()'s data for a folder as it stood at end; None if
    it didn't exist yet."""
    from . import legacy
    from .tracking import _DEFAULT_STABLE

    made = _at(tracking.get("created_at"))
    if made and made > end:
        return None
    entries = []
    for e in tracking.get("entries") or []:
        at = _at(e.get("created_at"))
        if at and at > end:
            continue
        done_at = _at(e.get("done_at"))
        if e.get("done") and done_at and done_at > end:
            e = {**e, "done": False}
        entries.append(e)
    past = [s for s in stables if (_at(s.get("created_at")) or end) <= end]
    last = dict(max(past, key=lambda s: _at(s.get("created_at")) or end)) if past else dict(_DEFAULT_STABLE)
    last["approvals"] = {
        d: kept
        for d, roles in (last.get("approvals") or {}).items()
        if isinstance(roles, dict)
        and (kept := {r: i for r, i in roles.items() if not isinstance(i, dict) or (_at(i.get("at")) or end) <= end})
    }
    wips = []
    for meta in wipmetas:
        made = _at(meta.get("created_at"))
        if made and made > end:
            continue
        sessions = legacy.wip_read(dict(meta)).get(legacy.SESSIONS) or {}
        kept = {
            k: s
            for k, s in sessions.items()
            if (_at(s.get("saved_at") if isinstance(s, dict) else meta.get("edited_at")) or end) <= end
        }
        wips.append({**meta, legacy.SESSIONS: kept, legacy.V1_SESSIONS: dict(kept)})
    return {
        "tracking": {**tracking, "entries": entries},
        "last_stable": last,
        "wipmetas": wips,
        "started": last.get("departments_started") or [],
        "kind": f"{kind}s",
    }


def _change_days(tracking: dict, stables: list, wipmetas: list) -> set[str]:
    """The days something changed in a folder: made, a note written or
    closed, a stable made, a validation given, a session saved."""
    from . import legacy

    out = {_day_of(tracking.get("created_at"))}
    for e in tracking.get("entries") or []:
        out |= {_day_of(e.get("created_at")), _day_of(e.get("done_at"))}
    for s in stables:
        out.add(_day_of(s.get("created_at")))
        for roles in (s.get("approvals") or {}).values():
            for info in (roles or {}).values() if isinstance(roles, dict) else ():
                if isinstance(info, dict):
                    out.add(_day_of(info.get("at")))
    for meta in wipmetas:
        for s in (legacy.wip_read(dict(meta)).get(legacy.SESSIONS) or {}).values():
            out.add(_day_of(s.get("saved_at") if isinstance(s, dict) else meta.get("edited_at")))
    out.discard(None)
    return out


def rebuild(root: Path, folders: list, config: dict, today: str | None = None) -> int:
    """The days before today the log doesn't hold, rebuilt from folders:
    [(kind "shot"|"asset", owner Path, tracking, [stablemeta data],
    [wipmeta data])] -- every one of the project's, as Migrate old data
    read them. Each folder's state worked out on its own change days only
    (the snapshot's build, one folder at a time), the project's figures
    each day from every folder's latest. Main thread (build_snapshot()).
    How many days written."""
    from datetime import timedelta

    from .snapshot import average_progress, build_snapshot

    today = today or datetime.now().date().isoformat()
    _seen_at.clear()
    timeline = []  # per folder: (kind, [(day, its item that evening, or None)])
    every = set()
    for kind, owner, tracking, stables, wips in folders:
        points = []
        for day in sorted(d for d in _change_days(tracking, stables, wips) if d < today):
            raw = _folder_at(kind, tracking, stables, wips, _end_of(day))
            item = None
            if raw is not None:
                built = build_snapshot([(kind, Path(owner), raw, [])], config, {})
                item = next(iter(built.get(f"{kind}s") or []), None)
            points.append((day, item))
        if points:
            timeline.append((kind, points))
            every |= {d for d, _ in points}
    if not every:
        return 0
    logged = days(root)
    out, figs = {}, None
    at = [0] * len(timeline)  # each folder's next point
    current = [None] * len(timeline)
    day = datetime.fromisoformat(min(every)).date()
    last = datetime.fromisoformat(today).date() - timedelta(days=1)
    while day <= last:
        key = day.isoformat()
        if key in every or figs is None:
            for n, (_kind, points) in enumerate(timeline):
                while at[n] < len(points) and points[at[n]][0] <= key:
                    current[n] = points[at[n]][1]
                    at[n] += 1
            snap = {"meta": {"progress": {}, "validation": {}}, "shots": [], "assets": []}
            for n, (kind, _points) in enumerate(timeline):
                if current[n] is not None:
                    snap[f"{kind}s"].append(current[n])
            for kind in ("shot", "asset"):
                snap["meta"]["progress"][kind] = average_progress(snap[f"{kind}s"])
                snap["meta"]["validation"][kind] = average_progress(snap[f"{kind}s"], "validation")
            figs = figures(snap)
        if key not in logged:
            out[key] = figs
        day += timedelta(days=1)
    if not out:
        return 0
    path_of(root).parent.mkdir(parents=True, exist_ok=True)
    with locked_json(path_of(root)) as box:
        data = box["data"] if isinstance(box["data"], dict) else {}
        known = data.setdefault("days", {})
        for key, point in out.items():
            known.setdefault(key, {**point, "at": now(), "rebuilt": True})
        data["days"] = dict(sorted(known.items()))
        box["data"], box["action"] = data, "to_write"
    return len(out)
