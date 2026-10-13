"""Monitor role: a single Blender instance owns monitor.lock and ticks the
queue on a timer. No automatic takeover on a stale lock -- manual kill only."""

import hashlib
import os
import subprocess
from datetime import datetime
from pathlib import Path

from ..lib import (
    AdoptedProcess,
    ConfigCache,
    PipelineError,
    get_machine_id,
    get_user_data,
    locked_json,
    log,
    now,
    process_alive,
    to_relative,
)
from .loop import (
    get_running_project,
    monitor_age_status,
    monitor_last_tick,
    register_farm_loop,
    set_running_project,
)
from .queue import scan_processes, scan_queue, scan_requests

_monitor_cache: dict = {
    "status": "unknown",  # "running" | "stale" | "dead"
    "lock_user": "",
    "lock_machine": "",
    "last_tick": None,
    "jobs": [],  # list of per-job snapshots
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
    Read-only: monitor.lock's content never changes while a monitor runs, so
    there's nothing to lock against. A read that fails (network hiccup,
    Windows refusing an open for a moment) keeps the previous answer instead
    of returning False -- farm_tick() stops the whole loop on False, and
    "couldn't check this tick" must never mean "not the monitor anymore"."""
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

    # Each step in its own try: one failing step (typically a file another
    # machine holds open for a moment, see retry_shared_io()) must never
    # skip the others -- a failed heartbeat used to skip scan_processes()/
    # scan_queue() too, freezing every job at its current stage.
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

    # Heartbeat, two layers. The content's "update_tick" is still rewritten
    # every tick -- readable by eye, and what addons older than this read --
    # but best effort only: one lock attempt, one replace attempt, failure
    # ignored, since a reader on another machine holding the file open makes
    # Windows refuse the replace now and then (WinError 5/32, see NOTES.md).
    # The authoritative heartbeat is the file's mtime, bumped by os.utime()
    # right after: attribute-only access, which no reader's open handle can
    # refuse. Readers take the newer of the two (monitor_last_tick()).
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
    request's dedup key."""
    key = f"{Path(filepath).resolve()}|{prerender_script}".lower()
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
    sources: (shot_label, mp4) pairs, already resolved."""
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
        try:
            log_file.rename(archives_dir / log_file.name)
        except OSError:
            pass

    job_path.rename(archives_dir / job_path.name)


def recover_interrupted_jobs() -> None:
    """Called once at monitor launch. A job at a local *_start stage with
    no tracked process means the Blender instance that ran the previous
    monitor went away mid-stage (crash, kill). Its process may well have
    survived -- child processes outlive their parent on every OS -- so:

    - still running on this machine (PID recorded at launch, checked with
      process_alive()): adopt it, and decide once it ends
      (_finish_job_processes() -> resume_interrupted_stage());
    - gone, or recorded on another machine: resume right away -- rewind to
      the stage before, so the queue redoes it (resume_interrupted_stage()).

    render_start is left alone: renders belong to workers, recovered from
    their side (launch_worker() -> "lost" result) and by
    check_render_completion(). Used to mark all of these "orphaned" -- a
    dead end needing a manual resubmit, even when the process had finished
    fine -- and missed preview_start entirely (stuck for good)."""
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
