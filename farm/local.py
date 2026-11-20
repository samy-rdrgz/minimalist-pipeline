"""Render here: a file rendered on this machine, now, outside the farm's
queue -- the animator who wants to see their shot play, a shot rendered
without forcing its priority on everyone's farm. See NOTES.md, "Render
here: a farm job of one machine".

The same job as the farm's (setup, chunks, the frame check, the video and
its sound, render_history.json, the department's to check, the shot's
thumbnail), with "local": this machine's id and only this machine assigned.
Written straight into actives/ (no host to take it from incoming/), and
carried by this machine whatever runs elsewhere: the farm host leaves it
alone (scan_queue()), this machine's own farm loop moves it on
(local_tick()) -- unless this Blender is the host itself, whose queue
does. The machine renders it as a worker: its worker role started for it
if it had none ("local_role", given up once its renders here are done),
kept for it meanwhile ("local_only": no host sends it anything else). A
worker busy with the farm's render gives way after its frame."""

import hashlib
from pathlib import Path

from ..lib import (
    ConfigCache,
    PipelineError,
    get_machine_id,
    locked_json,
    log,
    now,
    read_json_quiet,
    to_relative,
)

_IN_FLIGHT_END = ("finished", "archived", "orphaned", "split_finished")
_recovered = {"done": False}


def local_job_name(filepath: str, prerender_script: str, shot_override: str, machine: str) -> str:
    """job_<hash>.json: its own id, never the farm's for the same file (a
    render here never stops one sent to the farm, nor the other way)."""
    key = f"{to_relative(filepath)}|{prerender_script}|{shot_override}|here|{machine}".lower()
    return f"job_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:10]}.json"


def write_local_job(name: str, data: dict) -> str:
    """The job, queued, straight into actives/ -- as the host's
    scan_requests() would have it. Refused while the same render here is
    under way. Returns its id."""
    path = ConfigCache.get_path("farm_actives") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_json(path) as box:
        old = box["data"] or {}
        stage = (old.get("stage_history") or [{}])[-1].get("stage", "")
        if old and stage not in _IN_FLIGHT_END and not stage.endswith("failed"):
            raise PipelineError(f"{Path(data['filepath']).name} is already rendering here.")
        box["data"] = {"job_id": path.stem} | data | {"stage_history": [{"stage": "queued", "at": now()}]}
        box["action"] = "to_write"
    log("INFO", "farm", f"Render here queued: {data['filepath']} ({data.get('machine') or data['local'][:8]}).")
    return path.stem


def local_jobs_in_flight(machine: str | None = None) -> list[dict]:
    """This machine's renders here not over yet (a failed one is over: its
    retry starts it again)."""
    machine = machine or get_machine_id()
    out = []
    try:
        paths = list(ConfigCache.get_path("farm_actives").glob("job_*.json"))
    except Exception:
        return out
    for p in paths:
        data = read_json_quiet(p)
        if not isinstance(data, dict) or data.get("local") != machine:
            continue
        stage = (data.get("stage_history") or [{}])[-1].get("stage", "")
        if stage not in _IN_FLIGHT_END and not stage.endswith("failed"):
            out.append(data)
    return out


def reserve_this_machine() -> None:
    """This machine kept for its renders here: its worker role started if
    it had none (for them only), else kept off the farm's renders. Raises
    PipelineError when another Blender of this machine holds the role."""
    from .workers import launch_worker

    if not launch_worker(local_only=True):
        raise PipelineError(
            "Another Blender on this machine is its farm worker: render here from that one, or stop its worker."
        )


def _give_way_here(waiting: list[dict]) -> None:
    """A render here waiting while this machine renders one of the farm's:
    that one gives way after its frame (the host sends its chunk elsewhere)."""
    from .workers import local_render_jobs, render_yield_path

    if not any((d.get("stage_history") or [{}])[-1].get("stage") in ("queued", "setup_finished", "render_start") for d in waiting):
        return
    mine = {d.get("job_id") for d in waiting}
    for job_id in local_render_jobs():
        if job_id in mine:
            continue
        flag = render_yield_path(job_id)
        if not flag.exists():
            try:
                flag.touch()
                log("INFO", "farm", f"This machine gives way after its frame of {job_id}, for its render here.")
            except OSError:
                pass


def _release(data: dict) -> None:
    """No render here left: the role given up if it was started for them,
    else the machine back to the farm's renders."""
    from .workers import stop_worker, update_worker, worker_rendering

    if data.get("local_role"):
        if not worker_rendering():
            stop_worker(kill_render=False)
            log("INFO", "farm", "Renders here done: this machine's worker role ends.")
    elif data.get("local_only"):
        update_worker({"local_only": False})
        log("INFO", "farm", "Renders here done: this machine renders for the farm again.")


def local_tick(project_root: Path, as_host: bool) -> None:
    """This machine's renders here, each farm tick of its worker: moved on
    (unless this Blender is the farm host: its queue does it), a farm render
    asked to give way for them, the machine released once they're done.
    Never raises."""
    from .monitor import recover_interrupted_jobs
    from .queue import scan_processes, scan_queue
    from .workers import _worker_path

    try:
        waiting = local_jobs_in_flight()
        if not as_host and waiting:
            if not _recovered["done"]:
                _recovered["done"] = True
                recover_interrupted_jobs(local=True)
            scan_processes()
            scan_queue(project_root, local=True)
            waiting = local_jobs_in_flight()
        if waiting:
            _give_way_here(waiting)
            return
        worker = read_json_quiet(_worker_path()) or {}
        if worker.get("local_only") or worker.get("local_role"):
            _release(worker)
    except Exception as e:
        log("ERROR", "farm", f"Render here: {e}")
