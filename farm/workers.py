"""Worker role: register/heartbeat this machine, execute render requests, apply render presets."""

import importlib.util
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

import bpy

from ..lib import (
    AdoptedProcess,
    ConfigCache,
    PipelineError,
    get_active_project_root,
    get_addon_version,
    get_machine_id,
    get_user,
    get_user_data,
    json_get,
    locked_json,
    log,
    now,
    process_alive,
    read_json_quiet,
    retry_shared_io,
    to_absolute,
)
from .loop import register_farm_loop

STALE_WORKER_SECONDS = 15

# A frame taking this many times its usual time is stuck (a hang, not a heavy
# frame): the worker kills its own render (check_stuck_renders()). Default of
# the project setting farm.stuck_frame_factor -- 0 there: never.
STUCK_FRAME_FACTOR = 5
# Never before this long on one frame, whatever its usual time: short frames
# vary a lot, in proportion.
STUCK_FRAME_MIN_SECONDS = 300
# How often each running render is checked: two files read on the share.
_STUCK_CHECK_EVERY = 30.0
_stuck_checked_at: dict[str, float] = {}


def _worker_path(as_dir: bool = False) -> Path:
    """Path to this machine's worker_<uuid>.json, or the workers/ dir if as_dir."""
    if as_dir:
        return ConfigCache.get_path("workers")
    else:
        id = get_machine_id()
        return ConfigCache.get_path("workers") / f"worker_{id}.json"


def _heartbeat_age(heartbeat: str) -> int:
    """Seconds since an ISO heartbeat timestamp; a huge number if unparseable."""
    try:
        heartbeat = datetime.fromisoformat(heartbeat)
        return (now(iso=False) - heartbeat).total_seconds()
    except Exception:
        return 10**9


# Whether *this Blender instance* holds this machine's worker role. Runtime
# state, in memory only -- never a scene property, which would be saved into
# the .blend (see NOTES.md, "Farm popup").
_this_instance_worker = False


def _set_this_instance_worker(value: bool) -> None:
    global _this_instance_worker
    _this_instance_worker = bool(value)


def this_instance_is_worker() -> bool:
    """Whether this Blender instance is the worker for this machine -- what
    the UI shows ("Add this machine" vs "Kill this worker")."""
    return _this_instance_worker


def _recover_previous_render(previous: dict) -> dict:
    """Worker file fields to start with, given what the previous worker of
    this machine left in it. If it was mid-render (a crash): adopt the
    render by PID while it still runs, else report it "lost" right away --
    either way the monitor re-dispatches it (see NOTES.md, "Crash
    recovery")."""
    pid = previous.get("current_pid")
    job_id = previous.get("current_job_id")
    if previous.get("status") != "render" or not pid or not job_id:
        return {}
    dispatch_id = previous.get("current_dispatch_id")
    if process_alive(pid, "blender"):
        _worker_active_processes[job_id] = AdoptedProcess(
            pid, "blender", dispatch_id=dispatch_id
        )
        log(
            "WARNING",
            "farm",
            f"Render of {job_id} outlived a crash (pid {pid}) -- waiting for it.",
        )
        return {
            key: previous.get(key)
            for key in (
                "status",
                "current_job",
                "current_file",
                "current_pid",
                "current_job_id",
                "current_dispatch_id",
            )
        }
    log("WARNING", "farm", f"Render of {job_id} was lost in a crash -- reporting it.")
    return {"last_job_result": _lost_result(job_id, dispatch_id)}


def _lost_result(job_id: str, dispatch_id: str | None) -> dict:
    """last_job_result for a render whose outcome can't be known."""
    return {
        "job_id": job_id,
        "dispatch_id": dispatch_id,
        "success": False,
        "lost": True,
        "at": now(),
    }


def _worker_identity() -> dict:
    """What Worker details shows of a worker, set when it starts: the
    versions it runs and since when, its counters from zero."""
    return {
        "blender_version": bpy.app.version_string,
        "addon_version": get_addon_version(),
        "started_at": now(),
        "renders_done": 0,
        "renders_failed": 0,
    }


def launch_worker() -> bool:
    """Become the worker for this machine. Fails if another live (non-stale)
    Blender instance already holds the role."""
    worker_path = _worker_path()
    pid = os.getpid()

    with locked_json(worker_path) as box:
        data = box["data"] or {}
        if data:
            existing_pid = data.get("pid")
            stale = (
                _heartbeat_age(data.get("last_heartbeat", "")) > STALE_WORKER_SECONDS
            )
            if existing_pid and existing_pid != pid and not stale:
                return False  # another Blender instance is already the worker

        box["data"] = (
            get_user_data(get_user())
            | {
                "status": "idle",
                "current_job": None,
                "last_heartbeat": now(),
            }
            | _worker_identity()
            | _recover_previous_render(data)
        )
        box["action"] = "to_write"
        register_farm_loop(get_active_project_root())
    _set_this_instance_worker(True)
    return True


def is_blender_worker() -> bool:
    """Whether this Blender process (pid) owns this machine's worker file.
    False (no crash) if there's no active project to resolve the file
    against -- no project, no worker role. A read that fails keeps the
    previous answer: farm_tick() stops the loop on False (same as
    is_blender_monitor())."""
    try:
        worker_path = _worker_path()
    except PipelineError:
        _set_this_instance_worker(False)
        return False
    try:
        if not worker_path.exists():
            _set_this_instance_worker(False)
            return False
        with locked_json(worker_path, read_only=True, retries=0) as box:
            data = box["data"] or {}
        _set_this_instance_worker(data.get("pid") == os.getpid())
    except (OSError, ValueError):
        pass
    return _this_instance_worker


def kill_worker() -> bool:
    """Remove this machine's worker file, if this process owns it. True if
    this machine ends up with no worker role (removed or none to begin
    with), False if the entry belongs to another process and was left as-is."""
    try:
        worker_path = _worker_path()
    except PipelineError:
        return True  # No active project -- nothing to have been worker for.
    if not worker_path.exists():
        _set_this_instance_worker(False)
        return True
    pid = os.getpid()
    uuid = get_machine_id()
    with locked_json(worker_path) as box:
        data = box["data"] or {}
        owned = data.get("pid", "") == pid and data.get("uuid", "") == uuid
        if owned:
            box["action"] = "to_delete"
    _set_this_instance_worker(False)
    return owned


def _terminate(p) -> None:
    """Stop a render subprocess: terminate, then kill if it hangs."""
    p.terminate()
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()


# Worker file fields once the role is given up: "stopped" and no pid, so
# is_blender_worker() turns False (the farm loop stops) while the file --
# and its last_job_result -- stay readable by the monitor, which would
# otherwise take the render for "lost".
_STOPPED_FIELDS = {
    "status": "stopped",
    "pid": None,
    "stopping": False,
    "current_job": None,
    "current_file": None,
    "current_pid": None,
    "current_job_id": None,
    "current_dispatch_id": None,
}


def worker_rendering() -> bool:
    """Whether this instance, as a worker, has a render running right now."""
    return any(p.poll() is None for p in _worker_active_processes.values())


def stop_worker(kill_render: bool) -> str:
    """Give up this machine's worker role. kill_render=True: the render in
    progress is terminated and reported "stopped" -- neutral for the
    monitor, which carries on with the job's other machines or sends it out
    again (never a failure); the role ends now. kill_render=False: the render
    stops once the frame it's on is written (render_stop_path(), read by
    the render entry after each frame), then the role ends (worker_tick()).
    Returns "stopped" or "draining"."""
    running = [(j, p) for j, p in _worker_active_processes.items() if p.poll() is None]
    if running and not kill_render:
        for job_id, _ in running:
            try:
                render_stop_path(job_id).touch()
            except OSError as e:
                log("WARNING", "farm", f"Could not ask {job_id}'s render to stop: {e}")
        update_worker({"stopping": True})
        log("INFO", "farm", "Worker stopping once its current frame is written.")
        return "draining"
    result = None
    for job_id, p in running:
        _terminate(p)
        _clear_render_flags(job_id)
        result = {
            "job_id": job_id,
            "dispatch_id": getattr(p, "dispatch_id", None),
            "success": False,
            "stopped": True,
            "at": now(),
        }
        log("INFO", "farm", f"Worker stopped: render of {job_id} interrupted.")
    _worker_active_processes.clear()
    fields = dict(_STOPPED_FIELDS, last_heartbeat=now())
    if result:
        fields["last_job_result"] = result
    update_worker(fields)
    _set_this_instance_worker(False)
    return "stopped"


def request_worker_stop(uuid: str, kill_render: bool, user: str = "unknown") -> None:
    """Ask worker uuid -- any machine -- to stop (stop_worker() on its next
    tick): kill_render=True interrupts its render in progress, False lets it
    write the frame it's on first."""
    path = ConfigCache.get_path("farm_requests") / f"stop_{uuid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_json(path) as box:
        box["data"] = get_user_data(user) | {"kill_render": kill_render, "at": now()}
        box["action"] = "to_write"


def scan_stop_requests() -> bool:
    """Act on a stop request targeting this worker (request_worker_stop()).
    True if the worker role was given up, or is winding down."""
    path = ConfigCache.get_path("farm_requests") / f"stop_{get_machine_id()}.json"
    if not path.exists():
        return False
    with locked_json(path) as box:
        data = box["data"] or {}
        box["action"] = "to_delete"
    outcome = stop_worker(kill_render=bool(data.get("kill_render")))
    log(
        "INFO",
        "farm",
        f"Worker stop requested by {data.get('user', 'unknown')}: {outcome}.",
    )
    return True


def update_worker_heartbeat():
    """Refresh this machine's worker last_heartbeat timestamp."""
    path = _worker_path()
    with locked_json(path) as box:
        box["data"]["last_heartbeat"] = now()
        box["action"] = "to_write"


def read_workers(workers_dir: Path, silent: dict | None = None) -> dict:
    """{uuid: worker_data} for every worker file in workers_dir with a
    recent heartbeat. Pure os/json, no lock (writes are atomic) -- safe on
    a reader thread (farm.loop._read_farm_raw()). silent: filled with the
    others that never said they stopped -- crashed, closed, asleep, off the
    share -- for Farm monitoring to show them instead of hiding them."""
    workers = {}
    try:
        files = [
            e.path
            for e in os.scandir(workers_dir)
            if e.name.startswith("worker_") and e.name.endswith(".json")
        ]
    except OSError:
        return workers
    for f in files:
        data = read_json_quiet(f) or {}
        if _heartbeat_age(data.get("last_heartbeat", "")) < STALE_WORKER_SECONDS:
            workers[data.get("uuid", "unknown")] = data
        elif silent is not None and data.get("status") != "stopped":
            silent[data.get("uuid", "unknown")] = data
    return workers


def forget_worker(uuid: str) -> bool:
    """Delete worker uuid's file, if it's still silent (read_workers()): a
    machine that won't come back. True if deleted. Harmless if it does come
    back: launch_worker() writes a new file."""
    path = ConfigCache.get_path("workers") / f"worker_{uuid}.json"
    with locked_json(path) as box:
        data = box["data"] or {}
        if not data:
            return False
        if _heartbeat_age(data.get("last_heartbeat", "")) < STALE_WORKER_SECONDS:
            return False  # alive again meanwhile
        box["action"] = "to_delete"
    return True


_workers_cache: tuple[float, dict] | None = None
# scan_workers() is also read by the Render dialog's machine enum (every
# redraw): at most one scan per this many seconds, well under a heartbeat.
_WORKERS_CACHE_TTL = 1.5


def scan_workers() -> dict:
    """read_workers() for this project, cached _WORKERS_CACHE_TTL seconds."""
    global _workers_cache
    checked_at = time.monotonic()
    if _workers_cache and checked_at - _workers_cache[0] < _WORKERS_CACHE_TTL:
        return _workers_cache[1]
    workers = read_workers(_worker_path(as_dir=True))
    _workers_cache = (checked_at, workers)
    return workers


def scan_render_requests(target_uuid: str = "") -> dict:
    """Return {filename: data} for pending render requests, optionally
    filtered to target_uuid. Read without a lock (writes are atomic): a
    lock per request, every tick, only fought with the workers taking them.
    A request gone (taken) or unreadable since the listing is left out --
    whoever acts on one re-reads it under its lock (execute_render_request())."""
    requests = {}
    path = ConfigCache.get_path("farm_requests")
    if not path.exists():
        return requests
    for r in path.glob(
        f"request_*_{target_uuid}.json" if target_uuid else "request_*.json"
    ):
        data = read_json_quiet(r)
        if data:
            requests[r.name] = data
    return requests


def idle_machines() -> dict:
    """{uuid: worker} idle right now and not already targeted by a pending
    render request -- computed once per monitor tick (scan_queue()), then
    handed out: render_dispatch() takes the machines it uses out of it."""
    targeted = {r.get("target_uuid") for r in scan_render_requests().values()}
    return {
        uuid: w
        for uuid, w in scan_workers().items()
        if w.get("status") == "idle" and uuid not in targeted
    }


def update_worker(dict: dict, count: str = ""):
    """Merge dict into this machine's worker file and refresh its heartbeat.
    count: a counter field to add one to (renders_done / renders_failed)."""
    worker_path = _worker_path()
    with locked_json(worker_path) as box:
        data = box["data"] or {}
        if count:
            dict = dict | {count: int(data.get(count) or 0) + 1}
        box["data"] = data | dict | {"last_heartbeat": now()}
        box["action"] = "to_write"


def saved_frames_path(job_id: str, uuid: str) -> Path:
    """Worker uuid's record of the frames it wrote for job_id -- one
    "<dispatch_id> <frame> <time>" line per frame (no time from a worker on
    an older version), plus "<dispatch_id> start <time>" each time a render
    of it starts on that machine, appended by the render entry
    (templates/worker_render_entry.py), read by the monitor (_note_frames())
    and for the pace (frame_seconds()). Next to the render's own log."""
    return ConfigCache.get_path("farm_requests") / f"request_{job_id}_{uuid}.saved"


def parse_saved(text: str) -> list[tuple[str, int | None, float | None]]:
    """A saved_frames_path() record as (dispatch_id, frame, time) lines:
    frame None for a "start" line (a render of it starting on that
    machine), time None from a worker on an older version. Pure: safe on a
    reader thread."""
    lines = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2 or not (parts[1].isdigit() or parts[1] == "start"):
            continue
        try:
            at = float(parts[2]) if len(parts) == 3 else None
        except ValueError:
            at = None
        lines.append((parts[0], int(parts[1]) if parts[1].isdigit() else None, at))
    return lines


def frame_seconds(text: str) -> list[float]:
    """Seconds each frame took on one machine, from its saved_frames_path()
    record: the time between two frames it wrote in a row, same render
    (dispatch_id) -- times from one clock, its own. The first frame of each
    render has none (it includes opening the .blend; a "start" line marks
    it), nor a line with no time. Pure: safe on a reader thread."""
    seconds = []
    previous = None
    for dispatch_id, frame, at in parse_saved(text):
        if frame is None or at is None:
            previous = None
            continue
        if previous and previous[0] == dispatch_id and at > previous[1]:
            seconds.append(at - previous[1])
        previous = (dispatch_id, at)
    return seconds


def startup_seconds(text: str, frame_time: float) -> list[float]:
    """How long one machine took to start rendering, each time a render
    started on it: from its "start" line to its first frame, less one
    frame's time (frame_time, the job's average). Pure."""
    startups = []
    started = None
    for dispatch_id, frame, at in parse_saved(text):
        if frame is None:
            started = (dispatch_id, at)
        elif started and started[0] == dispatch_id and None not in (at, started[1]):
            startups.append(max(0.0, at - started[1] - frame_time))
            started = None
    return startups


def render_stop_path(job_id: str) -> Path:
    """This machine's "stop after this frame" flag for its render of job_id:
    the render entry exits once the frame it's on is written, if it's
    there (stop_worker(kill_render=False))."""
    return (
        ConfigCache.get_path("farm_requests")
        / f"request_{job_id}_{get_machine_id()}.stop"
    )


def _clear_render_flags(job_id: str) -> None:
    """Delete this machine's render_stop_path() of job_id once its render
    ended (or before it starts). Best effort."""
    try:
        retry_shared_io(render_stop_path(job_id).unlink)
    except OSError:
        pass


def render_request(job_data: dict, uuid: str, cmd_flags: list):
    """Write a render request file targeting worker uuid for this job."""
    request_path = (
        ConfigCache.get_path("farm_requests")
        / f"request_{job_data['job_id']}_{uuid}.json"
    )
    request_path.parent.mkdir(parents=True, exist_ok=True)
    with locked_json(request_path) as box:
        box["data"] = {"cmd_flags": cmd_flags, "target_uuid": uuid} | job_data
        box["action"] = "to_write"


_worker_active_processes: dict[str, subprocess.Popen] = {}


def execute_render_request() -> dict:
    """Pop the next render request targeting this worker and launch it as a
    subprocess. Returns the worker status patch to apply, or {} if idle."""
    global _worker_active_processes

    pending = scan_render_requests(target_uuid=get_machine_id())
    if not pending:
        return {}

    request_path, data = next(iter(pending.items()))
    request_path = ConfigCache.get_path("farm_requests") / request_path

    with locked_json(request_path) as box:
        if not box["data"]:
            # Gone since the scan: dropped by the monitor (render already
            # done, see _drop_pending_request()) or cancelled. Never launch it.
            return {}
        data = box["data"]
        try:
            log_path = request_path.parent / f"{request_path.stem}.log"
            project_root = get_active_project_root()
            templates_dir = Path(__file__).parent.parent / "templates"
            entry = templates_dir / "worker_render_entry.py"
            # Closed as soon as the child has its own copy: an open handle
            # keeps Windows from deleting or moving the file.
            _clear_render_flags(data["job_id"])  # a stop left from before
            log_file = open(log_path, "wb")
            with log_file:
                p = subprocess.Popen(
                    [
                        bpy.app.binary_path,
                        "-b",
                        str(to_absolute(data["filepath"], project_root)),
                        "-o",
                        str(to_absolute(data["output_path"], project_root)),
                        "-F",
                        data["output_extension"],
                    ]
                    + data["cmd_flags"]
                    + [
                        # Otherwise an exception in the entry script still
                        # exits 0, reported as a successful render.
                        "--python-exit-code",
                        "1",
                        "--python",
                        str(entry),
                        "--",
                        "--job-id",
                        data["job_id"],
                        "--preset",
                        data.get("prerender_script", ""),
                        # Real (possibly namespaced) module name -- see NOTES.md,
                        # "CSV batch: the subprocess couldn't import itself".
                        "--addon-module",
                        __package__.rsplit(".", 1)[0],
                        # Each frame it writes, and when: who rendered what,
                        # time per frame (queue._note_frames()).
                        "--saved-file",
                        str(saved_frames_path(data["job_id"], get_machine_id())),
                        "--dispatch-id",
                        data.get("dispatch_id") or "",
                        # Stop after this frame.
                        "--stop-file",
                        str(render_stop_path(data["job_id"])),
                    ],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                )
            p.log_path = log_path
            p.dispatch_id = data.get("dispatch_id")
        except Exception as e:
            # Malformed request: drop it instead of retrying every tick.
            box["action"] = "to_delete"
            job_id = data.get("job_id")
            log("ERROR", "farm", f"Could not launch render for {job_id}: {e}")
            if job_id:
                from .queue import mark_stage

                mark_stage(
                    ConfigCache.get_path("farm_actives") / f"{job_id}.json",
                    "render_failed",
                )
            return {}

        _worker_active_processes[data["job_id"]] = p
        box["action"] = "to_delete"
        return {
            "status": "render",
            # A name, not this machine's absolute path (shared file).
            "current_job": request_path.name,
            "current_file": data["filepath"],
            # So a worker restarted after a crash can find this render
            # again (_recover_previous_render()).
            "current_pid": p.pid,
            "current_job_id": data["job_id"],
            "current_dispatch_id": data.get("dispatch_id"),
        }


def worker_tick():
    """Per-tick worker work: heartbeat, cancel/finished-process bookkeeping,
    then pick up a render request if idle. Never raises: called from the
    farm_tick timer, an uncaught exception here would silently deregister it."""
    # A stop request first: nothing else to do once the role is given up.
    try:
        if scan_stop_requests() and not is_blender_worker():
            return
    except Exception as e:
        log("ERROR", "farm", f"Error during worker tick (scan_stop_requests): {e}")
    # Each step in its own try: one failing step must never skip the others
    # -- a heartbeat refused every tick (NAS lock) would otherwise also skip
    # scan_worker_processes(), and the worker would stay in "render" forever.
    for step in (
        update_worker_heartbeat,
        scan_cancel_requests,
        check_stuck_renders,
        scan_worker_processes,
    ):
        try:
            step()
        except Exception as e:
            log("ERROR", "farm", f"Error during worker tick ({step.__name__}): {e}")

    try:
        stopped = False
        with locked_json(_worker_path()) as box:
            data = box["data"] or {}
            if data.get("stopping"):
                # "After this frame": once the render has exited, give up the role
                # instead of picking up the next one.
                if not worker_rendering():
                    box["data"] = data | _STOPPED_FIELDS | {"last_heartbeat": now()}
                    box["action"] = "to_write"
                    stopped = True
            elif data.get("status") != "idle":
                return  # already busy, nothing to do this tick
            else:
                result = execute_render_request()
                box["data"] = data | result
                box["action"] = "to_write" if result else ""
                return
        if stopped:
            _set_this_instance_worker(False)
            log("INFO", "farm", "Worker stopped after its last render.")
    except Exception as e:
        log("ERROR", "farm", f"Error during worker tick: {e}")


def local_render_running() -> bool:
    """Whether this Blender instance, as a worker, is rendering right now --
    lets the monitor role in the same instance hold back a job's setup,
    which loads a whole second .blend alongside the render's own."""
    return any(p.poll() is None for p in _worker_active_processes.values())


def scan_worker_processes() -> None:
    """Poll this worker's active render subprocesses; publish last_job_result
    for each one that finished."""
    global _worker_active_processes
    finished = []

    for job_id, p in _worker_active_processes.items():
        ret = p.poll()
        if ret is None:
            continue
        finished.append(job_id)
        _clear_render_flags(job_id)

        # Rendered fine: its log has nothing left to tell. Kept on failure
        # (archive() moves it with the job). Best effort.
        log_path = getattr(p, "log_path", None)
        if ret == 0 and log_path:
            try:
                retry_shared_io(Path(log_path).unlink)
            except OSError:
                pass

        if getattr(p, "adopted", False):
            # Picked up again after a crash: its exit code is unknowable.
            result = _lost_result(job_id, getattr(p, "dispatch_id", None))
        else:
            result = {
                "job_id": job_id,
                "dispatch_id": getattr(p, "dispatch_id", None),
                "success": ret == 0,
                "at": now(),
            }
        update_worker(
            {
                "status": "idle",
                "current_job": None,
                "current_pid": None,
                "current_job_id": None,
                "current_dispatch_id": None,
                "last_job_result": result,
            },
            count="renders_done" if result.get("success") else "renders_failed",
        )

    for job_id in finished:
        _worker_active_processes.pop(job_id, None)


def _kill_render(job_id: str, p, result: dict, count: str = "") -> None:
    """Kill this machine's render p of job_id and publish a failed
    last_job_result carrying result's fields (cancelled, stuck...)."""
    p.terminate()
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()
    _clear_render_flags(job_id)
    update_worker(
        {
            "status": "idle",
            "current_job": None,
            "current_pid": None,
            "current_job_id": None,
            "current_dispatch_id": None,
            "last_job_result": {
                "job_id": job_id,
                "dispatch_id": getattr(p, "dispatch_id", None),
                "success": False,
                "at": now(),
            }
            | result,
        },
        count=count,
    )
    _worker_active_processes.pop(job_id, None)


def stuck_frame_factor() -> float:
    """Project setting farm.stuck_frame_factor (Edit project): how many
    times its usual time a frame may take before its render is killed; 0:
    never."""
    try:
        value = json_get(ConfigCache.get(), "farm.stuck_frame_factor", STUCK_FRAME_FACTOR)
        return max(0.0, float(STUCK_FRAME_FACTOR if value is None else value))
    except (TypeError, ValueError):
        return STUCK_FRAME_FACTOR


def stuck_frame_check(
    text: str, dispatch_id: str, job: dict, uuid: str, factor: float, at: float
) -> tuple[float, float, float] | None:
    """(seconds on the frame in progress, limit, usual seconds per frame)
    for machine uuid's render dispatch_id, from its saved_frames_path()
    record (text) -- its own clock, at: time.time() on it. The usual time:
    this render's frames so far, else the machine's on this job, else the
    job's. The first frame of a render also gets the machine's usual
    startup (scene sync). None when unknown: nothing written for this
    render yet, no usual time. Pure."""
    lines = [(f, t) for d, f, t in parse_saved(text) if d == dispatch_id and t is not None]
    if not lines:
        return None
    own = [
        b[1] - a[1]
        for a, b in zip(lines, lines[1:])
        if a[0] is not None and b[0] is not None and b[1] > a[1]
    ]
    usual = (
        (sum(own) / len(own) if own else 0)
        or (job.get("machine_seconds") or {}).get(uuid)
        or job.get("seconds_per_frame")
    )
    if not usual:
        return None
    last_frame, last_at = lines[-1]
    budget = usual
    if last_frame is None:  # its first frame: the scene sync comes first
        startups = startup_seconds(text, usual)
        budget += sum(startups) / len(startups) if startups else usual
    limit = max(factor * budget, STUCK_FRAME_MIN_SECONDS)
    return at - last_at, limit, usual


def check_stuck_renders() -> None:
    """Kill this machine's render of a job when the frame it's on takes
    stuck_frame_factor() times its usual time (stuck_frame_check()): a
    failure for this machine -- the farm host sends the frames left to the
    others (see NOTES.md, "Stuck frame")."""
    factor = stuck_frame_factor()
    if not factor:
        return
    me = get_machine_id()
    for job_id, p in list(_worker_active_processes.items()):
        if p.poll() is not None:
            continue
        t = time.monotonic()
        if t - _stuck_checked_at.get(job_id, 0.0) < _STUCK_CHECK_EVERY:
            continue
        _stuck_checked_at[job_id] = t
        try:
            text = saved_frames_path(job_id, me).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            continue
        job = read_json_quiet(ConfigCache.get_path("farm_actives") / f"{job_id}.json")
        found = stuck_frame_check(
            text, getattr(p, "dispatch_id", None), job or {}, me, factor, time.time()
        )
        if not found or found[0] <= found[1]:
            continue
        since, _limit, usual = found
        # TODO chunks (farm-chunks-plan.md §8): frame_in_progress and
        # updated_at from this machine's claim, instead of the .saved.
        frame = ""
        log(
            "WARNING",
            "farm",
            f"Render of {job_id}: stuck on {frame or 'a frame'} for {since / 60:.0f} min "
            f"(usually {usual:.0f} s a frame) -- killed, its frames go to other machines.",
        )
        _kill_render(
            job_id,
            p,
            {"stuck": {"frame": frame, "seconds": round(since), "usual": round(usual)}},
            count="renders_failed",
        )
        _stuck_checked_at.pop(job_id, None)


def scan_cancel_requests() -> None:
    """Process cancel requests targeting this worker: terminate the matching
    subprocess, if still running, and publish a cancelled last_job_result."""
    global _worker_active_processes
    my_uuid = get_machine_id()
    requests_dir = ConfigCache.get_path("farm_requests")
    if not requests_dir.exists():
        return
    for r in requests_dir.glob(f"cancel_*_{my_uuid}.json"):
        try:
            with locked_json(r) as box:
                data = box["data"]
                if data:
                    job_id = data.get("job_id")
                    p = _worker_active_processes.get(job_id)
                    if p and p.poll() is None:
                        _kill_render(job_id, p, {"cancelled": True})
                    else:
                        log(
                            "INFO",
                            "farm",
                            f"Cancel for {job_id}: no render of it running on "
                            f"this machine (already finished?).",
                        )
                box["action"] = (
                    "to_delete"  # no leftover if the job was already finished
                )
        except Exception as e:
            log("WARNING", "farm", f"Cancel request '{r.name}' failed: {e}")
            r.unlink(missing_ok=True)


def _apply_flat_overrides(scene, overrides: dict) -> None:
    """For .json presets -- dot-notation keys applied directly onto the scene.
    E.g. {"render.use_stamp": true, "render.image_settings.quality": 95}"""
    for dotted_key, value in overrides.items():
        *path, attr = dotted_key.split(".")
        try:
            target = scene
            for part in path:
                target = getattr(target, part)
            setattr(target, attr, value)
        except Exception:
            log(
                "WARNING",
                "farm",
                f"Invalid render preset key '{dotted_key}' = {value!r}.",
            )


def _read_job_quiet(job_id: str, attempts: int = 10, delay: float = 0.2) -> dict:
    """The active job's file, read without a lock (writes are atomic, see
    read_json_quiet()). A few retries: on Windows a read can be refused
    while another process replaces the file. Raises if still unreadable."""
    job_path = ConfigCache.get_path("farm_actives") / f"{job_id}.json"
    for i in range(attempts):
        data = read_json_quiet(job_path)
        if data:
            return data
        if i < attempts - 1:
            time.sleep(delay)
    raise PipelineError(f"Could not read {job_path.name}.")


def apply_custom_preset(
    preset_name: str,
    scene,
    job_id: str,
    job_data: dict | None = None,
    *,
    strict: bool = False,
) -> None:
    """Apply a per-job render preset onto scene. Looks for a .py first
    (contract: override(scene, job_data)), then a .json (flat key/value
    overrides). job_data: the job if the caller already has it (the
    setup) -- else read from its file, without a lock: every worker of a
    job starts at once, and a lock they all fought over made some of them
    render without the preset (burn-in, full resolution...).
    strict=False (the setup): any error is logged and swallowed.
    strict=True (the render): a preset that can't be applied -- missing,
    broken, job unreadable -- raises, so the render fails instead of
    rendering with the .blend's own settings."""
    if not preset_name:
        return

    base = ConfigCache.get_path("presets") / preset_name
    py_path = base.with_suffix(".py")
    json_path = base.with_suffix(".json")

    try:
        if py_path.exists():
            spec = importlib.util.spec_from_file_location("pipeline_prerender", py_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.override(
                scene, job_data if job_data is not None else _read_job_quiet(job_id)
            )
        elif json_path.exists():
            overrides = read_json_quiet(json_path)
            if overrides is None:
                raise PipelineError(f"{json_path.name} is unreadable.")
            _apply_flat_overrides(scene, overrides)
        else:
            raise PipelineError("not found")
    except Exception as e:
        level = "ERROR" if strict else "WARNING"
        log(level, "farm", f"Render preset '{preset_name}' failed: {e}")
        if strict:
            raise
