"""Submission queue: incoming requests -> active jobs, scanned every tick by the monitor."""

import datetime
from pathlib import Path

from ..lib import ConfigCache, log, now, to_relative
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
from .post_render import checks_images, compilation
from .workers import scan_workers


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
                if not local_slot_busy():
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


def scan_processes():
    """Poll all locally-tracked Popen processes; advance each job's stage
    once its whole process group has finished. Output is read back from the
    job's log (popen_logged()); the log itself is only deleted once the
    whole job ends well (scan_queue())."""
    path = ConfigCache.get_path("farm_actives")
    for job_id, procs in list(_active_processes.items()):
        # One job's failure must never stop the others from being polled --
        # without this, a single unreadable job file raised every tick
        # before the rest were reached, and none of them ever advanced.
        try:
            _finish_job_processes(job_id, procs, path / f"{job_id}.json")
        except Exception as e:
            log("ERROR", "farm", f"Could not update job {job_id} after its process ended: {e}")


def _finish_job_processes(job_id: str, procs: list, job_path: Path) -> None:
    """scan_processes() for one job: advance its stage once all of its
    processes have exited. Raises on an unreadable/unwritable job file --
    the processes stay tracked, so the next tick retries."""
    if any(p.poll() is None for p, _ in procs):
        return  # not finished yet
    errors = [ip for p, ip in procs if p.poll() != 0]

    if not job_path.exists():
        # Archived or deleted by hand while its process ran: nothing left
        # to update, and retrying would fail every tick forever.
        _active_processes.pop(job_id, None)
        log("WARNING", "farm", f"Job {job_id}: process ended but its job file is gone -- stopped tracking it.")
        return

    with locked_json(job_path) as box:
        data = box["data"] or {}
        stage = data["stage_history"][-1]["stage"]

        if not stage.endswith("_start"):
            # The job file moved on without us (hand-edited, or an
            # older stage left behind) -- appending "<stage>_finished"
            # to e.g. "queued" would invent a stage nothing handles
            # ("queued_finished"), stuck forever. Just stop tracking.
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
    start_time = _stage_time(job["stage_history"], "render")
    end_time = _last_stage_time(job["stage_history"], "render")
    entry = {
        "job_id": job["job_id"],
        "completed_at": now(),
        "user": job["user"],
        "render_mode": job["render_mode"],
        "machines_used": job.get("used_machines", []),
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


def check_render_completion(job_path: Path) -> None:
    """Monitor-only: cross-check used_machines against each worker's declared
    state. No worker ever writes this job file for this stage."""
    with locked_json(job_path) as box:
        data = box["data"]
        if data["stage_history"][-1]["stage"] != "render_start":
            return data

        workers = (
            scan_workers()
        )  # read-only, each worker file is already locked individually
        still_running = []
        any_failed = False

        for uuid in data.get("used_machines", []):
            w = workers.get(uuid)
            result = (w or {}).get("last_job_result")
            if result and result["job_id"] == data["job_id"]:
                if not result["success"]:
                    any_failed = True
                # else: this worker did finish THIS job successfully, treat it
                # as handled and don't put it back in still_running
            else:
                still_running.append(uuid)  # worker not found/stale -- see reconcile

        if any_failed:
            data["stage_history"].append({"stage": "render_failed", "at": now()})
            box["action"] = "to_write"
        elif not still_running:
            data["stage_history"].append({"stage": "render_finished", "at": now()})
            box["action"] = "to_write"
        return data


def mark_stage(path, stage):
    """Append a stage entry to a job file's stage_history (own locked transaction)."""
    with locked_json(path) as box:
        box["data"]["stage_history"].append({"stage": stage, "at": now()})
        box["action"] = "to_write"
