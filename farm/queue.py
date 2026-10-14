"""Submission queue: incoming requests -> active jobs, scanned every tick by the monitor."""

import datetime
from pathlib import Path

from ..lib import ConfigCache, log, mark_render_to_check, now, retry_shared_io, to_relative
from .dispatch import (
    _active_processes,
    append_render_history,
    discard_job_log,
    job_log_path,
    local_slot_busy,
    locked_json,
    read_process_log,
    render_dispatch,
)
from .post_render import checks_images, compilation, refresh_shot_thumbnail
from .workers import local_render_running


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


def scan_queue(project_root: Path) -> None:
    """Advance every active job by one step according to its current stage."""
    scan_dir = ConfigCache.get_path("farm_actives")

    jobs = []
    for job_file in scan_dir.glob("job_*.json"):
        try:
            with locked_json(job_file) as box:
                data = box["data"] or {}
                jobs.append((job_file, data))
        except Exception as e:
            log("ERROR", "farm", f"Could not read job file {job_file.name}: {e}")

    jobs.sort(
        key=lambda x: (
            x[1].get("priority", 10),  # descending priority
            x[1].get("submitted_at", ""),  # ascending date at equal priority
        )
    )
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
                "archived",
            ]
            if stage in pass_stage:
                pass

            elif stage == "queued":
                # Setup also waits for a render this same instance runs as a
                # worker: both load the whole .blend. Only setup -- the
                # ffmpeg stages are light and must not queue behind a whole
                # render (see NOTES.md, "Re-rendering a file...").
                if not local_slot_busy() and not local_render_running():
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
                else:
                    render_dispatch(job)
            elif stage == "split_finished":
                construct_split_history(data)
                mark_stage(job, "archived")
                discard_job_log(data["job_id"])  # the shots carry on as their own jobs
            elif stage == "render_start":
                check_render_completion(job)
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
                construct_history(data, status="finished")
                mark_stage(job, "archived")
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
# a render runs on a worker, recovered through its own last_job_result
# ("lost") or its heartbeat -- see check_render_completion().
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
    left by the failed one: a placeholder is skipped, never re-rendered."""
    failed = failed_stage(data)
    if not failed:
        return None
    target = _RETRY_STAGE[failed]
    if failed == "render_failed" and data.get("output_path"):
        _delete_placeholders(project_root / Path(data["output_path"]).parent)
    data.pop("rendered_by", None)
    data.pop("local_processes", None)
    data["stage_history"].append({"stage": target, "at": now(), "resumed": "retry"})
    log("INFO", "farm", f"Job {data.get('job_id')}: retried at {target}.")
    return target


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
            if stage == "checks_images_start":
                # ffmpeg -v error: one non-empty line per corrupted frame.
                corrupted = sum(
                    1
                    for p, _ in procs
                    for line in read_process_log(p).splitlines()
                    if line.strip()
                )
                data["frames_corrupted"] = corrupted

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


def _is_this_render(result: dict | None, data: dict) -> bool:
    """Whether a worker's last_job_result is about *this* render of the job,
    not an earlier one: re-rendering the same file reuses its job id (a
    hash of file + preset + shot), so the job id alone matched the previous
    render's result and marked the new one finished right away."""
    if not result or result.get("job_id") != data.get("job_id"):
        return False
    if result.get("dispatch_id") and data.get("dispatch_id"):
        return result["dispatch_id"] == data["dispatch_id"]
    # A side without dispatch_id (worker or monitor on an older version):
    # fall back to "finished after this render was dispatched". Two
    # machines' clocks -- see now().
    started = _last_stage_time(data.get("stage_history", []), "render_start")
    try:
        return (
            started is None or datetime.datetime.fromisoformat(result["at"]) >= started
        )
    except (KeyError, TypeError, ValueError):
        return False


# A worker silent this long is gone (crashed, machine off), not just slow --
# well past STALE_WORKER_SECONDS (a missed beat or two) and a Blender
# restart, so a worker that comes back quickly reports its own lost render
# instead (launch_worker() -> last_job_result "lost").
WORKER_GONE_SECONDS = 180


def _read_worker(uuid: str) -> dict | None:
    """Worker uuid's file as it is on disk: {} if it's gone, None if it
    can't be read this tick. Never through scan_workers(), which drops a
    worker whose heartbeat is a few seconds late -- and with it the result
    it published (see NOTES.md, "Render stuck at 100 %")."""
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


def check_render_completion(job_path: Path) -> None:
    """Monitor-only: cross-check used_machines against each worker's declared
    state. No worker ever writes this job file for this stage. A render
    whose worker lost it (crashed and came back -> result "lost", or never
    came back -> WORKER_GONE_SECONDS) is sent back to setup_finished and
    re-dispatched: renders run with placeholders and no overwrite, so the
    new one only renders the frames still missing."""
    with locked_json(job_path) as box:
        data = box["data"]
        if data["stage_history"][-1]["stage"] != "render_start":
            return data

        still_running = []
        lost = []
        any_failed = False
        any_succeeded = False

        for uuid in data.get("used_machines", []):
            # Its file, whatever its heartbeat's age: a result for this
            # render is final even from a worker a few seconds late.
            w = _read_worker(uuid)
            if w is None:
                still_running.append(uuid)  # can't tell this tick
                continue
            result = w.get("last_job_result")
            if _is_this_render(result, data):
                if result.get("lost"):
                    lost.append(uuid)
                elif not result["success"]:
                    any_failed = True
                else:
                    any_succeeded = True  # finished THIS render successfully
            elif _worker_gone(w):
                lost.append(uuid)
            else:
                still_running.append(uuid)

        if any_succeeded and still_running and not any_failed and not lost:
            # A worker that ended this render successfully went through the
            # whole range (placeholders, no overwrite): every frame is
            # rendered or being rendered. One that never picked up its
            # request has nothing left to do -- drop the request rather than
            # wait for it: busy on another job, it held this one at 100 %
            # for that job's whole render. See NOTES.md, "Render stuck at
            # 100 %".
            dropped = [
                uuid
                for uuid in still_running
                if _drop_pending_request(data["job_id"], uuid)
            ]
            if dropped:
                still_running = [u for u in still_running if u not in dropped]
                data["used_machines"] = [
                    u for u in data["used_machines"] if u not in dropped
                ]
                box["action"] = "to_write"
                log(
                    "INFO",
                    "farm",
                    f"Job {data['job_id']}: rendered before "
                    f"{', '.join(u[:8] for u in dropped)} picked up its share "
                    f"-- request dropped.",
                )

        if any_failed:
            data["rendered_by"] = list(data.get("used_machines", []))
            data["stage_history"].append({"stage": "render_failed", "at": now()})
            box["action"] = "to_write"
        elif lost:
            # A request the lost worker never picked up would otherwise run
            # whenever it comes back, for a dispatch nobody waits on anymore.
            for uuid in lost:
                request = (
                    ConfigCache.get_path("farm_requests")
                    / f"request_{data['job_id']}_{uuid}.json"
                )
                try:
                    retry_shared_io(request.unlink)
                except OSError:
                    pass
            data["stage_history"].append(
                {
                    "stage": "setup_finished",
                    "at": now(),
                    "resumed": "render lost by a worker",
                }
            )
            data["used_machines"] = []
            data.pop("dispatch_id", None)
            box["action"] = "to_write"
            log(
                "WARNING",
                "farm",
                f"Job {data['job_id']}: render lost on {', '.join(u[:8] for u in lost)} "
                f"-- re-dispatching (frames already rendered are kept).",
            )
        elif not still_running:
            # Kept for construct_history(): used_machines is reset by the
            # next local stages (_finish_job_processes()).
            data["rendered_by"] = list(data.get("used_machines", []))
            data["stage_history"].append({"stage": "render_finished", "at": now()})
            box["action"] = "to_write"
        return data


def mark_stage(path, stage):
    """Append a stage entry to a job file's stage_history (own locked transaction)."""
    with locked_json(path) as box:
        box["data"]["stage_history"].append({"stage": stage, "at": now()})
        box["action"] = "to_write"
