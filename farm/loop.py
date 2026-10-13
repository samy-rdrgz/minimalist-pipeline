"""Blender-side timers: the monitor/worker tick loop, and the UI refresh loop."""

import functools
import os
import time
from datetime import datetime
from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    addon_pref,
    get_active_project_root,
    json_get,
    locked_json,
    now,
)
from ..lib.core import cached_scandir, read_json_quiet
from .post_render import _EXTENSION_MAP

_registered_tick_fn = None
_registered_status_tick_fn = None
_registered_loop_tick_fn = None

_farm_running_project: Path | None = None

# Popup open: the user is actively watching, keep it snappy.
_REFRESH_INTERVAL = 2.0
# Always-on header status: the monitor itself only ticks every ~10 s
# (farm_tick), so polling faster than that only re-reads the same data.
_STATUS_INTERVAL = 10.0

# Last status _status_tick saw -- a redraw is only requested when it changes.
_last_status: str | None = None


def get_running_project() -> Path | None:
    """Project root this Blender instance is currently monitoring/working, or None."""
    return _farm_running_project


def set_running_project(project_root: Path | None) -> None:
    """Set the project root this Blender instance is monitoring/working (None to clear)."""
    global _farm_running_project
    _farm_running_project = project_root


def stop_farm_role_for_project(project_root) -> None:
    """If this Blender instance is running a farm role (monitor and/or worker)
    for project_root, stop it. Called when the active project changes away
    from project_root without quitting Blender -- a farm role should never
    keep running for a project this instance no longer has open."""
    if not project_root or str(get_running_project() or "") != str(project_root):
        return

    from .monitor import is_blender_monitor, stop_monitor_loop
    from .workers import is_blender_worker, kill_worker

    if is_blender_monitor():
        stop_monitor_loop()
    if is_blender_worker():
        kill_worker()


def farm_tick(project_root: Path, interval: float = 10) -> float | None:
    """Timer callback. Returning None deregisters the timer (stop); any
    other float reschedules the next call in that many seconds."""

    from .monitor import is_blender_monitor, monitor_tick
    from .workers import is_blender_worker, worker_tick

    monitor = is_blender_monitor()
    worker = is_blender_worker()

    if monitor:
        monitor_tick(project_root)

    if worker:
        worker_tick()

    if not monitor and not worker:
        return

    return interval


def register_farm_loop(project_root: Path, interval: float = 10) -> None:
    """Register farm_tick as a persistent Blender timer. Raises if this
    Blender instance is already monitoring another project -- one
    orchestrator role per Blender process."""
    global _registered_loop_tick_fn, _farm_running_project
    if _farm_running_project is None:
        _farm_running_project = project_root
        _registered_loop_tick_fn = functools.partial(farm_tick, project_root, interval)
        if not bpy.app.timers.is_registered(_registered_loop_tick_fn):
            bpy.app.timers.register(
                _registered_loop_tick_fn, first_interval=1, persistent=True
            )


_popup_regions: set = set()


def register_popup_region(region) -> None:
    """Track a farm-monitor popup's own floating region so _refresh_tick can
    force its redraw. Call from the popup's draw() -- context.region_popup
    (4.2+) only exists while actually drawing, not yet at invoke() time,
    and the popup draws in its own floating region tag_redraw() can't reach."""
    if region is not None:
        _popup_regions.add(region)


def clear_popup_regions() -> None:
    """Drop every tracked popup region (called once the popup closes)."""
    _popup_regions.clear()


def refresh_monitor_cache(*, force_rescan: bool = False) -> None:
    """Recompute the full monitor snapshot (status + jobs) immediately.
    Call on project change so the cache doesn't show the previous project's
    status/jobs. force_rescan also drops the actives/incomings mtime cache,
    in case the new project's dirs share an mtime with the old one's."""
    prefs = addon_pref()
    if not prefs or not prefs.active_project_root:
        return

    from .monitor import get_monitor_cache

    if force_rescan:
        _jobs_scan_cache["actives_mtime"] = None
        _jobs_scan_cache["incomings_mtime"] = None

    get_monitor_cache().update(_compute_snapshot())


def refresh_monitor_status() -> None:
    """Cheap counterpart to refresh_monitor_cache: re-reads monitor.lock only,
    no jobs directory scan. Enough to keep the sidebar's collapsed header
    live without the cost of the full snapshot."""
    prefs = addon_pref()
    if not prefs or not prefs.active_project_root:
        return

    from .monitor import get_monitor_cache

    get_monitor_cache().update(_read_monitor_status())


class _BackgroundRead:
    """One disk read at a time on a daemon thread; the caller polls take()
    from a bpy.app.timers tick. The function run must be pure I/O -- no bpy
    -- see _read_farm_raw()."""

    def __init__(self):
        self._thread = None
        self._result = None
        self.started_at = 0.0

    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, fn, *args) -> None:
        import threading

        def run():
            try:
                self._result = ("ok", fn(*args))
            except Exception as e:  # reported by take()
                self._result = ("error", e)

        self._result = None
        self.started_at = time.monotonic()
        self._thread = threading.Thread(target=run, daemon=True, name="pipeline-farm-read")
        self._thread.start()

    def take(self):
        """("ok", value) / ("error", exc) once the read finished, else None."""
        if self.busy() or self._result is None:
            return None
        result, self._result = self._result, None
        return result


_refresh_reader = _BackgroundRead()
_status_reader = _BackgroundRead()


def _farm_paths() -> dict | None:
    """Every path the farm snapshot reads -- resolved on the main thread
    (ConfigCache/prefs are bpy), handed to the reader thread as plain data."""
    root = get_active_project_root()
    if not root:
        return None
    return {
        "root": Path(root),
        "monitor_file": ConfigCache.get_path("monitor_file"),
        "farm_actives": ConfigCache.get_path("farm_actives"),
        "farm_incomings": ConfigCache.get_path("farm_incomings"),
        "workers": ConfigCache.get_path("workers"),
    }


def _read_farm_raw(paths: dict, want_jobs: bool, scanned: dict) -> dict:
    """Reader thread: everything the farm UI shows, straight from disk, as
    plain data. Pure os/json (read_json_quiet()) -- never bpy, never a lock.
    scanned: the actives/incomings dir mtimes already scanned, so unchanged
    job folders aren't re-read."""
    from .workers import STALE_WORKER_SECONDS, _heartbeat_age

    raw: dict = {}
    monitor_file = paths["monitor_file"]
    data = read_json_quiet(monitor_file)
    try:
        mtime = os.stat(monitor_file).st_mtime if data else None
    except OSError:
        mtime = None
    raw["monitor"] = (data, mtime)
    if not want_jobs:
        return raw

    for name in ("farm_actives", "farm_incomings"):
        folder = paths[name]
        dir_mtime = _dir_mtime(folder)
        if dir_mtime == scanned.get(name):
            raw[name] = (dir_mtime, None)  # unchanged: keep what's cached
            continue
        items = []
        try:
            files = sorted(e.path for e in os.scandir(folder) if e.name.startswith("job_") and e.name.endswith(".json"))
        except OSError:
            files = []
        for f in files:
            item = read_json_quiet(f)
            if item:
                if name == "farm_incomings":
                    item = dict(item)
                    item["_job_id"] = Path(f).stem
                items.append(item)
        raw[name] = (dir_mtime, items)

    workers = {}
    try:
        worker_files = [e.path for e in os.scandir(paths["workers"]) if e.name.startswith("worker_") and e.name.endswith(".json")]
    except OSError:
        worker_files = []
    for f in worker_files:
        w = read_json_quiet(f) or {}
        if _heartbeat_age(w.get("last_heartbeat", "")) < STALE_WORKER_SECONDS:
            workers[w.get("uuid", "unknown")] = w
    raw["workers"] = workers
    return raw


def _frames_for_jobs(root: Path, jobs: list) -> dict:
    """Reader thread: rendered-frame counts for the jobs being rendered."""
    frames = {}
    for job in jobs:
        try:
            stage = job["stage_history"][-1]["stage"]
        except (KeyError, IndexError, TypeError):
            continue
        out = _output_dir(job, root)
        if stage == "render_start" and out and job.get("resolved_frame_range"):
            ext = _EXTENSION_MAP.get(job.get("output_extension"), "png")
            frames[job.get("job_id", "")] = _count_rendered_frames(out, ext)
    return frames


def _read_farm_snapshot(paths: dict, scanned: dict, cached_actives: list) -> dict:
    """Reader thread, full popup refresh: _read_farm_raw() + frame counts."""
    raw = _read_farm_raw(paths, True, scanned)
    actives = raw["farm_actives"][1]
    raw["frames"] = _frames_for_jobs(paths["root"], actives if actives is not None else cached_actives)
    return raw


def _status_from_monitor_raw(monitor: tuple) -> dict:
    """Main thread: the sidebar/popup status fields from (lock content, mtime)."""
    data, mtime = monitor
    status = {"status": "not running", "lock_user": "", "lock_machine": "", "last_tick": None}
    if not data:
        return status
    last = datetime.fromtimestamp(mtime) if mtime else None
    try:
        in_file = datetime.fromisoformat(data.get("update_tick", ""))
        last = max(last, in_file) if last else in_file
    except (TypeError, ValueError):
        pass
    if last is None:
        return status
    status["status"] = monitor_age_status(last)
    status["lock_user"] = data.get("user", "")
    status["lock_machine"] = data.get("machine", "")
    status["last_tick"] = last
    return status


def _apply_farm_snapshot(raw: dict) -> None:
    """Main thread: fold a reader-thread snapshot into the monitor cache
    (memory only)."""
    from .monitor import get_monitor_cache

    snapshot = _status_from_monitor_raw(raw["monitor"])
    for name, key in (("farm_actives", "actives"), ("farm_incomings", "incomings")):
        dir_mtime, items = raw[name]
        if items is not None:
            _jobs_scan_cache[f"{key}_raw"] = items
        _jobs_scan_cache[f"{key}_mtime"] = dir_mtime
    frames = raw.get("frames", {})
    jobs = []
    for job in _jobs_scan_cache["actives_raw"]:
        try:
            jobs.append(_build_job_entry(job, frames.get(job.get("job_id", ""))))
        except Exception:
            pass
    for req in _jobs_scan_cache["incomings_raw"]:
        try:
            jobs.append(_build_incoming_entry(req))
        except Exception:
            pass
    snapshot["jobs"] = jobs
    snapshot["workers"] = raw.get("workers", {})
    get_monitor_cache().update(snapshot)


def _redraw_sidebars() -> None:
    """Tag only the 3D views' sidebar (UI) regions, where the farm panel
    lives. area.tag_redraw() would redraw every region of the area,
    including the viewport itself -- a full scene redraw just to refresh
    one label, even with the sidebar hidden."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "UI":
                    region.tag_redraw()


def _redraw_popups() -> None:
    for region in list(_popup_regions):
        try:
            region.tag_redraw()
            if hasattr(region, "tag_refresh_ui"):
                region.tag_refresh_ui()
        except Exception:
            # region freed (popup closed) without going through
            # clear_popup_regions() -- drop the stale reference
            _popup_regions.discard(region)


def _refresh_tick() -> float:
    """UI-only timer while the farm popup is open. Never touches the disk
    itself: every _REFRESH_INTERVAL it starts a background read
    (_read_farm_snapshot()), and when one has finished it applies it to the
    monitor cache and redraws -- a refresh used to block the UI for every
    disk call it made (~10 network round-trips each 2 s on a share)."""
    try:
        result = _refresh_reader.take()
        if result is not None and result[0] == "ok":
            _apply_farm_snapshot(result[1])
            _redraw_sidebars()
            _redraw_popups()
        if not _refresh_reader.busy() and time.monotonic() - _refresh_reader.started_at >= _REFRESH_INTERVAL:
            paths = _farm_paths()
            if paths:
                scanned = {
                    "farm_actives": _jobs_scan_cache["actives_mtime"],
                    "farm_incomings": _jobs_scan_cache["incomings_mtime"],
                }
                _refresh_reader.start(
                    _read_farm_snapshot, paths, scanned, list(_jobs_scan_cache["actives_raw"])
                )
    except Exception:
        pass
    return 0.25


def _status_tick() -> float:
    """UI-only timer: status-only refresh so the sidebar's farm header stays
    live even collapsed. The read runs on a background thread (monitor.lock
    only); this tick applies the last result and redraws the sidebars only
    when the status actually changed -- an idle farm reads "not running" for
    hours and costs zero redraws, and zero disk calls on the UI thread."""
    global _last_status
    try:
        result = _status_reader.take()
        if result is not None and result[0] == "ok":
            from .monitor import get_monitor_cache

            get_monitor_cache().update(_status_from_monitor_raw(result[1]["monitor"]))
            status = get_monitor_cache().get("status")
            if status != _last_status:
                _last_status = status
                _redraw_sidebars()
            return _STATUS_INTERVAL
        if not _status_reader.busy():
            paths = _farm_paths()
            if paths:
                _status_reader.start(_read_farm_raw, paths, False, {})
                return 0.5  # come back for the result shortly
    except Exception:
        pass
    return _STATUS_INTERVAL


_jobs_scan_cache = {
    "actives_mtime": None,
    "incomings_mtime": None,
    "actives_raw": [],
    "incomings_raw": [],
}


def _dir_mtime(path: Path) -> float:
    """0.0 if the directory doesn't exist yet -- never raises."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _scan_active_jobs(jobs_dir: Path) -> list[dict]:
    """Full scan: open every job_*.json in farm_actives/. Read-only, zero
    retries: this only ever reads box["data"], never writes back, and runs
    off the UI-ish _refresh_tick timer -- it must never wait on, let alone
    take, another process's write lock."""
    raw = []
    for job_file in sorted(jobs_dir.glob("job_*.json")):
        with locked_json(job_file, read_only=True, retries=0) as box:
            try:
                job = box["data"] or {}
                if job:
                    raw.append(job)
            except Exception:
                pass
    return raw


def _scan_incoming_jobs(incomings_dir: Path) -> list[dict]:
    """Full scan: open every job_*.json in farm_incomings/. Read-only, zero
    retries -- see _scan_active_jobs()."""
    raw = []
    for req_file in sorted(incomings_dir.glob("job_*.json")):
        with locked_json(req_file, read_only=True, retries=0) as box:
            try:
                req = box["data"] or {}
                if req:
                    req = dict(req)
                    req["_job_id"] = req_file.stem
                    raw.append(req)
            except Exception:
                pass
    return raw


def _output_dir(job: dict, root: Path | None = None) -> Path | None:
    """Absolute folder a job renders into, or None before setup has set it.
    A plain join on the project root, never to_absolute()/resolve() -- this
    runs for every job on every popup refresh, and a resolve is two network
    round-trips on Windows."""
    output_path = job.get("output_path", "")
    root = root or get_active_project_root()
    if not output_path or not root:
        return None
    path = Path(output_path)
    return (path if path.is_absolute() else Path(root) / path).parent


def _count_rendered_frames(folder: Path, ext: str) -> int:
    """Frames actually written in folder: files with this extension and a
    non-zero size. Renders run with placeholders (worker_render_entry.py),
    which create an empty file per frame when it *starts* -- counting those
    showed frames claimed, not done. cached_scandir() re-lists the folder
    only when its mtime changes, and DirEntry.stat() reads the size the
    listing already returned (Windows) instead of one stat per frame."""
    suffix = f".{ext}".lower()
    done = 0
    for entry in cached_scandir(folder):
        if not entry.name.lower().endswith(suffix):
            continue
        try:
            if entry.stat().st_size > 0:
                done += 1
        except OSError:
            pass
    return done


def _build_job_entry(job: dict, frames_done: int | None = None) -> dict:
    """UI-facing entry for one active job. elapsed_seconds/frames_done are
    recomputed fresh even when job came from a cached scan -- progress
    lives in the output folder, the job file's mtime never reflects it."""
    stage = job["stage_history"][-1]
    if stage["stage"] == "archived":
        stage = job["stage_history"][-2]
    stage_time = datetime.fromisoformat(stage["at"])
    elapsed = (now(False) - stage_time).total_seconds()

    frames_total = 0
    output_dir = _output_dir(job)
    resolved = job.get("resolved_frame_range")
    if stage["stage"] == "render_start" and output_dir and resolved:
        if frames_done is None:  # synchronous path (refresh_monitor_cache())
            ext = _EXTENSION_MAP.get(job.get("output_extension"), "png")
            frames_done = _count_rendered_frames(output_dir, ext)
        frames_total = resolved[1] - resolved[0] + 1
    frames_done = frames_done or 0

    return {
        "job_id": job.get("job_id", ""),
        "filepath": job.get("filepath", ""),
        "stage": stage["stage"],
        "stage_at": stage["at"],
        "elapsed_seconds": elapsed,
        "frames_done": frames_done,
        "frames_total": frames_total,
        "machines": job.get("used_machines", []),
        "skipped_shots": job.get("skipped_shots", []),
        "absorbed_shots": job.get("absorbed_shots", []),
        "shot_override": job.get("shot_override", ""),
        "output_dir": str(output_dir) if output_dir else "",
    }


def _build_incoming_entry(req: dict) -> dict:
    """UI-facing "pending" entry for one not-yet-claimed request."""
    submitted_at = datetime.fromisoformat(req["submitted_at"])
    return {
        "job_id": req.get("_job_id", ""),
        "filepath": req.get("filepath", ""),
        "stage": "pending",
        "stage_at": req["submitted_at"],
        "elapsed_seconds": (now(False) - submitted_at).total_seconds(),
        "frames_done": 0,
        "frames_total": 0,
        "machines": [],
        "shot_override": req.get("shot_override", ""),
    }


def monitor_last_tick(lock_path: Path, data: dict | None = None) -> datetime | None:
    """The monitor's last heartbeat: the newer of monitor.lock's mtime
    (bumped every tick by os.utime(), never refused) and its content's
    "update_tick" (rewritten every tick too, but best effort -- see
    monitor_tick()). Pass `data` if the content is already read; mtime alone
    otherwise, which is enough since every content write bumps it as well.
    None if the file is gone or can't be stat'd. Clock caveat: the monitor
    machine's clock vs the reader's (see now())."""
    try:
        last = datetime.fromtimestamp(lock_path.stat().st_mtime)
    except OSError:
        return None
    try:
        in_file = datetime.fromisoformat((data or {}).get("update_tick", ""))
        last = max(last, in_file)
    except (TypeError, ValueError):
        pass
    return last


def monitor_age_status(last_tick: datetime) -> str:
    """"running" | "stale" | "dead" for a heartbeat timestamp. "stale" is a
    missed heartbeat that may still recover on its own; "dead" is well past
    that and treated as safe to relaunch over without much doubt."""
    stale_threshold = json_get(ConfigCache.get(), "farm.stale_monitor_seconds", 90)
    dead_threshold = json_get(
        ConfigCache.get(), "farm.dead_monitor_seconds", stale_threshold * 4
    )
    age = (now(False) - last_tick).total_seconds()
    if age > dead_threshold:
        return "dead"
    if age > stale_threshold:
        return "stale"
    return "running"


def _read_monitor_status() -> dict:
    """Read monitor.lock only, no jobs directory scan: owner from its
    content, liveness from monitor_last_tick() (mtime or in-file
    update_tick, whichever is newer)."""
    status = {
        "status": "not running",
        "lock_user": "",
        "lock_machine": "",
        "last_tick": None,
    }

    lock_path = ConfigCache.get_path("monitor_file")

    # No exists() first (a missing file just reads as None below). Read-only, zero retries: a status read never takes the writer lock nor
    # sleeps on the UI thread. The file can vanish between the check and the
    # read (monitor stopping): treat that as "not running" instead of
    # raising into the caller.
    try:
        with locked_json(lock_path, read_only=True, retries=0) as box:
            data = box["data"]
    except (OSError, ValueError):
        return status
    if not data:
        return status  # no monitor.lock: not running
    last_tick = monitor_last_tick(lock_path, data)
    if last_tick is None:
        return status

    status["status"] = monitor_age_status(last_tick)
    status["lock_user"] = data.get("user", "")
    status["lock_machine"] = data.get("machine", "")
    status["last_tick"] = last_tick
    return status


def _compute_snapshot() -> dict:
    """Full snapshot for draw(): monitor status plus the job lists.
    farm_actives/farm_incomings are only re-scanned when their own mtime
    changed since the last tick (every write here bumps it via atomic
    rename/lock), so a stale mtime just delays noticing a change by one
    tick, never hides it permanently."""
    snapshot = {"jobs": []}
    snapshot.update(_read_monitor_status())
    # Workers too, so the popup's draw() only ever reads memory: draw() runs
    # on every hover/redraw of the popup, this runs once per refresh tick.
    try:
        from .workers import scan_workers

        snapshot["workers"] = scan_workers()
    except Exception:
        snapshot["workers"] = {}

    jobs_dir = ConfigCache.get_path("farm_actives")
    incomings_dir = ConfigCache.get_path("farm_incomings")

    actives_mtime = _dir_mtime(jobs_dir)
    if actives_mtime != _jobs_scan_cache["actives_mtime"]:
        _jobs_scan_cache["actives_raw"] = _scan_active_jobs(jobs_dir)
        _jobs_scan_cache["actives_mtime"] = actives_mtime

    incomings_mtime = _dir_mtime(incomings_dir)
    if incomings_mtime != _jobs_scan_cache["incomings_mtime"]:
        _jobs_scan_cache["incomings_raw"] = _scan_incoming_jobs(incomings_dir)
        _jobs_scan_cache["incomings_mtime"] = incomings_mtime

    for job in _jobs_scan_cache["actives_raw"]:
        try:
            snapshot["jobs"].append(_build_job_entry(job))
        except Exception:
            pass

    # Requests not yet claimed by a monitor tick (or with none running at
    # all) -- shown as "pending" so submitting a job is never invisible,
    # even with the farm stopped.
    for req in _jobs_scan_cache["incomings_raw"]:
        try:
            snapshot["jobs"].append(_build_incoming_entry(req))
        except Exception:
            pass

    return snapshot


def register_refresh_timer() -> None:
    """Register _refresh_tick as a persistent Blender timer (UI redraw loop)."""
    global _registered_tick_fn
    if _registered_tick_fn is None:
        _registered_tick_fn = _refresh_tick
        bpy.app.timers.register(_registered_tick_fn, first_interval=0, persistent=True)


def unregister_refresh_timer() -> None:
    """Unregister the UI redraw timer and drop any tracked popup regions."""
    global _registered_tick_fn
    if _registered_tick_fn is not None and bpy.app.timers.is_registered(
        _registered_tick_fn
    ):
        bpy.app.timers.unregister(_registered_tick_fn)
    _registered_tick_fn = None


def register_status_timer() -> None:
    """Register _status_tick as a persistent Blender timer (cheap, always on)."""
    global _registered_status_tick_fn
    if _registered_status_tick_fn is None:
        _registered_status_tick_fn = _status_tick
        bpy.app.timers.register(
            _registered_status_tick_fn, first_interval=0, persistent=True
        )


def unregister_status_timer() -> None:
    global _registered_status_tick_fn
    if _registered_status_tick_fn is not None and bpy.app.timers.is_registered(
        _registered_status_tick_fn
    ):
        bpy.app.timers.unregister(_registered_status_tick_fn)
    _registered_status_tick_fn = None
    clear_popup_regions()
