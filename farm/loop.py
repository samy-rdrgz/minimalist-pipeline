"""Blender-side timers: the monitor/worker tick loop, and the UI refresh loop."""

import functools
from datetime import datetime
from pathlib import Path

import bpy

from ..lib import ConfigCache, addon_pref, json_get, locked_json, now, to_absolute
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


def _refresh_tick() -> float:
    """UI-only timer: recompute the full monitor snapshot and redraw the 3D
    views' sidebars plus any open farm-monitor popup (see register_popup_region)."""

    try:
        refresh_monitor_cache()
        _redraw_sidebars()

        for region in list(_popup_regions):
            try:
                region.tag_redraw()
                if hasattr(region, "tag_refresh_ui"):
                    region.tag_refresh_ui()
            except Exception:
                # region freed (popup closed) without going through
                # clear_popup_regions() -- drop the stale reference
                _popup_regions.discard(region)
    except Exception:
        pass
    return _REFRESH_INTERVAL


def _status_tick() -> float:
    """UI-only timer: cheap status-only refresh so the sidebar's farm header
    stays live even collapsed. Redraws the sidebars only when the status
    actually changed -- an idle farm reads "not running" for hours, which
    then costs one stat per tick and zero redraws."""
    global _last_status
    try:
        refresh_monitor_status()
        from .monitor import get_monitor_cache

        status = get_monitor_cache().get("status")
        if status != _last_status:
            _last_status = status
            _redraw_sidebars()
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


def _build_job_entry(job: dict) -> dict:
    """UI-facing entry for one active job. elapsed_seconds/frames_done are
    always recomputed fresh (cheap: one glob on the output folder) even when
    job came from a cached scan -- progress lives elsewhere, its mtime never
    reflects it."""
    stage = job["stage_history"][-1]
    if stage["stage"] == "archived":
        stage = job["stage_history"][-2]
    stage_time = datetime.fromisoformat(stage["at"])
    elapsed = (now(False) - stage_time).total_seconds()

    frames_done = 0
    frames_total = 0
    output_path = job.get("output_path", "")
    resolved = job.get("resolved_frame_range")
    if stage["stage"] == "render_start" and output_path and resolved:
        ext = _EXTENSION_MAP.get(job.get("output_extension"), "png")
        pattern = f"*.{ext}"
        frames_done = len(list(Path(to_absolute(output_path)).parent.glob(pattern)))
        frames_total = resolved[1] - resolved[0] + 1

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
    if not lock_path.exists():
        return status

    # Read-only, zero retries: a status read never takes the writer lock nor
    # sleeps on the UI thread. The file can vanish between the check and the
    # read (monitor stopping): treat that as "not running" instead of
    # raising into the caller.
    try:
        with locked_json(lock_path, read_only=True, retries=0) as box:
            data = box["data"] or {}
    except (OSError, ValueError):
        return status
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
