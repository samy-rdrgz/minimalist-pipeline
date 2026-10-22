"""Launch the actual render commands -- local Popen or SSH, one machine or
several, depending on render_mode."""

import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from ..lib import (
    ConfigCache,
    get_machine_id,
    json_get,
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
        f.write(f"\n===== {stage} {now()} =====\n".encode())
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


# A log kept past its job (a failure, a stop) is read for its start --
# Blender and the add-ons loading, a file that won't open -- and its end --
# the error. In between, Blender's render progress ("Fra:..." -- a line per
# BVH/sample update) made up 99 % of logs of up to 36 MB: dropped but for
# its last lines, then the middle is cut if still too big. See NOTES.md,
# "Farm logs: kept small".
LOG_KEEP_BYTES = 256_000
_LOG_KEEP_HEAD = 32_000
_PROGRESS_LINES_KEPT = 20


def compact_log(path: Path) -> None:
    """Shrink a kept log in place (see above). Best effort: never raises,
    a log left as is just stays big."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        if path.stat().st_size <= LOG_KEEP_BYTES:
            return
        lines = path.read_bytes().decode("utf-8", errors="replace").splitlines(True)
        progress = [i for i, line in enumerate(lines) if line.startswith("Fra:")]
        dropped = set(progress[:-_PROGRESS_LINES_KEPT])
        data = "".join(line for i, line in enumerate(lines) if i not in dropped).encode(
            "utf-8"
        )
        if len(data) > LOG_KEEP_BYTES:
            tail = LOG_KEEP_BYTES - _LOG_KEEP_HEAD
            cut = len(data) - _LOG_KEEP_HEAD - tail
            data = (
                data[:_LOG_KEEP_HEAD]
                + f"\n[... {cut} bytes cut ...]\n".encode()
                + data[-tail:]
            )
        if dropped:
            header = f"[{len(dropped)} render progress lines (Fra:) dropped]\n"
            data = header.encode("utf-8") + data
        tmp.write_bytes(data)
        retry_shared_io(os.replace, tmp, path)
    except Exception as e:
        log("WARNING", "farm", f"Could not compact {path.name}: {e}")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def discard_job_log(job_id: str) -> None:
    """Delete the job's log -- it ended well. Best effort: a log that can't
    be deleted is just left behind (archive() still moves it)."""
    try:
        retry_shared_io(job_log_path(job_id).unlink)
    except FileNotFoundError:
        pass
    except OSError as e:
        log("WARNING", "farm", f"Could not delete log for {job_id}: {e}")


from .chunks import free_chunks
from .workers import render_request


def chunk_size() -> int:
    """Project setting farm.chunk_size (Edit project): frames per chunk, at
    least 1. Read at dispatch only and stored in the job: every worker of a
    render must cut it the same way (chunks.chunk_frames())."""
    value = json_get(ConfigCache.get(), "farm.chunk_size", 5)
    try:
        return max(1, int(value or 5))
    except (TypeError, ValueError):
        return 5


def machines_for(job_data: dict, idle: dict, with_left: bool = False) -> list[str]:
    """The idle machines (idle_machines()) this job may render on: all of
    them, or only its assigned ones -- never one that failed it
    (failed_machines), nor one cancelled off it (left_machines) unless
    with_left: no other job took it this tick."""
    assigned = job_data.get("assigned_machines") or []
    out = set(job_data.get("failed_machines") or [])
    if not with_left:
        out |= set(job_data.get("left_machines") or [])
    return [uuid for uuid in idle if (not assigned or uuid in assigned) and uuid not in out]


def send_render(job_data: dict, machines: list, idle: dict) -> None:
    """A render request of this job (its dispatch_id, its chunk_size) to
    each of these machines: taken out of idle, added to used_machines. The
    caller holds the job's lock and writes it back."""
    fs, fe = job_data["resolved_frame_range"]
    for uuid in machines:
        render_request(job_data, uuid, ["-s", str(fs), "-e", str(fe)])
        idle.pop(uuid, None)
    used = list(job_data.get("used_machines") or [])
    job_data["used_machines"] = used + [u for u in machines if u not in used]


# Jobs whose wait for a machine is already in the log: one line when a job
# starts waiting, not one per job per tick (it was 99 % of the pipeline log
# -- Farm monitoring already shows "waiting for a worker"). Memory only.
_waiting_logged: set[str] = set()


def note_waiting(job_data: dict) -> None:
    """Log that a set-up job waits for a machine -- once per wait."""
    job_id = job_data.get("job_id", "")
    if job_id in _waiting_logged:
        return
    _waiting_logged.add(job_id)
    log("INFO", "farm", f"Job {job_id}: waiting for an idle machine.")


def render_dispatch(job_path: Path, idle: dict, project_root: Path) -> None:
    """Launch the render for an already-set-up job (output_path and
    resolved_frame_range in its file, stage setup_finished): a new
    dispatch_id, the project's chunk_size fixed for it, a request to one
    machine ("single") or to as many as it has chunks to render. idle:
    idle_machines() for this tick -- the machines given the job are taken
    out of it, so the next job of the same tick never gets them too."""
    with locked_json(job_path) as box:
        job_data = box["data"] or {}
        history = job_data.get("stage_history") or []
        if not history or history[-1]["stage"] != "setup_finished":
            return  # moved on since scan_queue() read it (cancel, retry...)

        source = to_absolute(job_data["filepath"])
        if not source.exists():
            # Every worker would fail on it at once ("Cannot read file"):
            # a newer version replaced it, or it was moved by hand.
            history.append(
                {"stage": "render_failed", "at": now(), "reason": "source file missing"}
            )
            box["action"] = "to_write"
            log(
                "ERROR",
                "farm",
                f"Job {job_data.get('job_id')}: {job_data['filepath']} no longer "
                f"exists -- not rendered.",
            )
            return

        # A new render: the machines cancelled off the last one may take it.
        job_data.pop("left_machines", None)
        available = machines_for(job_data, idle)
        if not available:
            note_waiting(job_data)
            return  # stays in setup_finished, retried on the next tick
        _waiting_logged.discard(job_data.get("job_id", ""))

        start, end = (int(x) for x in job_data["resolved_frame_range"])
        size = chunk_size()
        # Frames sent back by the frame check: only their chunks are left.
        missing = missing_frames(job_data, project_root)
        if missing is None:
            missing = list(range(start, end + 1))
        free = free_chunks(start, size, missing, ())
        single_machine = job_data["render_mode"] == "single"
        used = available[: 1 if single_machine else len(free)]

        # Identifies this render, not the job (whose id a re-render reuses);
        # echoed back in the worker's last_job_result -- see NOTES.md,
        # "Re-rendering a file".
        job_data["dispatch_id"] = uuid4().hex[:12]
        job_data["chunk_size"] = size
        job_data["used_machines"] = []
        names = ", ".join((idle.get(u) or {}).get("machine") or u[:8] for u in used)
        send_render(job_data, used, idle)
        history.append({"stage": "render_start", "at": now()})
        log(
            "INFO",
            "farm",
            f"Job {job_data.get('job_id')}: rendering on {names or 'no machine yet'} "
            f"({len(free)} chunk(s) of {size} frames).",
        )
        box["action"] = "to_write"


def frame_paths(job_data: dict, project_root: Path | None) -> list[Path] | None:
    """Every frame file of the job's resolved range, rendered or not. None
    if the job has no output to look at yet."""
    from .post_render import _EXTENSION_MAP  # local: post_render imports dispatch

    output_path = job_data.get("output_path")
    frame_range = job_data.get("resolved_frame_range") or (0, 0)
    if not output_path or not project_root or tuple(frame_range) == (0, 0):
        return None
    pattern = to_absolute(output_path, project_root)
    digits = pattern.name.count("#")
    stem = pattern.name.split("#")[0]
    ext = _EXTENSION_MAP.get(job_data.get("output_extension"), "png")
    start, end = int(frame_range[0]), int(frame_range[1])
    return [
        pattern.parent / f"{stem}{frame:0{digits}d}.{ext}"
        for frame in range(start, end + 1)
    ]


def missing_frames(job_data: dict, project_root: Path) -> list[int] | None:
    """Frames of the job's range not on disk yet -- one listing of the
    folder, not a stat per frame. None if the job has no output to look at
    yet."""
    paths = frame_paths(job_data, project_root)
    if paths is None:
        return None
    try:
        existing = {entry.name for entry in paths[0].parent.iterdir()}
    except OSError:
        existing = set()
    start = int(job_data["resolved_frame_range"][0])
    return [start + i for i, path in enumerate(paths) if path.name not in existing]


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
