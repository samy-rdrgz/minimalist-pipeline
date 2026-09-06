"""Worker role: register/heartbeat this machine, execute render requests, apply render presets."""

import importlib.util
import os
import subprocess
from datetime import datetime
from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    PipelineError,
    get_active_project_root,
    get_machine_id,
    get_user,
    get_user_data,
    locked_json,
    log,
    now,
    to_absolute,
)
from .loop import register_farm_loop

STALE_WORKER_SECONDS = 15


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

        box["data"] = get_user_data(get_user()) | {
            "status": "idle",
            "current_job": None,
            "last_heartbeat": now(),
        }
        box["action"] = "to_write"
        register_farm_loop(get_active_project_root())
    bpy.context.scene.is_worker = True
    return True


def is_blender_worker() -> bool:
    """Whether this Blender process (pid) owns this machine's worker file.
    False (no crash) if there's no active project to resolve the file
    against -- no project, no worker role."""
    try:
        worker_path = _worker_path()
    except PipelineError:
        return False
    pid = os.getpid()
    try:
        with locked_json(worker_path) as box:
            data = box["data"] or {}
            bpy.context.scene.is_worker = True
            return data.get("pid") == pid
    except Exception:
        bpy.context.scene.is_worker = False
        return False


def kill_worker() -> bool:
    """Remove this machine's worker file, if this process owns it. True if
    this machine ends up with no worker role (removed or none to begin
    with), False if the entry belongs to another process and was left as-is."""
    try:
        worker_path = _worker_path()
    except PipelineError:
        return True  # No active project -- nothing to have been worker for.
    if not worker_path.exists():
        bpy.context.scene.is_worker = False
        return True
    pid = os.getpid()
    uuid = get_machine_id()
    with locked_json(worker_path) as box:
        data = box["data"] or {}
        owned = data.get("pid", "") == pid and data.get("uuid", "") == uuid
        if owned:
            box["action"] = "to_delete"
    bpy.context.scene.is_worker = False
    return owned


def update_worker_heartbeat():
    """Refresh this machine's worker last_heartbeat timestamp."""
    path = _worker_path()
    with locked_json(path) as box:
        box["data"]["last_heartbeat"] = now()
        box["action"] = "to_write"


def scan_workers():
    """Return {uuid: worker_data} for every worker with a recent heartbeat."""
    workers = {}
    workers_dir = _worker_path(as_dir=True)
    if not workers_dir.exists():
        return workers
    for w in _worker_path(as_dir=True).glob("worker_*.json"):
        with locked_json(w) as box:
            data = box["data"] or {}
            if _heartbeat_age(data.get("last_heartbeat", "")) < STALE_WORKER_SECONDS:
                workers[data.get("uuid", "unknown")] = data
    return workers


def scan_render_requests(target_uuid: str = "") -> dict:
    """Return {filename: data} for pending render requests, optionally filtered to target_uuid."""
    requests = {}
    path = ConfigCache.get_path("farm_requests")
    if not path.exists():
        return requests
    for r in path.glob(
        f"request_*_{target_uuid}.json" if target_uuid else "request_*.json"
    ):
        with locked_json(r) as box:
            requests[r.name] = box["data"]
    return requests


def update_worker(dict: dict):
    """Merge dict into this machine's worker file and refresh its heartbeat."""
    worker_path = _worker_path()
    with locked_json(worker_path) as box:
        box["data"] = (box["data"] or {}) | dict | {"last_heartbeat": now()}
        box["action"] = "to_write"


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
        data = box["data"] or data
        try:
            log_path = request_path.parent / f"{request_path.stem}.log"
            project_root = get_active_project_root()
            templates_dir = Path(__file__).parent.parent / "templates"
            entry = templates_dir / "worker_render_entry.py"
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
                    "--python",
                    str(entry),
                    "--",
                    "--job-id",
                    data["job_id"],
                    "--preset",
                    data.get("prerender_script", ""),
                ],
                stdout=open(log_path, "wb"),
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
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
            "current_job": str(request_path),
            "current_file": data["filepath"],
        }


def worker_tick():
    """Per-tick worker work: heartbeat, cancel/finished-process bookkeeping,
    then pick up a render request if idle. Never raises: called from the
    farm_tick timer, an uncaught exception here would silently deregister it."""
    try:
        update_worker_heartbeat()
        scan_cancel_requests()
        scan_worker_processes()

        with locked_json(_worker_path()) as box:
            data = box["data"] or {}
            if data.get("status") != "idle":
                return  # already busy, nothing to do this tick
            else:
                result = execute_render_request()
                box["data"] = data | result
                box["action"] = "to_write" if result else ""
                return
    except Exception as e:
        log("ERROR", "farm", f"Error during worker tick: {e}")


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

        update_worker(
            {
                "status": "idle",
                "current_job": None,
                "last_job_result": {
                    "job_id": job_id,
                    "success": ret == 0,
                    "at": now(),
                },
            }
        )

    for job_id in finished:
        _worker_active_processes.pop(job_id, None)


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
                        p.terminate()
                        try:
                            p.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            p.kill()
                        update_worker(
                            {
                                "status": "idle",
                                "current_job": None,
                                "last_job_result": {
                                    "job_id": job_id,
                                    "success": False,
                                    "cancelled": True,
                                    "at": now(),
                                },
                            }
                        )
                        _worker_active_processes.pop(job_id, None)
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
        target = scene
        for part in path:
            target = getattr(target, part)
        try:
            setattr(target, attr, value)
        except Exception:
            log(
                "WARNING",
                "farm",
                f"Invalid render preset key '{dotted_key}' = {value!r}.",
            )


def apply_custom_preset(preset_name: str, scene, job_id: str) -> None:
    """Apply a per-job render preset onto scene. Run AFTER apply_default_render_settings. Looks for a .py first
    (contract: override(scene)), then a .json (flat key/value
    overrides). Any error here is caught: a broken preset must never
    prevent the save+quit that follows."""
    if not preset_name:
        return

    base = ConfigCache.get_path("presets") / preset_name
    py_path = base.with_suffix(".py")
    json_path = base.with_suffix(".json")
    job_path = ConfigCache.get_path("farm_actives") / f"{job_id}.json"

    try:
        if py_path.exists():
            spec = importlib.util.spec_from_file_location("pipeline_prerender", py_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with locked_json(job_path) as box:
                data = box["data"] or {}
                module.override(scene, data)
        elif json_path.exists():
            with locked_json(json_path) as box:
                overrides = box["data"] or {}
                _apply_flat_overrides(scene, overrides)
        else:
            log("WARNING", "farm", f"Render preset '{preset_name}' not found.")
    except Exception as e:
        log("WARNING", "farm", f"Render preset '{preset_name}' failed: {e}")
