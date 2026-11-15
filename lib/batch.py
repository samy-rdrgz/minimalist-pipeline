"""Batch creation of assets/shots from a CSV -- each row runs in its own
disposable headless Blender subprocess (see templates/batch_create_entry.py),
so the artist's live session is never touched and nothing accumulates
between rows."""

import json
import subprocess
import tempfile
from pathlib import Path

from .config import prefix_to_parent_folder
from .core import ADDON_PACKAGE, blender_command, read_csv
from .errors import PipelineError
from .logs import log


def parse_asset_batch_csv(filepath: Path) -> list[dict]:
    """Parse an asset batch CSV: 'prefix' and 'name' required,
    'departments'/'description' optional. Raises if the header is missing a
    required column."""
    rows = read_csv(filepath)
    if rows and not ("prefix" in rows[0] and "name" in rows[0]):
        raise PipelineError("CSV header is missing 'prefix' and/or 'name'.")
    return rows


def parse_shot_batch_csv(filepath: Path) -> list[dict]:
    """Parse a shot batch CSV: 'sequence' and 'shot' required (dash-joined
    for a multi-shot row -- see NOTES.md, "CSV batch: multi-shot rows"),
    'frame_start'/'frame_end'/'frame_duration'/'timeline'/'departments'/
    'description' optional. Raises if the header is missing a required
    column."""
    rows = read_csv(filepath)
    if rows and not ("sequence" in rows[0] and "shot" in rows[0]):
        raise PipelineError("CSV header is missing 'sequence' and/or 'shot'.")
    return rows


def resolve_batch_departments(
    raw: str, *, default: list[str], valid: list[str]
) -> list[str]:
    """Turn a CSV row's 'departments' cell (comma-separated) into a filtered
    list, falling back to `default` when empty. Names not in `valid` are
    dropped and logged, never blocking the row."""
    names = [d.strip() for d in raw.split(",")] if raw else list(default)
    names = [d for d in names if d]

    resolved = []
    for d in names:
        if d in valid:
            resolved.append(d)
        else:
            log(
                "WARNING",
                "batch_create",
                f"Department '{d}' is not in the project config -- skipped.",
            )
    return resolved


def parse_batch_assignees(raw, departments: list[str]) -> dict[str, list[str]]:
    """A row's 'assignees' cell as {department: [names]}, among its
    departments: "animation:tom, léa; layout:sam", or names alone ("tom")
    for every department; a dict (the page's) taken as it is. Lower case,
    each once; a department it doesn't require dropped."""
    out: dict[str, list[str]] = {}
    if isinstance(raw, dict):
        parts = [(str(d), p if isinstance(p, list) else str(p).split(",")) for d, p in raw.items()]
    else:
        parts = []
        for chunk in str(raw or "").split(";"):
            dep, sep, names = chunk.partition(":")
            parts.append((dep, names.split(",")) if sep else ("", dep.split(",")))
    for dep, names in parts:
        names = [str(n).strip().lower() for n in names if str(n).strip()]
        dep = dep.strip().lower()
        for d in [dep] if dep else departments:
            if d in departments and names:
                out[d] = list(dict.fromkeys([*out.get(d, []), *names]))
    return out


def asset_batch_exists(
    project_root: Path, prefix: str, name: str, config: dict
) -> bool:
    """Whether prefix_name's asset folder already exists (any version)."""
    parent = prefix_to_parent_folder(prefix, config)
    return (project_root / parent / prefix / f"{prefix}_{name}").exists()


def shot_batch_exists(project_root: Path, sequence_label: str, shot_label: str) -> bool:
    """Whether sequence/shot's folder already exists (any version)."""
    return (project_root / "shots" / sequence_label / shot_label).exists()


def launch_batch_create_entry(
    *, project_root: Path, kind: str, row: dict
) -> tuple[subprocess.Popen, Path]:
    """Launch one asset/shot creation in a disposable headless Blender
    subprocess (non-blocking). Returns (process, request_path): the entry
    script reads its request from and writes its result
    ({"status", "message"}) into that temp JSON -- caller polls process,
    then reads and deletes request_path (see read_batch_result)."""
    import bpy

    # The same install, so the addon is importable there too.
    if not bpy.app.binary_path:
        raise PipelineError("Could not resolve the running Blender executable.")

    fd, tmp_name = tempfile.mkstemp(suffix=".json", prefix="pipeline_batch_")
    request_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "project_root": str(project_root),
                    "kind": kind,
                    "row": row,
                    "addon_module": ADDON_PACKAGE,
                },
                f,
            )
    except Exception:
        request_path.unlink(missing_ok=True)
        raise

    process = subprocess.Popen(
        blender_command("batch_create_entry.py", [request_path]),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return process, request_path


def read_batch_result(request_path: Path) -> dict:
    """Read back the {"status", "message"} the entry script wrote into
    request_path once its subprocess has exited. Never raises -- a missing
    or unreadable file just reports as a generic failure, the caller (a
    modal operator) has no PipelineError catch to route this through."""
    try:
        with open(request_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Could not read result: {e}"}
