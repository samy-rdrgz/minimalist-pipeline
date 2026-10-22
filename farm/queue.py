"""Submission queue: incoming requests -> active jobs, scanned every tick by the monitor."""

import datetime
import os
import re
import string
import time
from pathlib import Path

from ..lib import (
    ConfigCache,
    PipelineError,
    get_active_project_root,
    get_machine_id,
    log,
    mark_render_to_check,
    now,
    read_json_quiet,
    retry_shared_io,
    to_absolute,
    to_relative,
)
from .dispatch import (
    _active_processes,
    append_render_history,
    discard_job_log,
    frame_paths,
    free_frames,
    job_log_path,
    join_running_renders,
    local_slot_busy,
    locked_json,
    machines_for,
    note_waiting,
    read_process_log,
    render_dispatch,
)
from .post_render import checks_images, compilation, refresh_shot_thumbnail
from .workers import (
    frame_seconds,
    idle_machines,
    local_render_running,
    parse_saved,
    saved_frames_path,
    scan_workers,
    this_instance_is_worker,
)


def scan_requests() -> bool:
    """Process incoming/: kill requests are consumed here, job requests
    moved to active/ with their stage_history. Returns True if a kill
    request was processed -- the caller (farm_tick) actually stops the loop
    and clears monitor.lock, avoiding a circular dependency between modules."""
    scan_dir = ConfigCache.get_path("farm_incomings")
    active_dir = ConfigCache.get_path("farm_actives")
    kill_received = False

    for i in scan_dir.glob("kill_*.json"):
        if not kill_received:
            try:
                log("INFO", "farm", "Farm stop requested by kill request.")
                kill_received = True
            except Exception as e:
                log("ERROR", "farm", f"Kill request processing error: {e}")

        i.unlink(missing_ok=True)

    if kill_received:
        return kill_received

    active_dir.mkdir(parents=True, exist_ok=True)
    for i in scan_dir.glob("job_*.json"):
        filepath = active_dir / i.name
        try:
            if filepath.exists():
                with locked_json(filepath, read_only=True) as box_existing:
                    existing = box_existing["data"] or {}
                stage = (existing.get("stage_history") or [{}])[-1].get("stage", "")
                if stage not in (
                    "finished",
                    "archived",
                    "orphaned",
                ) and not stage.endswith("failed"):
                    # a job for this exact file+script is already in flight --
                    # never clobber it. The request stays in incoming/ and is
                    # retried next tick, so it gets picked up automatically
                    # once the in-flight job reaches a terminal stage.
                    continue

            with locked_json(i) as box_incoming:
                incoming_data = box_incoming["data"] or {}
                # Transient: a request can name its own first stage (e.g. a
                # preview compile starting at "preview_queued" instead of
                # "queued") -- consumed here, never stored on the job itself.
                first_stage = incoming_data.pop("initial_stage", "queued")
                box_incoming["action"] = "to_delete"

            with locked_json(filepath) as box:
                data = (
                    {"job_id": filepath.stem}
                    | incoming_data
                    | {
                        "stage_history": [{"stage": first_stage, "at": now()}],
                    }
                )
                box["data"] = data
                box["action"] = "to_write"
            log("INFO", "farm", f"Job queued: {to_relative(data['filepath'])}.")
        except Exception as e:
            log("ERROR", "farm", f"Job request error: {e} ({to_relative(filepath)}).")


# Stages a job never moves on from by itself: nothing for scan_queue() to do.
_TERMINAL_STAGES = ("archived", "orphaned")

# job file path -> its mtime when last read at a terminal stage. Such a job
# is skipped without being read again until its file changes (a retry, a
# recompile): they pile up in actives/ until archived, and were re-read --
# under a lock -- every tick.
_terminal_jobs: dict[str, float] = {}


def _job_stage(data: dict) -> str:
    try:
        return data["stage_history"][-1]["stage"]
    except (KeyError, IndexError, TypeError):
        return ""


def _setup_unblocks_idle(data: dict, jobs: list, idle: dict) -> bool:
    """Whether setting up queued job data now, beside this instance's own
    render, puts idle machines to work: some may render it once set up, and
    no job already set up (setup_finished) can take any of them -- those
    left idle after this tick's joins and dispatches."""
    if not machines_for(data, idle):
        return False
    return not any(
        _job_stage(other) == "setup_finished"
        and not other.get("split_into")
        and machines_for(other, idle)
        for _, other in jobs
    )


def read_active_jobs(scan_dir: Path) -> list[tuple[Path, dict]]:
    """(path, data) of every job in actives/ that may still need work,
    read without a lock: writes are atomic (read_json_quiet()), and the
    lock taken here on every job, every tick, was fought over by the setup
    and render subprocesses -- some lost it and rendered without their
    preset -- and its .lock file churn changed actives/'s mtime every tick,
    so the UI re-read every job every refresh. Whatever acts on a job
    re-reads it under its own lock. A job unreadable right now (mid-replace
    on Windows) is just skipped this tick."""
    jobs = []
    seen = set()
    try:
        entries = [
            e
            for e in os.scandir(scan_dir)
            if e.name.startswith("job_") and e.name.endswith(".json")
        ]
    except OSError:
        return jobs
    for entry in entries:
        seen.add(entry.path)
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if _terminal_jobs.get(entry.path) == mtime:
            continue
        data = read_json_quiet(entry.path)
        if not data:
            continue
        if _job_stage(data) in _TERMINAL_STAGES:
            _terminal_jobs[entry.path] = mtime
            continue
        _terminal_jobs.pop(entry.path, None)
        jobs.append((Path(entry.path), data))
    for path in set(_terminal_jobs) - seen:
        del _terminal_jobs[path]
    return jobs


def scan_queue(project_root: Path) -> None:
    """Advance every active job by one step according to its current stage."""
    jobs = read_active_jobs(ConfigCache.get_path("farm_actives"))
    jobs.sort(
        key=lambda x: (
            -int(x[1].get("priority", 10) or 0),  # highest priority first
            x[1].get("submitted_at", ""),  # then oldest first
        )
    )

    # Idle machines, once for the whole tick: joining and dispatching take
    # theirs out of it.
    try:
        idle = idle_machines()
    except Exception as e:
        log("ERROR", "farm", f"Could not list idle machines: {e}")
        idle = {}
    if this_instance_is_worker() and any(
        _job_stage(data) == "queued" for _, data in jobs
    ):
        # A setup waits for this instance's own render to end
        # (local_render_running()): renders of hours held the whole queue
        # back. Keep it off new renders until the waiting setups are done.
        idle.pop(get_machine_id(), None)

    # Before any new job: idle workers first reinforce renders in progress.
    try:
        join_running_renders(jobs, project_root, idle)
    except Exception as e:
        log("ERROR", "farm", f"Could not send idle workers to running renders: {e}")
    for job, data in jobs:
        try:
            config = ConfigCache.get()
            stage = data["stage_history"][-1]["stage"]

            pass_stage = [
                "setup_start",
                "checks_images_start",
                "compilation_start",
                "preview_start",
                "finished",
            ]
            if stage in pass_stage:
                pass

            elif stage == "queued":
                # Setup also waits for a render this same instance runs as a
                # worker: both load the whole .blend. Only setup -- the
                # ffmpeg stages are light and must not queue behind a whole
                # render (see NOTES.md, "Re-rendering a file..."). Unless
                # machines sit idle with nothing else to take: then it runs
                # alongside, the .blend loaded twice for the setup's length
                # rather than the farm held back for the whole render.
                if not local_slot_busy() and (
                    not local_render_running()
                    or _setup_unblocks_idle(data, jobs, idle)
                ):
                    from .setup import run_render_setup

                    run_render_setup(data["job_id"], config)

            elif stage == "preview_queued":
                # Pure ffmpeg, not a render job.
                if not local_slot_busy():
                    from .post_render import run_preview_compile

                    run_preview_compile(data["job_id"], project_root)

            elif stage in ("preview_finished", "preview_failed"):
                # Before the generic "*failed" branch below.
                mark_stage(job, "archived")
                if stage == "preview_finished":
                    discard_job_log(data["job_id"])

            elif stage == "setup_finished":
                # A block fans out into one job per shot instead of rendering itself.
                if data.get("split_into"):
                    mark_stage(job, "split_finished")
                elif machines_for(data, idle):
                    render_dispatch(job, idle)
                else:
                    note_waiting(data)  # no lock, no disk: nothing free
            elif stage == "split_finished":
                construct_split_history(data)
                mark_stage(job, "archived")
                discard_job_log(data["job_id"])  # the shots carry on as their own jobs
            elif stage == "render_start":
                check_render_completion(job, project_root, data)
            elif stage == "render_finished":
                if not local_slot_busy():
                    checks_images(job)

            elif stage == "checks_images_finished":
                if not local_slot_busy():
                    compilation(
                        project_root=project_root,
                        job_path=job,
                        compilation_settings=data.get("compilation_settings", None),
                    )

            elif stage == "compilation_finished":
                # Waits for its artist's check in Project monitoring. Never
                # finished without it: a failed write is retried next tick.
                if data.get("output_path") and not _flag_to_check(
                    job, data, project_root
                ):
                    continue
                refresh_shot_thumbnail(data, project_root)
                mark_stage(job, "finished")
                # A recompile rendered nothing: its render is already in
                # render_history.json.
                if not _is_recompile(data):
                    construct_history(data, status="finished")
                mark_stage(job, "archived")
                discard_saved_frames(data["job_id"])
                # Ended well -- unless the frame check flagged corrupted
                # frames: that list only lives in the log, keep it.
                if not data.get("frames_corrupted"):
                    discard_job_log(data["job_id"])

            elif stage.endswith("failed"):
                construct_history(data, status="failed")
                mark_stage(job, "archived")

            else:
                log(
                    "WARNING",
                    "farm",
                    f"Unknown stage '{stage}' for job {data.get('job_id')}.",
                )

        except Exception as e:
            log("ERROR", "farm", f"Active job error: {e} ({job.name}).")


# Where a job goes when the process running its *_start stage was lost (a
# crash of the Blender instance tracking it) -- every one of these stages
# is safe to redo: ffmpeg overwrites its own output, and setup is checked
# on disk first (see resume_interrupted_stage()). render_start isn't here:
# a render runs on workers, over once none of them is on it any more --
# see check_render_completion().
_RESUME_STAGE = {
    "checks_images_start": "render_finished",
    "compilation_start": "checks_images_finished",
    "preview_start": "preview_queued",
}


# Where a failed job restarts on a retry: the stage before the one that
# failed. Same output folder, frame range and preset -- no new increment.
_RETRY_STAGE = {
    "setup_failed": "queued",
    "render_failed": "setup_finished",
    "checks_images_failed": "render_finished",
    "compilation_failed": "checks_images_finished",
}
RETRYABLE_STAGES = frozenset(_RETRY_STAGE)


def failed_stage(data: dict) -> str | None:
    """The *_failed stage a job ended on (before "archived"), if retryable."""
    stages = [s.get("stage") for s in data.get("stage_history") or []]
    while stages and stages[-1] == "archived":
        stages.pop()
    return stages[-1] if stages and stages[-1] in _RETRY_STAGE else None


def retry_job(data: dict, project_root: Path) -> str | None:
    """Rewind a failed job to _RETRY_STAGE so the queue runs it again.
    Mutates data (caller writes it back); returns the stage resumed to, or
    None if it didn't fail. A render retry first deletes the empty frames
    left by the failed one (a placeholder is skipped, never re-rendered),
    and is pointed at the workers that didn't fail it."""
    failed = failed_stage(data)
    if not failed:
        return None
    source = data.get("filepath")
    if source and not to_absolute(source, project_root).exists():
        # Every worker would fail at once on it: replaced by a newer
        # version (a block's old -stable), or moved by hand.
        raise PipelineError(
            f"{source} no longer exists -- submit the current version instead."
        )
    target = _RETRY_STAGE[failed]
    if failed == "render_failed" and frames_complete(data, project_root):
        # Rendered in full by the other machines: nothing left to render.
        target = "render_finished"
    elif failed == "render_failed":
        if data.get("output_path"):
            _delete_placeholders(project_root / Path(data["output_path"]).parent)
        _reassign_away_from_failed(data)
    data.pop("rendered_by", None)
    data.pop("local_processes", None)
    data.pop("refill_rounds", None)  # a manual retry starts a fresh count
    data.pop("refill_single", None)
    data.pop("cancel_requested", None)
    data["stage_history"].append({"stage": target, "at": now(), "resumed": "retry"})
    log("INFO", "farm", f"Job {data.get('job_id')}: retried at {target}.")
    return target


def recompilable(data: dict) -> bool:
    """A render job that ended well (before "archived"): its frames are on
    disk, so its video can be compiled again without rendering anything."""
    stages = [s.get("stage") for s in data.get("stage_history") or []]
    while stages and stages[-1] == "archived":
        stages.pop()
    return bool(
        stages
        and stages[-1] == "finished"
        and data.get("output_path")
        and data.get("compiled_output_path")
    )


def _is_recompile(data: dict) -> bool:
    """Whether the job's current pass is a recompile (recompile_job())."""
    for stage in reversed(data.get("stage_history") or []):
        if stage.get("stage") == "checks_images_finished":
            return stage.get("resumed") == "recompile"
    return False


def recompile_job(data: dict) -> bool:
    """Rewind a finished job to checks_images_finished: the queue runs only
    the compilation again (local ffmpeg, no worker, no Blender), then flags
    the render to check again. Mutates data (caller writes it back)."""
    if not recompilable(data):
        return False
    data.pop("to_check_attempts", None)
    data["stage_history"].append(
        {"stage": "checks_images_finished", "at": now(), "resumed": "recompile"}
    )
    log("INFO", "farm", f"Job {data.get('job_id')}: compilation requested again.")
    return True


def _reassign_away_from_failed(data: dict) -> None:
    """Point a failed render at the workers that didn't fail it: its
    assigned machines (or every known worker, for an "auto" job) minus
    failed_machines. Left as is when no other worker is left."""
    failed = set(data.get("failed_machines") or [])
    if not failed:
        return
    pool = set(data.get("assigned_machines") or scan_workers())
    others = sorted(pool - failed)
    if not others:
        log(
            "WARNING",
            "farm",
            f"Job {data.get('job_id')}: no other worker than the one(s) that "
            f"failed it -- retried on the same machine(s).",
        )
        return
    data["assigned_machines"] = others
    log(
        "INFO",
        "farm",
        f"Job {data.get('job_id')}: retried on {', '.join(u[:8] for u in others)} "
        f"(without {', '.join(u[:8] for u in sorted(failed))}).",
    )


def _delete_placeholders(folder: Path) -> None:
    """Delete the empty files a render leaves for every frame it started."""
    try:
        entries = list(folder.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_file() and entry.stat().st_size == 0:
                entry.unlink()
        except OSError:
            pass


# How many ticks compilation_finished retries flagging the render to check
# before giving up on it (~5 min at the 10 s tick).
_TO_CHECK_ATTEMPTS = 30


def _flag_to_check(job: Path, data: dict, project_root: Path) -> bool:
    """mark_render_to_check() for a finished job. False: not written this
    tick, try again -- counted in the job file, given up (True) after
    _TO_CHECK_ATTEMPTS."""
    if mark_render_to_check(
        data["filepath"],
        data.get("shot_override", ""),
        Path(data["output_path"]).parent.as_posix(),
        data["job_id"],
        project_root,
        video=data.get("compiled_output_path"),
    ):
        return True
    with locked_json(job) as box:
        attempts = box["data"].get("to_check_attempts", 0) + 1
        box["data"]["to_check_attempts"] = attempts
        box["action"] = "to_write"
    if attempts < _TO_CHECK_ATTEMPTS:
        return False
    log(
        "ERROR",
        "farm",
        f"Job {data['job_id']}: render never flagged to check "
        f"({attempts} attempts) -- finished without it.",
    )
    return True


def resume_interrupted_stage(data: dict, reason: str) -> str | None:
    """Rewind a job whose *_start stage lost its process, so the queue picks
    it up again instead of leaving it stuck or "orphaned". Mutates data
    (caller writes it back); returns the stage resumed to, or None if the
    job wasn't in a resumable stage. A setup that got as far as writing its
    result counts as finished -- redoing it would create a new output
    folder (increment) for nothing."""
    stage = data["stage_history"][-1]["stage"]
    if stage == "setup_start":
        resolved = data.get("resolved_frame_range")
        done = data.get("split_into") or (resolved and tuple(resolved) != (0, 0))
        target = "setup_finished" if done else "queued"
    elif stage in _RESUME_STAGE:
        target = _RESUME_STAGE[stage]
    else:
        return None
    data["stage_history"].append({"stage": target, "at": now(), "resumed": reason})
    data.pop("local_processes", None)
    log(
        "WARNING",
        "farm",
        f"Job {data.get('job_id')}: {stage} interrupted ({reason}) -- resumed at {target}.",
    )
    return target


def scan_processes():
    """Poll all locally-tracked Popen processes; advance each job's stage
    once its whole process group has finished. Output is read back from the
    job's log (popen_logged()); the log itself is only deleted once the
    whole job ends well (scan_queue())."""
    path = ConfigCache.get_path("farm_actives")
    for job_id, procs in list(_active_processes.items()):
        # One job's failure must never stop the others from being polled.
        try:
            _finish_job_processes(job_id, procs, path / f"{job_id}.json")
        except Exception as e:
            log(
                "ERROR",
                "farm",
                f"Could not update job {job_id} after its process ended: {e}",
            )


def _finish_job_processes(job_id: str, procs: list, job_path: Path) -> None:
    """scan_processes() for one job: advance its stage once all of its
    processes have exited. Raises on an unreadable/unwritable job file --
    the processes stay tracked, so the next tick retries."""
    if any(p.poll() is None for p, _ in procs):
        return  # not finished yet

    if any(getattr(p, "adopted", False) for p, _ in procs):
        # Found again by PID after a crash (recover_interrupted_jobs()): its
        # exit code is unknowable, so judge by what's on disk, not by it.
        if job_path.exists():
            with locked_json(job_path) as box:
                data = box["data"] or {}
                if data.get("stage_history") and resume_interrupted_stage(
                    data, "process outlived a crash"
                ):
                    box["action"] = "to_write"
        _active_processes.pop(job_id, None)
        return

    errors = [ip for p, ip in procs if p.poll() != 0]

    if not job_path.exists():
        # Archived or deleted by hand while its process ran: nothing left
        # to update, and retrying would fail every tick forever.
        _active_processes.pop(job_id, None)
        log(
            "WARNING",
            "farm",
            f"Job {job_id}: process ended but its job file is gone -- stopped tracking it.",
        )
        return

    with locked_json(job_path) as box:
        data = box["data"] or {}
        stage = data["stage_history"][-1]["stage"]

        if not stage.endswith("_start"):
            # The job file moved on without us (hand-edited...): don't
            # invent a "<stage>_finished" nothing handles, stop tracking.
            log(
                "WARNING",
                "farm",
                f"Job {job_id}: process finished but the job is at '{stage}', "
                f"not a *_start stage -- result ignored.",
            )
        else:
            redo = False
            if stage == "checks_images_start":
                corrupted = corrupted_frames(
                    "\n".join(read_process_log(p) for p, _ in procs), data
                )
                data["frames_corrupted"] = len(corrupted)
                # With the frames two machines wrote: one re-render for both.
                redo = not errors and _send_back_bad_frames(data, corrupted)

            elif stage == "setup_start":
                # exit code 0 doesn't guarantee the script ran fine --
                # check the frame range actually got written.
                resolved = data.get("resolved_frame_range")
                if not resolved or tuple(resolved) == (0, 0):
                    errors.append("setup")
                    tail = "\n".join(read_process_log(p) for p, _ in procs).strip()
                    log(
                        "ERROR",
                        "farm",
                        f"Setup for job {job_id} never wrote a frame range "
                        f"(subprocess likely failed before that point) -- "
                        f"last output: {tail[-1500:] or '(empty)'}",
                    )

            outcome = "failed" if errors else "finished"
            if not redo:  # else already back at setup_finished
                data["stage_history"].append(
                    {"stage": f"{stage.replace('_start', '')}_{outcome}", "at": now()}
                )
            if errors:
                log(
                    "WARNING",
                    "farm",
                    f"Stage {stage} ends with errors for job_id {job_id} "
                    f"-- see {job_log_path(job_id).name}.",
                )

            data["used_machines"] = []
            data.pop("local_processes", None)
            box["action"] = "to_write"

    # Only once the job file is actually written: if that write fails,
    # the processes stay tracked and the next tick tries again.
    _active_processes.pop(job_id, None)


def _stage_time(stage_history: list, stage_name: str) -> datetime.datetime | None:
    """Timestamp of the first entry matching stage_name exactly, or None."""
    for entry in stage_history:
        if entry["stage"] == stage_name:
            return datetime.datetime.fromisoformat(entry["at"])
    return None


def _last_stage_time(stage_history: list, prefix: str) -> datetime.datetime | None:
    """Timestamp of the most recent entry whose stage starts with prefix, or None."""
    for entry in reversed(stage_history):
        if entry["stage"].startswith(prefix):
            return datetime.datetime.fromisoformat(entry["at"])
    return None


def construct_history(job: dict, status):
    """Build and append a completed/failed-job entry to the job's render_history.json."""
    # First render_start (a lost render re-dispatches, adding more) to the
    # last render_finished.
    start_time = _stage_time(job["stage_history"], "render_start")
    end_time = _last_stage_time(job["stage_history"], "render_finished")
    entry = {
        "job_id": job["job_id"],
        "completed_at": now(),
        "user": job["user"],
        "render_mode": job["render_mode"],
        # Which .blend version, and which vNNN_inc output folder.
        "source_file": job.get("filepath"),
        "output_path": job.get("output_path"),
        "shot_override": job.get("shot_override", ""),
        # used_machines is emptied at the end of every local stage, long
        # before this: rendered_by is its copy from render_finished.
        "machines_used": job.get("rendered_by") or job.get("used_machines", []),
        "frame_range_rendered": job.get("resolved_frame_range"),
        "frames_corrupted": job.get("frames_corrupted", 0),
        "duration_seconds": (end_time - start_time).total_seconds()
        if start_time and end_time
        else None,
        "status": status,
    }
    # A block rendered whole because the split couldn't cut it (setup);
    # frames corrupted or written by two machines, rendered again at the
    # end of the frame check (_send_back_bad_frames()).
    for key in (
        "skipped_shots",
        "absorbed_shots",
        "written_twice",
        "frames_rerendered",
        "seconds_per_frame",
        "machine_seconds",
        "frame_machines",
        "machine_names",
    ):
        if job.get(key):
            entry[key] = job[key]

    append_render_history(job["filepath"], entry)


def construct_split_history(job: dict) -> None:
    """Append a split submission's outcome to the block's render_history.json:
    which shots it split into, skipped, and absorbed."""
    entry = {
        "job_id": job["job_id"],
        "completed_at": now(),
        "user": job["user"],
        "status": "split",
        "split_into": job.get("split_into", []),
        "skipped_shots": job.get("skipped_shots", []),
        "absorbed_shots": job.get("absorbed_shots", []),
    }
    append_render_history(job["filepath"], entry)


def _stuck_this_render(worker: dict | None) -> dict | None:
    """The "stuck" part of a worker's last_job_result (frame, seconds,
    usual), if its render was killed on a stuck frame -- for a worker
    _failed_this_render() already matched to this render."""
    return ((worker or {}).get("last_job_result") or {}).get("stuck")


def _failed_this_render(worker: dict | None, data: dict) -> bool:
    """Whether a worker's last_job_result says it failed *this* render (its
    dispatch_id: a re-render reuses the job id) -- a real failure, not one
    cancelled, stopped or lost. The outcome of its last render only: once
    that machine ends another one, it's just not known any more."""
    result = (worker or {}).get("last_job_result") or {}
    return (
        bool(data.get("dispatch_id"))
        and result.get("dispatch_id") == data["dispatch_id"]
        and result.get("success") is False
        and not (result.get("lost") or result.get("stopped") or result.get("cancelled"))
    )


# A worker silent this long is gone (crashed, machine off), not just slow --
# well past STALE_WORKER_SECONDS (a missed beat or two) and a Blender
# restart: a worker that comes back quickly shows for itself whether it's
# still on its render (adopted by PID) or not (launch_worker()).
WORKER_GONE_SECONDS = 180


def _read_worker(uuid: str) -> dict | None:
    """Worker uuid's file as it is on disk: {} if it's gone, None if it
    can't be read this tick. Never through scan_workers(), which drops a
    worker whose heartbeat is a few seconds late -- and with it the render
    it's on (see NOTES.md, "Render stuck at 100 %")."""
    path = ConfigCache.get_path("workers") / f"worker_{uuid}.json"
    try:
        with locked_json(path, read_only=True, retries=0) as box:
            return box["data"] or {}
    except (OSError, ValueError):
        return None


def _worker_gone(worker: dict) -> bool:
    """Whether a worker file (_read_worker()) is gone or hasn't heartbeat
    for WORKER_GONE_SECONDS."""
    if not worker:
        return True
    try:
        last = datetime.datetime.fromisoformat(worker.get("last_heartbeat", ""))
    except (TypeError, ValueError):
        return True
    return (now(False) - last).total_seconds() > WORKER_GONE_SECONDS


def _drop_pending_request(job_id: str, uuid: str) -> bool:
    """Delete worker uuid's render request for job_id if it's still waiting
    to be picked up. True if it was (and is now gone); False if the worker
    already took it (it's running), or the request can't be locked this
    tick -- then the caller keeps waiting, as before."""
    request = ConfigCache.get_path("farm_requests") / f"request_{job_id}_{uuid}.json"
    if not request.exists():
        return False
    try:
        with locked_json(request, retries=1) as box:
            if not box["data"]:
                return False
            box["action"] = "to_delete"
    except Exception:
        return False
    return not request.exists()


def _withdraw_requests(job_id: str, machines: list, cancel: bool = False) -> list:
    """Delete the render requests of job_id these machines haven't picked up
    yet: they leave its used_machines. cancel: the job's own Cancel --
    flagged (cancel_requested), never sent out again, and failed as
    cancelled at once if no machine is left. Returns the machines whose
    request was deleted."""
    dropped = [uuid for uuid in machines if _drop_pending_request(job_id, uuid)]
    if dropped or cancel:
        job_path = ConfigCache.get_path("farm_actives") / f"{job_id}.json"
        with locked_json(job_path) as box:
            data = box["data"] or {}
            if data and data["stage_history"][-1]["stage"] == "render_start":
                data["used_machines"] = [
                    u for u in data.get("used_machines", []) if u not in dropped
                ]
                if cancel:
                    data["cancel_requested"] = True
                    if not data["used_machines"]:
                        data["stage_history"].append(
                            {"stage": "render_failed", "at": now(), "cancelled": True}
                        )
                box["action"] = "to_write"
    if dropped:
        log(
            "INFO",
            "farm",
            f"Job {job_id}: render request withdrawn from "
            f"{', '.join(u[:8] for u in dropped)} before it started.",
        )
    return dropped


def cancel_pending_renders(
    job_id: str, machines: list, whole_job: bool = False
) -> list:
    """Cancel side for the machines that haven't picked up their render
    request for job_id yet: the request is deleted (a cancel file would find
    nothing to kill, and the request would still run later). whole_job: the
    job's Cancel, not one machine's (_withdraw_requests()). Returns the
    machines still to cancel through a cancel file (their render is
    running)."""
    dropped = _withdraw_requests(job_id, machines, cancel=whole_job)
    return [uuid for uuid in machines if uuid not in dropped]


def frames_complete(data: dict, project_root: Path) -> bool:
    """Every frame of the job's resolved range is on disk, non-empty (an
    empty file is a placeholder: a frame started, never finished)."""
    paths = frame_paths(data, project_root)
    if not paths:
        return False
    for path in paths:
        try:
            if path.stat().st_size == 0:
                return False
        except OSError:
            return False
    return True


# How many times a render whose machines all stopped with frames still
# missing is sent out again for them before giving up (render_failed).
MAX_REFILL_ROUNDS = 3


def _render_folder(data: dict, project_root: Path | None) -> Path | None:
    output_path = data.get("output_path")
    if not output_path or not project_root:
        return None
    return (Path(project_root) / output_path).parent


# How long nobody must be seen on a render before it's judged: a worker
# taking up its request deletes it, then writes its own file -- a monitor
# reading in between sees neither. Two ticks.
NOBODY_SECONDS = 20

# (job_id, dispatch_id) -> time.monotonic() nobody was first seen on it.
_nobody_since: dict[tuple, float] = {}


def _machines_on(data: dict) -> tuple[list, list]:
    """The job's used_machines still on this render, (rendering, waiting):
    its worker rendering this job, alive -- or unreadable this tick, can't
    tell -- or its request not taken up yet, the worker alive. One gone,
    stopped, or on to anything else is done with it, whatever it published:
    a worker keeps the outcome of its last render only."""
    job_id = data["job_id"]
    rendering, waiting = [], []
    for uuid in data.get("used_machines", []):
        w = _read_worker(uuid)
        if w is None:
            rendering.append(uuid)
            continue
        if _worker_gone(w) or w.get("status") == "stopped":
            continue
        if w.get("status") == "render" and w.get("current_job_id") == job_id:
            rendering.append(uuid)
            continue
        request = (
            ConfigCache.get_path("farm_requests") / f"request_{job_id}_{uuid}.json"
        )
        try:
            if request.exists():
                waiting.append(uuid)
        except OSError:
            rendering.append(uuid)  # can't tell this tick
    return rendering, waiting


# One character per machine in frame_machines: 62 machines.
_MACHINE_LETTERS = string.ascii_uppercase + string.ascii_lowercase + string.digits


def _note_frames(data: dict) -> None:
    """From every machine's saved_frames_path() record of the job -- every
    round so far, not only this one's -- into data, for its detail and its
    render history:
    - machine_seconds / seconds_per_frame: the mean seconds per frame of
      each machine and of the job (frame_seconds());
    - frame_machines: which machine wrote each frame, {"start": first
      frame, "frames": one letter per frame of the range, "." if none is
      known, "machines": {letter: [uuid, name]}} -- a byte a frame, read
      through machine_for_frame(). A frame written in several rounds: this
      round's machine, else the latest line's.
    Nothing for workers on a version that records no time / no frame."""
    start, end = (int(x) for x in data.get("resolved_frame_range") or (0, 0))
    dispatch_id = data.get("dispatch_id")
    per_machine, timed, writers = {}, [], {}
    prefix = f"request_{data['job_id']}_"
    for path in sorted(ConfigCache.get_path("farm_requests").glob(f"{prefix}*.saved")):
        uuid = path.stem[len(prefix) :]
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        seconds = frame_seconds(text)
        if seconds:
            per_machine[uuid] = round(sum(seconds) / len(seconds), 1)
            timed += seconds
        for line_dispatch, frame, at in parse_saved(text):
            rank = (line_dispatch == dispatch_id, at or 0.0)
            if frame is None or not start <= frame <= end:
                continue
            if rank >= writers.get(frame, ((), ""))[0]:
                writers[frame] = (rank, uuid)
    if timed:
        data["machine_seconds"] = per_machine
        data["seconds_per_frame"] = round(sum(timed) / len(timed), 1)
    if not writers:
        return
    previous = (data.get("frame_machines") or {}).get("machines", {})
    known = {u: n for u, n in previous.values()}
    letters = {}
    for frame in sorted(writers):
        uuid = writers[frame][1]
        if uuid not in letters and len(letters) < len(_MACHINE_LETTERS):
            letters[uuid] = _MACHINE_LETTERS[len(letters)]
    data["frame_machines"] = {
        "start": start,
        "frames": "".join(
            letters.get(writers[f][1], ".") if f in writers else "."
            for f in range(start, end + 1)
        ),
        "machines": {
            letter: [uuid, _machine_name(uuid, known)]
            for uuid, letter in letters.items()
        },
    }


def _note_machine_names(data: dict, uuids) -> None:
    """machine_names: {uuid: name} of every machine on the job (merged
    across rounds), stored with it and in its render history -- what the
    job detail names them by once their worker is gone, or their id has
    changed (a machine's id is its prefs': reset with them)."""
    known = dict(data.get("machine_names") or {})
    frames = (data.get("frame_machines") or {}).get("machines", {})
    known.update({u: n for u, n in frames.values()})
    for uuid in set(uuids) | set(data.get("failed_machines") or []):
        known[uuid] = _machine_name(uuid, known)
    data["machine_names"] = known


def _machine_name(uuid: str, known: dict) -> str:
    """Machine uuid's name: its worker's user and id ("Alice (a1b2c3d4)" --
    the id alone, all a worker file says of the machine, told nobody who it
    was), else the one recorded before (a worker removed since), else its
    uuid's start."""
    worker = _read_worker(uuid) or {}
    if worker.get("user"):
        return f"{worker['user']} ({worker.get('machine') or uuid[:8]})"
    return worker.get("machine") or known.get(uuid) or uuid[:8]


def machine_for_frame(record: dict | None, frame: int) -> tuple[str, str] | None:
    """(uuid, name) of the machine that wrote this frame, from a render's
    frame_machines (_note_frames()); ("", "unknown") if none is known for
    it, None if it's out of the render's range. Pure: draw()-safe."""
    if not record or not record.get("frames"):
        return None
    index = frame - int(record.get("start", 0))
    if not 0 <= index < len(record["frames"]):
        return None
    machine = record.get("machines", {}).get(record["frames"][index])
    return tuple(machine) if machine else ("", "unknown")


def check_render_completion(
    job_path: Path, project_root: Path | None = None, data: dict | None = None
) -> None:
    """Monitor-only. A render is over once none of its machines is on it
    any more (_machines_on()), for NOBODY_SECONDS -- whatever each one did:
    one that failed, crashed, was stopped or moved on to another job doesn't
    end it while others render (placeholders + no overwrite: they may still
    render every frame). Then it's judged on the frames on disk: all there
    -> render_finished; else a machine failed it -> render_failed; the
    job's Cancel -> render_failed (cancelled); MAX_REFILL_ROUNDS reached ->
    render_failed; else the empty files left are deleted (safe now: nobody
    renders it) and it goes back to setup_finished for them.

    data: the job as scan_queue() read it (no lock): while a machine is on
    it, nothing is locked -- every tick of a render of hours."""
    if data is None:
        data = read_json_quiet(job_path)
        if not data:
            return None
    key = (data.get("job_id"), data.get("dispatch_id"))
    rendering, waiting = _machines_on(data)
    if waiting and free_frames(data, project_root) == []:
        # Every frame taken: a machine that hasn't taken up its request
        # (busy on another job) has nothing left to do here -- dropped
        # rather than waited for. See NOTES.md, "Render stuck at 100 %".
        dropped = _withdraw_requests(data["job_id"], waiting)
        waiting = [u for u in waiting if u not in dropped]
    if rendering or waiting:
        _nobody_since.pop(key, None)
        return data
    if time.monotonic() - _nobody_since.setdefault(key, time.monotonic()) < (
        NOBODY_SECONDS
    ):
        return data

    with locked_json(job_path) as box:
        data = box["data"]
        if not data or data["stage_history"][-1]["stage"] != "render_start":
            return data
        rendering, waiting = _machines_on(data)
        if rendering or waiting or (data["job_id"], data.get("dispatch_id")) != key:
            return data  # joined, or sent out again, meanwhile
        _nobody_since.pop(key, None)

        machines = data.get("used_machines", [])
        # A request a gone/stopped worker never took up would otherwise run
        # whenever it comes back, for a render nobody waits on any more.
        for uuid in machines:
            request = (
                ConfigCache.get_path("farm_requests")
                / f"request_{data['job_id']}_{uuid}.json"
            )
            try:
                retry_shared_io(request.unlink)
            except OSError:
                pass
        failed = [u for u in machines if _failed_this_render(_read_worker(u), data)]
        # Killed on a stuck frame (workers.check_stuck_renders()): never sent
        # back to it, but no reason to fail the job -- its frames left go to
        # the other machines, within MAX_REFILL_ROUNDS like any refill.
        stuck = {u for u in failed if _stuck_this_render(_read_worker(u))}
        for uuid in sorted(stuck):  # for Job details
            data.setdefault("stuck_frames", []).append(
                {"machine": uuid, "at": now()} | _stuck_this_render(_read_worker(uuid))
            )

        # Kept for construct_history(): used_machines is reset by the next
        # local stages (_finish_job_processes()).
        data["rendered_by"] = list(machines)
        _note_frames(data)
        _note_machine_names(data, machines)
        box["action"] = "to_write"
        if failed:
            # Kept across retries: retry_job() reassigns the job to the
            # other workers.
            data["failed_machines"] = sorted(
                set(data.get("failed_machines", [])) | set(failed)
            )

        if frames_complete(data, project_root):
            data["stage_history"].append({"stage": "render_finished", "at": now()})
        elif set(failed) - stuck:
            data["stage_history"].append({"stage": "render_failed", "at": now()})
        elif data.get("cancel_requested"):
            data["stage_history"].append(
                {"stage": "render_failed", "at": now(), "cancelled": True}
            )
        elif data.get("refill_rounds", 0) >= MAX_REFILL_ROUNDS:
            data["stage_history"].append(
                {
                    "stage": "render_failed",
                    "at": now(),
                    "resumed": f"frames still missing after {MAX_REFILL_ROUNDS} rounds",
                }
            )
            log(
                "ERROR",
                "farm",
                f"Job {data['job_id']}: frames still missing after "
                f"{MAX_REFILL_ROUNDS} re-dispatches -- failed.",
            )
        else:
            # Frames missing because machines stopped early (crash, worker
            # stopped, one machine cancelled): nobody renders this job now,
            # so any empty file is a frame abandoned mid-render -- delete
            # them and send the job out again for what's left.
            folder = _render_folder(data, project_root)
            if folder:
                _delete_placeholders(folder)
            if stuck:
                _reassign_away_from_failed(data)
            data["refill_rounds"] = data.get("refill_rounds", 0) + 1
            data["stage_history"].append(
                {
                    "stage": "setup_finished",
                    "at": now(),
                    "resumed": (
                        "frames left after a stuck frame"
                        if stuck
                        else "frames left after machines stopped"
                    ),
                }
            )
            data["used_machines"] = []
            data.pop("dispatch_id", None)
            log(
                "WARNING",
                "farm",
                f"Job {data['job_id']}: frames missing, nobody rendering it any "
                f"more -- sent out again for them.",
            )
        return data


def frames_written_twice(data: dict) -> list[int]:
    """Frames of this render (its dispatch_id) that two of its machines or
    more wrote, from each machine's saved_frames_path() record. [] for a
    worker on a version that keeps none."""
    dispatch_id = data.get("dispatch_id")
    if not dispatch_id:
        return []
    writers: dict[int, set[str]] = {}
    # rendered_by: the render's machines (used_machines is emptied when a
    # local stage ends -- the frame check included).
    for uuid in set(data.get("rendered_by") or data.get("used_machines") or []):
        try:
            text = saved_frames_path(data["job_id"], uuid).read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == dispatch_id and parts[1].isdigit():
                writers.setdefault(int(parts[1]), set()).add(uuid)
    return sorted(frame for frame, uuids in writers.items() if len(uuids) > 1)


# The frame check's ffmpeg output (checks_images()): one showinfo line per
# decoded frame, "pts" being its index in the sequence, and every log line
# tagged with its level.
_SHOWINFO_FRAME = re.compile(
    r"\[Parsed_showinfo[^\]]*\] \[info\] n:\s*\d+\s+pts:\s*(\d+)"
)
_LOG_PROBLEM = re.compile(r"\[(error|warning)\]")
# Not about a frame's data: filters (a format change mid-sequence rebuilds
# the graph, with swscaler warnings), the muxer. Only the decoder and the
# input's own lines count.
_NOT_INPUT = ("Parsed_", "[out#", "[fc#", "[vf#", "[swscaler", "[auto_scale", "[graph")


def corrupted_frames(log_text: str, data: dict) -> list[int]:
    """Frame numbers the frame check found corrupted, read off its ffmpeg
    output. Decoding single-threaded, every decoder error or warning comes
    right before the showinfo line of the frame it's about; a frame ffmpeg
    couldn't decode at all has no line: a gap in pts -- the errors before
    the frame after a gap count for both (one frame rendered again for
    nothing beats a corrupted one kept). [] if the output has no frame line
    at all (unreadable log): nothing can be told. See NOTES.md, "Frames
    written by two machines"."""
    start, end = (int(x) for x in data.get("resolved_frame_range") or (0, 0))
    total = end - start + 1
    bad: set[int] = set()
    expected = 0
    pending = False
    seen = False
    for line in log_text.splitlines():
        m = _SHOWINFO_FRAME.search(line)
        if m:
            seen = True
            index = int(m.group(1))
            bad.update(range(expected, index))  # never decoded
            if pending:
                bad.add(index)
            pending = False
            expected = index + 1
        elif _LOG_PROBLEM.search(line) and not any(s in line for s in _NOT_INPUT):
            pending = True
    if not seen:
        return []
    if expected < total:
        bad.update(range(expected, total))  # the end never decoded
    elif pending and expected == total:
        bad.add(total - 1)  # errors after the last frame (not frames past it)
    return sorted(start + i for i in bad if 0 <= i < total)


def _send_back_bad_frames(data: dict, corrupted: list[int]) -> bool:
    """End of the frame check: the frames ffmpeg found corrupted and those
    two machines wrote (frames_written_twice()) are deleted, and the job
    goes back to setup_finished for them -- one re-render for both kinds,
    on one machine (refill_single: a handful of frames on every free
    machine would collide again). Mutates data. False -- on to the
    compilation -- when there are none, or no refill round is left (then
    they're kept and named in a warning)."""
    twice = frames_written_twice(data)
    bad = sorted(set(corrupted) | set(twice))
    if not bad:
        return False
    what = []
    if corrupted:
        what.append(f"{len(corrupted)} corrupted ({_frames_label(corrupted)})")
    if twice:
        what.append(f"{len(twice)} written by two machines ({_frames_label(twice)})")
    what = ", ".join(what)
    if data.get("refill_rounds", 0) >= MAX_REFILL_ROUNDS:
        log(
            "WARNING",
            "farm",
            f"Job {data['job_id']}: frames {what} -- kept, no re-render left: "
            f"check them.",
        )
        return False
    _delete_frames(data, get_active_project_root(), bad)
    if twice:
        data["written_twice"] = sorted(
            set(data.get("written_twice") or []) | set(twice)
        )
    data["frames_rerendered"] = sorted(
        set(data.get("frames_rerendered") or []) | set(bad)
    )
    data["refill_rounds"] = data.get("refill_rounds", 0) + 1
    data["refill_single"] = True
    data["stage_history"].append(
        {
            "stage": "setup_finished",
            "at": now(),
            "resumed": f"{len(bad)} frame(s) to render again",
        }
    )
    data.pop("dispatch_id", None)
    log(
        "WARNING",
        "farm",
        f"Job {data['job_id']}: frames {what} -- rendered again on one machine.",
    )
    return True


def _delete_frames(data: dict, project_root: Path, frames: list[int]) -> None:
    """Delete these frame numbers' files of the job's output. Best effort: a
    frame that can't be deleted stays (and is then judged on disk)."""
    paths = frame_paths(data, project_root) or []
    start = int((data.get("resolved_frame_range") or (0, 0))[0])
    for frame in frames:
        index = frame - start
        if 0 <= index < len(paths):
            try:
                retry_shared_io(paths[index].unlink)
            except FileNotFoundError:
                pass
            except OSError as e:
                log("WARNING", "farm", f"Could not delete {paths[index].name}: {e}")


def _frames_label(frames: list[int], shown: int = 10) -> str:
    """ "1785, 1807, 1811 (+4)" """
    text = ", ".join(str(f) for f in frames[:shown])
    return text + (f" (+{len(frames) - shown})" if len(frames) > shown else "")


def discard_saved_frames(job_id: str) -> None:
    """Delete every machine's saved_frames_path() record of job_id -- only
    read while its render is judged -- and the .stop/.frame flags a worker
    that crashed mid-render left (workers.render_stop_path()). Best effort."""
    requests = ConfigCache.get_path("farm_requests")
    for ext in ("saved", "stop", "frame"):
        for path in requests.glob(f"request_{job_id}_*.{ext}"):
            try:
                retry_shared_io(path.unlink)
            except OSError:
                pass


def mark_stage(path, stage):
    """Append a stage entry to a job file's stage_history (own locked
    transaction). No-op if the file is gone -- archived from Farm monitoring
    meanwhile (it raised "'NoneType' object is not subscriptable")."""
    with locked_json(path) as box:
        if not box["data"]:
            return
        box["data"]["stage_history"].append({"stage": stage, "at": now()})
        box["action"] = "to_write"
