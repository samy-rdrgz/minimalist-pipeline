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


def has_figures(point) -> bool:
    """A day's point holds its finished figures (not only its activity)."""
    return isinstance(point, dict) and ("shots" in point or "assets" in point)


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
            same = all(known.get(k) == v for k, v in point.items())
            if same and not checked:
                _last[key] = (day, point)
                return False
            # Its activity, written apart, kept.
            data.setdefault("days", {})[day] = {**known, **point, "at": now()}
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
            _job["activity"] = activity_since(Path(root), today)
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
            if _job.get("activity"):
                record_activity(Path(root), *_job["activity"])
        except Exception as e:
            log("WARNING", "progress", f"Yesterday's activity not logged: {e}")
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
        if not has_figures(logged.get(key)):
            out[key] = figs
        day += timedelta(days=1)
    if not out:
        return 0
    path_of(root).parent.mkdir(parents=True, exist_ok=True)
    with locked_json(path_of(root)) as box:
        data = box["data"] if isinstance(box["data"], dict) else {}
        known = data.setdefault("days", {})
        for key, point in out.items():
            if not has_figures(known.get(key)):
                known[key] = {**(known.get(key) or {}), **point, "at": now(), "rebuilt": True}
        data["days"] = dict(sorted(known.items()))
        box["data"], box["action"] = data, "to_write"
    return len(out)


# ---------------------------------------------------------------------------
# Activity: what was worked each day, beside what was finished
# ---------------------------------------------------------------------------
# A day's "worked": {"shots"|"assets": {department: files}} -- the shots or
# assets with a session saved that day with that department ticked (Working
# on; a session counts on the day of its last save). Its "seconds": the
# sessions' time that day, everyone's, a session over midnight split
# between its days (sessions_log.jsonl, the saved ones: work time's rule);
# "people": how many worked then. Written for the days before today: the
# first Blender of the day adds those since the last ones written
# ("activity_until"), reading only the metas changed since; Migrate old
# data, every day before (rebuild_activity()).


def _sessions_of_meta(meta: dict) -> list:
    """A .wipmeta's or a .stablemeta's sessions: [(saved_at, departments)]."""
    from . import legacy

    out = []
    for s in (legacy.wip_read(dict(meta)).get(legacy.SESSIONS) or {}).values():
        if isinstance(s, dict):
            out.append((s.get("saved_at"), s.get("departments") or []))
        elif isinstance(s, list):
            out.append((meta.get("edited_at"), s))
    return out


def worked_by_day(folders, first: str, last: str) -> dict:
    """{day: {"shots"|"assets": {department: files}}} from folders [(kind
    "shot"|"asset", owner, [meta data])], first to last (days, inclusive)."""
    out: dict = {}
    for kind, owner, metas in folders:
        seen = set()
        for meta in metas:
            for saved, deps in _sessions_of_meta(meta):
                day = _day_of(saved)
                if not day or not first <= day <= last:
                    continue
                for d in deps:
                    if (day, d) in seen:
                        continue
                    seen.add((day, d))
                    per = out.setdefault(day, {}).setdefault(f"{kind}s", {})
                    per[d] = per.get(d, 0) + 1
    return out


def seconds_by_day(root: Path, first: str, last: str, archives: bool = False) -> dict:
    """{day: {"seconds", "people"}} from the sessions log (its archives too
    with archives), first to last."""
    import json
    from datetime import timedelta

    from ..core import parse_iso

    logs = Path(root) / "config" / "logs"
    paths = [logs / "sessions_log.jsonl"]
    if archives:
        paths = sorted((logs / "archives").glob("sessions_log_*.jsonl")) + paths
    secs: dict = {}
    people: dict = {}
    for path in paths:
        try:
            f = open(path, "r", encoding="utf-8")
        except OSError:
            continue
        with f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("action") != "session_end" or e.get("saved") is False:
                    continue
                end, dur = parse_iso(e.get("ts")), e.get("duration_seconds")
                if end is None or not isinstance(dur, (int, float)) or dur <= 0:
                    continue
                start = end - timedelta(seconds=dur)
                t = start
                while t < end:
                    midnight = datetime.combine(t.date() + timedelta(days=1), datetime.min.time(), t.tzinfo)
                    part = min(end, midnight)
                    day = t.date().isoformat()
                    if first <= day <= last:
                        secs[day] = secs.get(day, 0.0) + (part - t).total_seconds()
                        people.setdefault(day, set()).add(str(e.get("user") or ""))
                    t = part
    return {d: {"seconds": round(s), "people": len(people.get(d) or ())} for d, s in secs.items()}


def record_activity(root: Path, worked: dict, seconds: dict, first: str, last: str, rebuilt: bool = False) -> None:
    """Each day first to last given its activity (none: nobody worked),
    "activity_until" moved to last. Days written earlier keep their
    finished figures."""
    from datetime import timedelta

    day, end = datetime.fromisoformat(first).date(), datetime.fromisoformat(last).date()
    path_of(root).parent.mkdir(parents=True, exist_ok=True)
    with locked_json(path_of(root)) as box:
        data = box["data"] if isinstance(box["data"], dict) else {}
        known = data.setdefault("days", {})
        while day <= end:
            key = day.isoformat()
            point = known.setdefault(key, {})
            point["worked"] = worked.get(key) or {}
            s = seconds.get(key) or {}
            point["seconds"] = s.get("seconds", 0)
            point["people"] = s.get("people", 0)
            day += timedelta(days=1)
        data["days"] = dict(sorted(known.items()))
        if last > (data.get("activity_until") or ""):
            data["activity_until"] = last
        if rebuilt:
            # Every day before, done: what Migrate old data looks for (the
            # mornings' own write only covers the days since the last).
            data["activity_rebuilt"] = now()
        box["data"], box["action"] = data, "to_write"


def _recent_folders(root: Path, since: str) -> list:
    """[(kind, owner, [meta data])] of the metas changed since the day
    since began -- the only ones that can hold a session saved since.
    Pure os/json: a thread's."""
    from .tracking import _DATA_ROOTS, _pipeline_entries, _walk_owner_dirs

    start = datetime.fromisoformat(since).timestamp()
    out = []
    for top in _DATA_ROOTS:
        kind = "shot" if top == "shots" else "asset"
        for owner in _walk_owner_dirs(Path(root) / top):
            metas = []
            for entry in _pipeline_entries(owner):
                if not entry.name.endswith((".wipmeta", ".stablemeta")):
                    continue
                try:
                    if entry.stat().st_mtime < start:
                        continue
                except OSError:
                    continue
                data = read_json_quiet(Path(entry.path))
                if isinstance(data, dict):
                    metas.append(data)
            if metas:
                out.append((kind, str(owner), metas))
    return out


def activity_since(root: Path, today: str) -> tuple | None:
    """The activity of the days since the last written ("activity_until",
    else the last 30) up to yesterday: (worked, seconds, first, last), None
    if none to write. Pure os/json: check_yesterday()'s thread."""
    from datetime import timedelta

    yesterday = (datetime.fromisoformat(today).date() - timedelta(days=1)).isoformat()
    until = read(root).get("activity_until")
    first = (
        (datetime.fromisoformat(until).date() + timedelta(days=1)).isoformat()
        if until
        else (datetime.fromisoformat(today).date() - timedelta(days=30)).isoformat()
    )
    if first > yesterday:
        return None
    return (
        worked_by_day(_recent_folders(root, first), first, yesterday),
        seconds_by_day(root, first, yesterday),
        first,
        yesterday,
    )


def rebuild_activity(root: Path, folders: list, today: str | None = None) -> int:
    """Every day's activity before today, from folders [(kind, owner,
    tracking, [stablemeta data], [wipmeta data])] -- Migrate old data's --
    and the whole sessions log, archives too. How many days."""
    from datetime import timedelta

    today = today or datetime.now().date().isoformat()
    last = (datetime.fromisoformat(today).date() - timedelta(days=1)).isoformat()
    metas = [(kind, owner, [*stables, *wips]) for kind, owner, _tracking, stables, wips in folders]
    worked = worked_by_day(metas, "0000", last)
    seconds = seconds_by_day(root, "0000", last, archives=True)
    known = [*worked, *seconds]
    if not known:
        return 0
    first = min(known)
    record_activity(root, worked, seconds, first, last, rebuilt=True)
    return (datetime.fromisoformat(last).date() - datetime.fromisoformat(first).date()).days + 1
