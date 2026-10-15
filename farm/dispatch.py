"""Launch the actual render commands -- local Popen or SSH, one machine or
several, depending on render_mode."""

import json
import subprocess
from pathlib import Path
from uuid import uuid4

from ..lib import (
    ConfigCache,
    get_machine_id,
    locked_json,
    log,
    now,
    retry_shared_io,
    to_absolute,
)

_active_processes: dict[str, list[tuple[subprocess.Popen, str]]] = {}


# ---------------------------------------------------------------------------
# Per-job process log
# ---------------------------------------------------------------------------
# Farm subprocesses write to a file, never a PIPE (a full pipe blocks the
# child forever). One log per job for this machine's stages; worker renders
# keep one per machine. See NOTES.md, "Farm subprocess output: files, never
# pipes".


def job_log_path(job_id: str) -> Path:
    """The job's own log, shared by every stage this machine runs for it."""
    return ConfigCache.get_path("farm_requests") / f"request_{job_id}.log"


def popen_logged(cmd: list, job_id: str, stage: str, *, merge_stdout: bool = True):
    """subprocess.Popen with the child's stderr (and stdout, if merge_stdout)
    appended to job_log_path(job_id), after a header naming the stage. The
    parent's own handle is closed right away -- the child has its own copy
    -- so Windows can delete the file once the child exits. Keeps the path
    and the offset where this stage's output starts on the Popen
    (.log_path/.log_offset) for read_process_log()."""
    log_path = job_log_path(job_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as f:
        f.write(f"\n===== {stage} {now()} =====\n".encode("utf-8"))
        f.flush()
        offset = f.tell()
        proc = subprocess.Popen(
            [str(c) for c in cmd],
            stdout=f if merge_stdout else subprocess.DEVNULL,
            stderr=subprocess.STDOUT if merge_stdout else f,
            stdin=subprocess.DEVNULL,
        )
    proc.log_path = log_path
    proc.log_offset = offset
    proc.name_hint = Path(str(cmd[0])).stem.lower()  # "blender", "ffmpeg"
    return proc


def track_local_processes(data: dict, procs: list) -> None:
    """Start tracking a job's local processes: in memory for
    scan_processes(), and in the job's own data (caller writes it back) so
    a monitor restarted after a crash can find them again by PID instead of
    assuming them dead -- see recover_interrupted_jobs()."""
    _active_processes[data["job_id"]] = procs
    data["local_processes"] = {
        "machine": get_machine_id(),
        "pids": [[p.pid, getattr(p, "name_hint", "")] for p, _ in procs],
    }


def read_process_log(proc) -> str:
    """Text a finished popen_logged() process wrote -- its own stage only,
    not the earlier ones in the same job log. "" if none/unreadable."""
    path = getattr(proc, "log_path", None)
    if not path:
        return ""
    try:
        with open(path, "rb") as f:
            f.seek(getattr(proc, "log_offset", 0))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def discard_job_log(job_id: str) -> None:
    """Delete the job's log -- it ended well. Best effort: a log that can't
    be deleted is just left behind (archive() still moves it)."""
    try:
        retry_shared_io(job_log_path(job_id).unlink)
    except FileNotFoundError:
        pass
    except OSError as e:
        log("WARNING", "farm", f"Could not delete log for {job_id}: {e}")


from .workers import render_request, scan_render_requests, scan_workers


def render_dispatch(job_path: Path) -> None:
    """Launch the render for an already-prepared job (output_path/frame_start/
    frame_end already in the JSON, stage_history at least at 'prerender_script').
    """
    global _active_processes
    with locked_json(job_path) as box:
        job_data = box["data"]

        fs, fe = job_data.get("resolved_frame_range", (None, None))
        machines = scan_workers()

        pending = scan_render_requests()
        targeted_uuids = {r["target_uuid"] for r in pending.values()}
        idle_machines = {
            k: v
            for k, v in machines.items()
            if v["status"] == "idle" and k not in targeted_uuids
        }

        if not job_data["assigned_machines"]:
            avaliable_machines = idle_machines
        else:
            avaliable_machines = {
                k: v
                for k, v in idle_machines.items()
                if k in job_data["assigned_machines"]
            }
        if not avaliable_machines:
            log(
                "INFO",
                "farm",
                f"No idle machine for job {job_data.get('job_id')}, will retry.",
            )
            return  # stays in setup_finished, retried on the next tick

        single_machine = job_data["render_mode"] == "single" or (
            job_data["render_mode"] == "auto"
            and render_mode_auto(job_data["filepath"]) == "single"
        )

        cmd_flags = ["-s", str(fs), "-e", str(fe)]
        # Identifies this render, not the job (whose id a re-render reuses);
        # echoed back in the worker's last_job_result -- see NOTES.md,
        # "Re-rendering a file".
        job_data["dispatch_id"] = uuid4().hex[:12]
        if single_machine:
            render_request(job_data, list(avaliable_machines)[0], cmd_flags)
        else:
            for uuid in avaliable_machines:
                render_request(job_data, uuid, cmd_flags)

        job_data["used_machines"] = (
            list(avaliable_machines)
            if not single_machine
            else [list(avaliable_machines)[0]]
        )
        job_data["stage_history"].append({"stage": "render_start", "at": now()})
        box["action"] = "to_write"


# A worker that turns idle joins a render already in progress (rather than
# starting a new job) only while it would still get more frames than this.
JOIN_MIN_FRAMES_LEFT = 10


def frames_not_started(job_data: dict, project_root: Path) -> int | None:
    """Frames of the job's range with no file at all -- not even a
    placeholder (an empty file = a frame some machine already took). None
    if the job has no output to look at yet."""
    from .post_render import _EXTENSION_MAP  # local: post_render imports dispatch

    output_path = job_data.get("output_path")
    frame_range = job_data.get("resolved_frame_range") or (0, 0)
    if not output_path or tuple(frame_range) == (0, 0):
        return None
    pattern = to_absolute(output_path, project_root)
    digits = pattern.name.count("#")
    stem = pattern.name.split("#")[0]
    ext = _EXTENSION_MAP.get(job_data.get("output_extension"), "png")
    try:
        existing = {entry.name for entry in pattern.parent.iterdir()}
    except OSError:
        existing = set()
    start, end = int(frame_range[0]), int(frame_range[1])
    return sum(
        1
        for frame in range(start, end + 1)
        if f"{stem}{frame:0{digits}d}.{ext}" not in existing
    )


def join_running_renders(jobs: list, project_root: Path) -> None:
    """Send each idle worker to a render already in progress before any new
    job gets dispatched: jobs is scan_queue()'s (path, data) list, already in
    priority order. A job is joined only if it renders on several machines
    (not "single", nor an "auto" fallen back to single), the worker is
    allowed on it (no assigned machines, or in the list), and each joining
    worker still has more than JOIN_MIN_FRAMES_LEFT untouched frames for
    itself (78 frames left: up to 7 join). The new worker gets the same
    render request (same dispatch_id): placeholders + no overwrite, it only
    renders the frames nobody took."""
    machines = scan_workers()
    targeted = {r.get("target_uuid") for r in scan_render_requests().values()}
    idle = [
        uuid
        for uuid, w in machines.items()
        if w.get("status") == "idle" and uuid not in targeted
    ]
    for job_path, data in jobs:
        if not idle:
            return
        stages = data.get("stage_history") or []
        if not stages or stages[-1].get("stage") != "render_start":
            continue
        mode = data.get("render_mode", "auto")
        if mode == "single" or (
            mode == "auto" and render_mode_auto(data["filepath"]) == "single"
        ):
            continue
        assigned = data.get("assigned_machines") or []
        used = set(data.get("used_machines") or [])
        candidates = [u for u in idle if u not in used and (not assigned or u in assigned)]
        if not candidates:
            continue
        left = frames_not_started(data, project_root)
        if left is None:
            continue
        joining = candidates[: left // (JOIN_MIN_FRAMES_LEFT + 1)]
        if not joining:
            continue
        with locked_json(job_path) as box:
            job_data = box["data"] or {}
            now_stages = job_data.get("stage_history") or []
            if not now_stages or now_stages[-1].get("stage") != "render_start":
                continue  # moved on meanwhile
            used_now = list(job_data.get("used_machines") or [])
            joining = [u for u in joining if u not in used_now]
            fs, fe = job_data["resolved_frame_range"]
            for uuid in joining:
                render_request(job_data, uuid, ["-s", str(fs), "-e", str(fe)])
            job_data["used_machines"] = used_now + joining
            box["action"] = "to_write"
        for uuid in joining:
            idle.remove(uuid)
        if joining:
            names = ", ".join(
                (machines.get(u) or {}).get("machine") or u[:8] for u in joining
            )
            log(
                "INFO",
                "farm",
                f"Job {data.get('job_id')}: {names} join(s) the render "
                f"({left} frames not started yet).",
            )


def render_mode_auto(filepath: str) -> str | None:
    """Resolve render_mode="auto": fall back to "single" if the last placeholder
    render on this file had corrupted frames, else let the caller decide (None)."""
    if last_render_had_collision(filepath):
        return "single"
    else:
        return None


def render_history_path(filepath: str) -> Path:
    """Path to filepath's .pipeline/render_history.json sidecar."""
    return Path(filepath).parent / ".pipeline" / "render_history.json"


def append_render_history(filepath: str, entry: dict) -> None:
    """Append one completed-job entry to filepath's render_history.json."""
    path = to_absolute(render_history_path(filepath))
    with locked_json(path) as box:
        try:
            data = box["data"] or {"entries": []}
            entries = data.get("entries", [])
        except (json.JSONDecodeError, OSError):
            data = {"entries": []}
        entries.append(entry)
        box["data"] = data
        box["action"] = "to_write"


def last_render_had_collision(filepath: str) -> bool:
    """Whether the most recent placeholder-mode render entry reported corrupted frames."""
    path = to_absolute(render_history_path(filepath))
    if not path.exists():
        return False
    with locked_json(path) as box:
        try:
            data = box["data"] or {}
            entries = data.get("entries", [])
        except (json.JSONDecodeError, OSError):
            return False
        placeholder_entries = [
            e for e in entries if e.get("render_mode") == "placeholder"
        ]
        if not placeholder_entries:
            return False
        return placeholder_entries[-1].get("frames_corrupted", 0) > 0


def local_slot_busy(max_concurrent_local: int = 1) -> bool:
    """Count all live local Popen processes -- render, setup, checks_images,
    compilation alike -- and compare against the limit."""
    global _active_processes
    count = 0
    for procs in _active_processes.values():
        for proc, host in procs:
            if host == "local" and proc.poll() is None:
                count += 1
    return count >= max_concurrent_local
