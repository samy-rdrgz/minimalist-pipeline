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
