"""Launch the actual render commands -- local Popen or SSH, one machine or
several, depending on render_mode."""

import json
import subprocess
from pathlib import Path

from ..lib import locked_json, log, now, to_absolute

_active_processes: dict[str, list[tuple[subprocess.Popen, str]]] = {}

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


def render_mode_auto(filepath: str) -> str | None:
    """Resolve render_mode="auto": fall back to "single" if the last placeholder
    render on this file had corrupted frames, else let the caller decide (None)."""
    if last_render_had_collision(filepath):
        return "single"
    else:
        return None


def render_history_path(filepath: str) -> Path:
    """Path to the render_history.json sitting next to filepath."""
    return Path(filepath).parent / "render_history.json"


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
