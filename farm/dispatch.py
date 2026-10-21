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
    read_json_quiet,
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
        data = "".join(
            line for i, line in enumerate(lines) if i not in dropped
        ).encode("utf-8")
        if len(data) > LOG_KEEP_BYTES:
            tail = LOG_KEEP_BYTES - _LOG_KEEP_HEAD
            cut = len(data) - _LOG_KEEP_HEAD - tail
            data = (
                data[:_LOG_KEEP_HEAD]
                + f"\n[... {cut} bytes cut ...]\n".encode("utf-8")
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


from .workers import render_request


def max_workers_per_job() -> int:
    """Project setting farm.max_workers_per_job (Edit project): the most
    machines one job renders on at once in auto/placeholder mode, joining
    workers included. 0: no limit."""
    value = json_get(ConfigCache.get(), "farm.max_workers_per_job", 0)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def machines_for(job_data: dict, idle: dict) -> list[str]:
    """The idle machines (idle_machines()) this job may render on: all of
    them, or only its assigned ones."""
    assigned = job_data.get("assigned_machines") or []
    return [uuid for uuid in idle if not assigned or uuid in assigned]


# Jobs whose wait for a machine is already in the log: one line when a job
# starts waiting, not one per job per tick (it was 99 % of the pipeline log
# -- the Farm popup already shows "waiting for a worker"). Memory only.
_waiting_logged: set[str] = set()


def note_waiting(job_data: dict) -> None:
    """Log that a set-up job waits for a machine -- once per wait."""
    job_id = job_data.get("job_id", "")
    if job_id in _waiting_logged:
        return
    _waiting_logged.add(job_id)
    log("INFO", "farm", f"Job {job_id}: waiting for an idle machine.")


def render_dispatch(job_path: Path, idle: dict) -> None:
    """Launch the render for an already-set-up job (output_path and
    resolved_frame_range in its file, stage setup_finished). idle:
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

        available = machines_for(job_data, idle)
        if not available:
            note_waiting(job_data)
            return  # stays in setup_finished, retried on the next tick
        _waiting_logged.discard(job_data.get("job_id", ""))

        fs, fe = job_data.get("resolved_frame_range", (None, None))
        # refill_single: frames corrupted or written by two machines, sent
        # out again by the frame check (queue._send_back_bad_frames()) -- on
        # one machine, not one that failed this job while another is free.
        refill_single = bool(job_data.get("refill_single"))
        if refill_single:
            failed = set(job_data.get("failed_machines") or [])
            available = [u for u in available if u not in failed] or available
        single_machine = (
            refill_single
            or job_data["render_mode"] == "single"
            or (
                job_data["render_mode"] == "auto"
                and render_mode_auto(job_data["filepath"]) == "single"
            )
        )
        cap = 1 if single_machine else max_workers_per_job()
        used = available[:cap] if cap else available

        cmd_flags = ["-s", str(fs), "-e", str(fe)]
        # Identifies this render, not the job (whose id a re-render reuses);
        # echoed back in the worker's last_job_result -- see NOTES.md,
        # "Re-rendering a file".
        job_data["dispatch_id"] = uuid4().hex[:12]
        for uuid in used:
            render_request(job_data, uuid, cmd_flags)
            idle.pop(uuid, None)

        job_data["used_machines"] = used
        history.append({"stage": "render_start", "at": now()})
        box["action"] = "to_write"


# Until a frame of the render is timed: a worker that turns idle joins a
# render already in progress only while it would get more frames than this.
JOIN_MIN_FRAMES_LEFT = 10


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


def free_frames(job_data: dict, project_root: Path) -> list[int] | None:
    """Frames of the job's range with no file at all -- not even a
    placeholder (an empty file = a frame some machine already took). None
    if the job has no output to look at yet."""
    paths = frame_paths(job_data, project_root)
    if paths is None:
        return None
    try:
        existing = {entry.name for entry in paths[0].parent.iterdir()}
    except OSError:
        existing = set()
    start = int(job_data["resolved_frame_range"][0])
    return [start + i for i, path in enumerate(paths) if path.name not in existing]


def _render_timing(job_data: dict, machines: list) -> dict:
    """The render's pace from its machines' saved_frames_path() records:
    {"frame": the job's mean seconds per frame (None if nothing timed),
    "startup": a machine's mean time to start rendering (open the .blend
    -- else one frame's time), "pace": frames per second of these machines
    together (each one's last frames, the job's mean for one not timed),
    "behind": the first frame every one of them is past (this render's
    lines; one with none yet starts at the range's start)}."""
    from .workers import frame_seconds, parse_saved, startup_seconds

    texts = {}
    prefix = f"request_{job_data['job_id']}_"
    for path in ConfigCache.get_path("farm_requests").glob(f"{prefix}*.saved"):
        try:
            texts[path.stem[len(prefix) :]] = path.read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            continue
    seconds = {uuid: frame_seconds(text) for uuid, text in texts.items()}
    timed = [s for secs in seconds.values() for s in secs]
    frame = sum(timed) / len(timed) if timed else None
    start = int(job_data["resolved_frame_range"][0])
    timing = {"frame": frame, "startup": frame, "pace": 0.0, "behind": start}
    if frame is None:
        return timing
    startups = [s for text in texts.values() for s in startup_seconds(text, frame)]
    if startups:
        timing["startup"] = sum(startups) / len(startups)
    positions = []
    for uuid in machines:
        recent = seconds.get(uuid, [])[-_PACE_FRAMES:]
        timing["pace"] += 1 / (sum(recent) / len(recent) if recent else frame)
        done = [
            f
            for d, f, _ in parse_saved(texts.get(uuid, ""))
            if d == job_data.get("dispatch_id") and f is not None
        ]
        positions.append(max(done) if done else start)
    # Nobody on it: every free frame is behind.
    end = int(job_data["resolved_frame_range"][1])
    timing["behind"] = min(positions) if positions else end + 1
    return timing


# A machine's pace: the mean of its latest frames, this many (same as the
# popup's time left, loop._PACE_FRAMES).
_PACE_FRAMES = 10


def _joiners_wanted(
    job_data: dict, free: list[int], machines: list, offered: int
) -> int:
    """How many of `offered` idle workers joining this render helps.
    Every machine walks the range forward: a free frame behind all of them
    (one freed by a "Stop now") is only rendered by one joining -- a joiner
    each. Past those, one more joins while the machines on it, joiners
    included, would still be busy with the free frames ahead longer than it
    takes it to start and render one (_render_timing()). Nothing timed
    yet: JOIN_MIN_FRAMES_LEFT frames each."""
    timing = _render_timing(job_data, machines)
    if timing["frame"] is None:
        return min(offered, len(free) // (JOIN_MIN_FRAMES_LEFT + 1))
    holes = sum(1 for f in free if f < timing["behind"])
    ahead = len(free) - holes
    cost = timing["startup"] + timing["frame"]
    joining = min(offered, holes)
    while joining < offered:
        pace = timing["pace"] + joining / timing["frame"]
        if ahead <= 0 or (pace and ahead / pace <= cost):
            break
        joining += 1
    return joining


def _on_it(job_data: dict) -> int:
    """How many of the job's machines are on its render right now
    (queue._machines_on())."""
    from .queue import _machines_on  # local: queue imports dispatch

    rendering, waiting = _machines_on(job_data)
    return len(rendering) + len(waiting)


def join_running_renders(jobs: list, project_root: Path, idle_by_uuid: dict) -> None:
    """Send each idle worker to a render already in progress before any new
    job gets dispatched: jobs is scan_queue()'s (path, data) list, already in
    priority order. A job is joined only if it renders on several machines
    (not "single", nor an "auto" fallen back to single), the worker is
    allowed on it (no assigned machines, or in the list) and never failed
    it (failed_machines) -- one that left it may come back --, and joining
    helps: a frame free behind every machine on it, or free frames ahead
    for longer than the worker takes to start and render one
    (_joiners_wanted()). The new worker gets the same
    render request (same dispatch_id): placeholders + no overwrite, it only
    renders the frames nobody took. idle_by_uuid: idle_machines() for this
    tick -- joining workers are taken out of it."""
    machines = dict(idle_by_uuid)  # names for the log line
    idle = list(idle_by_uuid)
    for job_path, data in jobs:
        if not idle:
            return
        stages = data.get("stage_history") or []
        if not stages or stages[-1].get("stage") != "render_start":
            continue
        mode = data.get("render_mode", "auto")
        if (
            mode == "single"
            or data.get("refill_single")
            or (mode == "auto" and render_mode_auto(data["filepath"]) == "single")
        ):
            continue
        assigned = data.get("assigned_machines") or []
        # One that failed it (a crash...) is never sent back. One that left
        # it (stopped, quit Blender) and is idle again may come back: idle,
        # no request of it waiting, it's off the render whatever it did.
        failed = set(data.get("failed_machines") or [])
        candidates = [
            u for u in idle if u not in failed and (not assigned or u in assigned)
        ]
        if not candidates:
            continue
        # Project's farm.max_workers_per_job: machines on this render now,
        # joins included -- one that left frees its place.
        cap = max_workers_per_job()
        if cap and _on_it(data) >= cap:
            continue
        free = free_frames(data, project_root)
        if not free:
            continue
        from .queue import _machines_on  # local: queue imports dispatch

        rendering, waiting = _machines_on(data)
        joining = candidates[
            : _joiners_wanted(data, free, rendering + waiting, len(candidates))
        ]
        if not joining:
            continue
        left = len(free)
        with locked_json(job_path) as box:
            job_data = box["data"] or {}
            now_stages = job_data.get("stage_history") or []
            if not now_stages or now_stages[-1].get("stage") != "render_start":
                continue  # moved on meanwhile
            used_now = list(job_data.get("used_machines") or [])
            if cap:
                joining = joining[: max(0, cap - _on_it(job_data))]
            if not joining:
                continue
            fs, fe = job_data["resolved_frame_range"]
            for uuid in joining:
                render_request(job_data, uuid, ["-s", str(fs), "-e", str(fe)])
            job_data["used_machines"] = used_now + [
                u for u in joining if u not in used_now
            ]
            box["action"] = "to_write"
        for uuid in joining:
            idle.remove(uuid)
            idle_by_uuid.pop(uuid, None)
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
    """Whether the most recent placeholder-mode render entry reported
    corrupted frames. Read without a lock (append_render_history() writes
    atomically) -- it was a write lock on every dispatch."""
    data = read_json_quiet(to_absolute(render_history_path(filepath))) or {}
    placeholder_entries = [
        e for e in data.get("entries", []) if e.get("render_mode") == "placeholder"
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
