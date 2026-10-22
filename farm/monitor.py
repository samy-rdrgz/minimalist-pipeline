"""Monitor role: a single Blender instance owns monitor.lock and ticks the
queue on a timer. No automatic takeover on a stale lock -- manual kill only."""

import hashlib
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..lib import (
    AdoptedProcess,
    ConfigCache,
    PipelineError,
    get_machine_id,
    get_user_data,
    json_get,
    locked_json,
    log,
    now,
    process_alive,
    read_json_quiet,
    to_relative,
)
from .dispatch import LOG_KEEP_BYTES, compact_log
from .loop import (
    get_running_project,
    monitor_age_status,
    monitor_last_tick,
    register_farm_loop,
    set_running_project,
)
from .queue import (
    discard_saved_frames,
    scan_processes,
    scan_queue,
    scan_requests,
)

_monitor_cache: dict = {
    "status": "unknown",  # "running" | "stale" | "dead"
    "lock_user": "",
    "lock_machine": "",
    "last_tick": None,
    "jobs": [],  # list of per-job snapshots
    "workers": {},  # {uuid: worker data}, see _apply_farm_snapshot()
}


def get_monitor_cache():
    """Return the module-level monitor snapshot dict (refreshed by _refresh_tick)."""
    return _monitor_cache


def reset_monitor_cache() -> None:
    """Blank the snapshot back to its startup state. Call when the active
    project is unset -- there's nothing left to compute a snapshot for."""
    _monitor_cache.update(
        {
            "status": "unknown",
            "lock_user": "",
            "lock_machine": "",
            "last_tick": None,
            "jobs": [],
            "workers": {},
        }
    )


def launch_monitor(
    project_root: Path,
    user: str = "unknown",
    interval: float = 10,
    force: bool = False,
) -> None:
    """Become the monitor for project_root. Raises if another monitor.lock
    is already present, or if this Blender instance already monitors a
    different project."""
    path = ConfigCache.get_path("monitor_file")
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_json(path) as box:
        data = box["data"]
        if data:  # lock exists
            last_tick = monitor_last_tick(path, data) or datetime.min
            is_stale = monitor_age_status(last_tick) != "running"

            if not is_stale:
                raise PipelineError(f"Monitor role already taken by {data['user']}.")
            if not force:
                raise PipelineError(
                    f"Stale lock detected (last seen by {data['user']})."
                )

            log("WARNING", "farm", f"Taking over a stale lock left by {data['user']}.")

        register_farm_loop(project_root, interval)

        recover_interrupted_jobs()

        # Heartbeat from here on: see monitor_tick() (best-effort rewrite of
        # update_tick + os.utime() on this file).
        box["data"] = get_user_data(user) | {"start_time": now(), "update_tick": now()}
        box["action"] = "to_write"


_last_is_monitor = False


def is_blender_monitor() -> bool:
    """Whether this Blender process (pid + machine uuid) owns monitor.lock.
    A read that fails keeps the previous answer: farm_tick() stops the whole
    loop on False, and "couldn't check" must never mean "not the monitor"."""
    global _last_is_monitor
    try:
        lock_path = ConfigCache.get_path("monitor_file")
    except PipelineError:
        _last_is_monitor = False  # no active project, no monitor role
        return False
    try:
        if not lock_path.exists():
            _last_is_monitor = False
            return False
        with locked_json(lock_path, read_only=True, retries=0) as box:
            data = box["data"] or {}
        _last_is_monitor = (
            data.get("pid", "") == os.getpid()
            and data.get("uuid", "") == get_machine_id()
        )
    except (OSError, ValueError) as e:
        log("WARNING", "farm", f"Could not read monitor.lock, keeping last state: {e}")
    return _last_is_monitor


def monitor_tick(project_root: Path):
    """Per-tick monitor work: clear monitor.lock if stopped, else process kill
    requests, scan incoming/active jobs, and refresh the heartbeat."""
    if get_running_project() != project_root:
        try:
            path = ConfigCache.get_path("monitor_file")
            if path.exists():
                with locked_json(path) as box:
                    data = box["data"] or {}
                    if data.get("pid", "") == os.getpid():
                        box["action"] = "to_delete"
        except Exception as e:
            log("ERROR", "farm", f"Error while clearing monitor.lock on stop: {e}")
        return

    # Each step in its own try: one failing step must never skip the others
    # (see NOTES.md, "Windows: replace/delete refused...").
    path = ConfigCache.get_path("monitor_file")
    kill_received = False
    try:
        kill_received = scan_requests()
    except Exception as e:
        log("ERROR", "farm", f"Error while scanning farm requests: {e}")
    if kill_received:
        stop_monitor_loop()
        try:
            with locked_json(path) as box:
                box["action"] = "to_delete"
        except Exception as e:
            # Not fatal: the next farm_tick() sees the loop stopped and
            # retries the delete via the branch at the top of this function.
            log("ERROR", "farm", f"Error while clearing monitor.lock on kill: {e}")
        return

    # Heartbeat, two layers: "update_tick" rewritten best effort (one
    # attempt, failure ignored), then os.utime() -- which no reader can
    # refuse. Readers take the newer (monitor_last_tick()).
    try:
        with locked_json(path, retries=1, io_attempts=1) as box:
            data = box["data"] or {}
            if data.get("pid") == os.getpid():  # never touch a taken-over lock
                data["update_tick"] = now()
                box["data"] = data
                box["action"] = "to_write"
    except Exception:
        pass
    try:
        os.utime(path)
    except OSError as e:
        log("ERROR", "farm", f"Could not refresh the monitor heartbeat: {e}")

    try:
        scan_processes()
    except Exception as e:
        log("ERROR", "farm", f"Error while polling farm processes: {e}")

    try:
        scan_queue(project_root)
    except Exception as e:
        log("ERROR", "farm", f"Error while advancing the farm queue: {e}")

    try:
        farm_housekeeping()
    except Exception as e:
        log("ERROR", "farm", f"Error during farm housekeeping: {e}")


# Finished jobs (render, block split, preview) leave actives/ on their own
# this long after ending -- failed ones stay until someone looks at them.
# Archived logs are deleted past ARCHIVE_LOG_DAYS (the job files, a few KB
# each, are kept: render_history.json has the outcome anyway). Both
# overridable in project_config.json ("farm": {"auto_archive_hours",
# "archive_log_days"}, 0 = never). See NOTES.md, "Farm logs: kept small".
AUTO_ARCHIVE_HOURS = 24
ARCHIVE_LOG_DAYS = 14
_HOUSEKEEPING_INTERVAL = 3600  # seconds
_last_housekeeping = 0.0
_FINISHED_STAGES = ("finished", "split_finished", "preview_finished")


def farm_housekeeping(force: bool = False) -> None:
    """Monitor, at most once per _HOUSEKEEPING_INTERVAL: archive finished
    jobs older than AUTO_ARCHIVE_HOURS, delete archived logs older than
    ARCHIVE_LOG_DAYS. Never raises (called from the farm timer)."""
    global _last_housekeeping
    now_t = time.monotonic()
    if not force and now_t - _last_housekeeping < _HOUSEKEEPING_INTERVAL:
        return
    _last_housekeeping = now_t
    config = ConfigCache.get()
    try:
        hours = json_get(config, "farm.auto_archive_hours", AUTO_ARCHIVE_HOURS)
        if hours:
            moved = _archive_finished_jobs(hours)
            if moved:
                log("INFO", "farm", f"{moved} finished job(s) moved to archives/.")
    except Exception as e:
        log("ERROR", "farm", f"Auto-archive failed: {e}")
    try:
        _compact_ended_logs()
    except Exception as e:
        log("ERROR", "farm", f"Log compaction failed: {e}")
    try:
        days = json_get(config, "farm.archive_log_days", ARCHIVE_LOG_DAYS)
        if days:
            purged = _purge_archived_logs(days)
            if purged:
                log(
                    "INFO",
                    "farm",
                    f"{purged} archived log(s) older than {days} days deleted.",
                )
    except Exception as e:
        log("ERROR", "farm", f"Archived logs purge failed: {e}")


def _archive_finished_jobs(hours: float) -> int:
    """archive() every job of actives/ that ended well (_FINISHED_STAGES,
    then "archived") more than `hours` ago. Returns how many moved."""
    moved = 0
    limit = now(False) - timedelta(hours=hours)
    for job_path in ConfigCache.get_path("farm_actives").glob("job_*.json"):
        data = read_json_quiet(job_path) or {}
        stages = data.get("stage_history") or []
        if len(stages) < 2 or stages[-1].get("stage") != "archived":
            continue
        if stages[-2].get("stage") not in _FINISHED_STAGES:
            continue
        try:
            if datetime.fromisoformat(stages[-1]["at"]) > limit:
                continue
            archive(job_path)
            moved += 1
        except (KeyError, ValueError, OSError):
            continue
    return moved


def _compact_ended_logs() -> None:
    """compact_log() every big log in requests/ whose job has ended (at a
    terminal stage, or gone from actives/) -- here, on the monitor, rather
    than on whichever workstation clicks Archive later. Never a log of a
    job still in flight: a worker may be writing it."""
    actives = ConfigCache.get_path("farm_actives")
    try:
        entries = list(os.scandir(ConfigCache.get_path("farm_requests")))
    except OSError:
        return
    for entry in entries:
        if not (entry.name.startswith("request_job_") and entry.name.endswith(".log")):
            continue
        try:
            if entry.stat().st_size <= LOG_KEEP_BYTES:
                continue
        except OSError:
            continue
        # request_<job_id>.log or request_<job_id>_<uuid>.log
        job_id = "_".join(entry.name[len("request_") : -len(".log")].split("_")[:2])
        job_path = actives / f"{job_id}.json"
        data = read_json_quiet(job_path)
        if data is None and job_path.exists():
            continue  # unreadable right now (mid-replace): not known to be over
        stages = (data or {}).get("stage_history") or [{}]
        if data and stages[-1].get("stage") not in ("archived", "orphaned"):
            continue
        compact_log(Path(entry.path))


def _purge_archived_logs(days: float) -> int:
    """Delete the logs in queue/archives/ last written more than `days`
    ago. Returns how many."""
    purged = 0
    limit = time.time() - days * 86400
    try:
        entries = list(os.scandir(ConfigCache.get_path("farm_archives")))
    except OSError:
        return 0
    for entry in entries:
        try:
            if entry.name.endswith(".log") and entry.stat().st_mtime < limit:
                os.remove(entry.path)
                purged += 1
        except OSError:
            continue
    return purged


def stop_monitor_loop() -> None:
    """Flip the running flag. The next farm_tick call (already scheduled)
    sees the mismatch, clears monitor.lock if it owns it, and deregisters
    itself by returning None."""

    set_running_project(None)
    from .dispatch import _active_processes

    for job_id, procs in list(_active_processes.items()):
        for proc, ip in procs:
            if ip != "local":
                log(
                    "WARNING",
                    "farm",
                    f"Job {job_id} was rendering on {ip} -- remote process may still be running.",
                )
            try:
                proc.terminate()  # SIGTERM first, lets the process close cleanly
                proc.wait(timeout=5)  # give it 5s to exit
            except subprocess.TimeoutExpired:
                proc.kill()  # SIGKILL if it's still hanging around
            except Exception as e:
                log(
                    "WARNING",
                    "farm",
                    f"Could not terminate process for job {job_id}: {e}",
                )
    _active_processes.clear()


def monitor_request(request_name: str, data: dict) -> None:
    """Write a single request file under config/farm/incoming/."""
    try:
        request_path = ConfigCache.get_path("farm_incomings") / request_name
        request_path.parent.mkdir(parents=True, exist_ok=True)
        with locked_json(request_path) as box:
            box["data"] = data
            box["action"] = "to_write"
    except Exception as e:
        raise PipelineError(f"Failed to write farm request: {e}")


def request_monitor_kill(user: str = "unknown") -> None:
    """Ask the current monitor (on whichever machine is running it) to stop.
    Manual only -- never triggered automatically on a stale heartbeat."""
    try:
        nw = now(False)
        data = get_user_data(user) | {"time": nw.isoformat()}
        name = f"kill_{str(nw.timestamp()).replace('.', '')}.json"
        monitor_request(name, data)
        log("INFO", "farm", f"Kill request submitted by {data['user']}.")
    except Exception as e:
        log("ERROR", "farm", f"Error during farm tick: {e}")


def _file_key(filepath: str, prerender_script: str, shot_override: str = "") -> str:
    """Hash on file + prerender script + shot_override (if any) -- the
    request's dedup key. The project-relative path, not resolve(): that
    was S:\\... on the file server and \\\\host\\share\\... elsewhere, so the
    same file got another id per machine and a double submit (a split on
    the farm host, a resubmit from a workstation) was never caught."""
    key = f"{to_relative(filepath)}|{prerender_script}".lower()
    if shot_override:
        key += f"|{shot_override}".lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def job_request(
    filepath: Path,
    *,
    user: str = "unknown",
    priority: int = 10,
    render_mode: str = "auto",
    assigned_machines: list | None = None,
    increment: bool = True,
    prerender_script: str = "default",
    overrided_frame_range: tuple[str, str] = ("n", "n"),
    shot_override: str = "",
    only_shots: list[int] | None = None,
) -> None:
    """Submit a render job request, picked up by scan_requests(). shot_override
    (e.g. "sh045") routes output to shots/<sequence>/<shot_override>/.
    only_shots restricts a block's split to these shot numbers."""

    assigned_machines = assigned_machines if assigned_machines is not None else []
    try:
        data = get_user_data(user) | {
            "submitted_at": now(),
            "filepath": str(to_relative(filepath)),
            "priority": priority,
            "render_mode": render_mode,
            "assigned_machines": assigned_machines,
            "increment": increment,
            "prerender_script": prerender_script,
            "overrided_frame_range": overrided_frame_range,
            "shot_override": shot_override,
            "only_shots": only_shots or [],
            "file_frame_range": (0, 0),
            "resolved_frame_range": (0, 0),
        }
        name = f"job_{_file_key(str(filepath), prerender_script, shot_override)}.json"

        monitor_request(name, data)
        log(
            "INFO",
            "farm",
            f"Job request submitted by {data['user']}: {data['filepath']} (priority={priority}).",
        )
    except Exception as e:
        raise PipelineError(f"Failed to submit job request: {e}")


def _preview_key(scope: str, label: str) -> str:
    """Hash for a preview job's dedup key."""
    key = f"preview|{scope}|{label}".lower()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def request_preview_compile(
    *,
    user: str = "unknown",
    scope: str,
    label: str,
    sources: list[tuple[str, Path]],
    output_path: Path,
    priority: int = 10,
    compilation_settings: str = "default",
) -> None:
    """Submit a preview compile request, picked up by scan_requests().
    sources: (shot_label, mp4) pairs, already resolved. label: the block
    file or sequence folder -- stored (and hashed) project-relative."""
    label = to_relative(label)
    try:
        data = get_user_data(user) | {
            "initial_stage": "preview_queued",
            "submitted_at": now(),
            "filepath": label,
            "priority": priority,
            "scope": scope,
            "sources": [[label, str(to_relative(mp4))] for label, mp4 in sources],
            "output_path": str(to_relative(output_path)),
            "compilation_settings": compilation_settings,
        }
        name = f"job_{_preview_key(scope, label)}.json"

        monitor_request(name, data)
        log("INFO", "farm", f"Preview compile requested by {data['user']}: {label}.")
    except Exception as e:
        raise PipelineError(f"Failed to submit preview request: {e}")


def job_cancel_request(*, job_id: str, target_uuid: str, user: str = "unknown") -> None:
    """Ask a specific worker to cancel its in-progress render for job_id.

    Keyword-only: job_id and target_uuid are both hex-hash strings, a
    positional call risks silently swapping them."""
    path = ConfigCache.get_path("farm_requests") / f"cancel_{job_id}_{target_uuid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_json(path) as box:
        box["data"] = get_user_data(user) | {"job_id": job_id, "at": now()}
        box["action"] = "to_write"


def archive(job_path: Path) -> None:
    """Move a finished/failed job file, and its per-worker render logs, from
    active/ to archives/. Manual only: reaching "archived" in stage_history
    is just a marker so scan_queue() stops touching it -- the actual move is
    a dashboard button, a job left in active/ past that is harmless clutter."""
    archives_dir = ConfigCache.get_path("farm_archives")
    archives_dir.mkdir(parents=True, exist_ok=True)

    job_id = job_path.stem
    # request_<job_id>.log (this machine's stages) + request_<job_id>_<uuid>.log
    # (each worker's render) -- job ids are fixed-length hashes, no prefix clash.
    for log_file in ConfigCache.get_path("farm_requests").glob(
        f"request_{job_id}*.log"
    ):
        compact_log(log_file)  # up to 36 MB of render progress otherwise
        try:
            log_file.replace(archives_dir / log_file.name)
        except OSError:
            pass
    # Each machine's frames-written record: only read while the render is
    # judged (queue._note_frames()), nothing to keep.
    discard_saved_frames(job_id)

    # replace(), not rename(): a re-rendered file reuses its job id (hash of
    # file + preset + shot), so its previous run's archive is often already
    # there -- rename() overwrites it on Linux/macOS but raises on Windows
    # (WinError 183). The previous run is still in render_history.json.
    job_path.replace(archives_dir / job_path.name)


# The job Farm monitoring shows in detail: read once, on click
# (load_job_details()), never from draw().
_job_details: dict = {}
# Where that job's file was found, and its logs (archive() moves both).
_job_files: dict = {"path": None, "logs": []}


def load_job_details(job_id: str) -> dict | None:
    """Read a job's file -- active/, else archives/ -- and list its logs
    into the detail cache. None, cache emptied, if it's in neither."""
    _job_details.clear()
    _job_files.update(path=None, logs=[])
    for folder in ("farm_actives", "farm_archives"):
        path = ConfigCache.get_path(folder) / f"{job_id}.json"
        data = read_json_quiet(path)
        if data:
            _job_details.update(data)
            _job_files["path"] = path
            # request_<job_id>.log (this machine's stages) and
            # request_<job_id>_<uuid>.log (each worker's render).
            pattern = f"request_{job_id}*.log"
            _job_files["logs"] = sorted(
                log_file
                for logs in ("farm_requests", "farm_archives")
                for log_file in ConfigCache.get_path(logs).glob(pattern)
            )
            return data
    return None


def get_job_details() -> dict:
    """The job last read by load_job_details()."""
    return _job_details


def get_job_details_path() -> Path | None:
    """The file load_job_details() read that job from."""
    return _job_files["path"]


def get_job_details_logs() -> list[Path]:
    """That job's log files, as found by load_job_details()."""
    return _job_files["logs"]


def recover_interrupted_jobs() -> None:
    """Called once at monitor launch, for jobs left at a local *_start stage
    by a previous monitor that went away (crash, kill): adopt the process
    by PID if it still runs on this machine, else rewind the job so the
    queue redoes the stage (resume_interrupted_stage()). render_start is
    the workers' side. See NOTES.md, "Crash recovery"."""
    from .dispatch import _active_processes
    from .queue import resume_interrupted_stage

    me = get_machine_id()
    for job_path in ConfigCache.get_path("farm_actives").glob("job_*.json"):
        try:
            with locked_json(job_path) as box:
                data = box["data"] or {}
                history = data.get("stage_history") or []
                if not history or data.get("job_id") in _active_processes:
                    continue
                stage = history[-1]["stage"]
                if not stage.endswith("_start") or stage == "render_start":
                    continue

                recorded = data.get("local_processes") or {}
                alive = [
                    (pid, hint)
                    for pid, hint in recorded.get("pids", [])
                    if recorded.get("machine") == me and process_alive(pid, hint)
                ]
                if alive:
                    _active_processes[data["job_id"]] = [
                        (AdoptedProcess(pid, hint), "local") for pid, hint in alive
                    ]
                    log(
                        "WARNING",
                        "farm",
                        f"Job {data['job_id']}: {stage} still running after a restart "
                        f"(pid {', '.join(str(pid) for pid, _ in alive)}) -- waiting for it.",
                    )
                elif resume_interrupted_stage(data, "monitor restarted"):
                    box["action"] = "to_write"
        except Exception as e:
            log("ERROR", "farm", f"Could not recover {job_path.name}: {e}")
