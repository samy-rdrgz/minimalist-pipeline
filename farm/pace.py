"""Seconds per frame per pre-render script, project-wide: a file never
rendered with a preset (its first HD render after LD ones) is estimated at
that preset's pace on the other files, not at its own LD pace.
.farm/preset_pace.json, {"presets": {script: [record, ...]}} -- the last
KEEP finished renders of each, written by the farm host only: each render
it ends (note_preset_pace()), and once from every file's
render_history.json when the file is missing (seed_preset_pace()). See
NOTES.md, "Estimate before a render starts"."""

import os
import threading
from pathlib import Path

from ..lib import ConfigCache, locked_json, log, now, read_json_quiet
from ..lib.background import background_work
from ..lib.tracking import _DATA_ROOTS, _walk_owner_dirs

# Renders kept per preset: recent enough to follow the project's look
# getting heavier, enough not to hang on one odd shot.
KEEP = 20


def pace_record(entry: dict) -> tuple[str, dict] | None:
    """(script, record) of a render_history entry worth averaging: finished,
    timed, its script recorded. record: {"job_id", "at", "seconds_per_frame",
    "frames"}. None otherwise. Pure."""
    if not isinstance(entry, dict) or entry.get("status") != "finished":
        return None
    spf = entry.get("seconds_per_frame")
    if not spf or "prerender_script" not in entry:
        return None
    frames = 1
    span = entry.get("frame_range_rendered") or ()
    try:
        frames = max(1, int(span[1]) - int(span[0]) + 1)
    except (IndexError, TypeError, ValueError):
        pass
    return entry["prerender_script"] or "", {
        "job_id": entry.get("job_id", ""),
        "at": entry.get("completed_at") or "",
        "seconds_per_frame": float(spf),
        "frames": frames,
    }


def _merge(data: dict, found: dict) -> dict:
    """data with found ({script: [record]}) added: each record once (job id
    and time), oldest first, the last KEEP per script. "averages" written
    alongside, for whoever opens the file: each script's pace at a glance
    (preset_averages() is what the farm reads)."""
    presets = data.setdefault("presets", {})
    for script, records in found.items():
        mine = presets.get(script) or []
        seen = {(r.get("job_id"), r.get("at")) for r in mine}
        mine += [r for r in records if (r["job_id"], r["at"]) not in seen]
        mine.sort(key=lambda r: r.get("at") or "")
        presets[script] = mine[-KEEP:]
    data["averages"] = {
        script: {
            "seconds_per_frame": spf,
            "per_frame": _clock(spf),
            "renders": count,
        }
        for script, (spf, count) in sorted(preset_averages(data).items())
    }
    return data


def _clock(seconds: float) -> str:
    """ "1m23s", "45s", "1h02m" -- a pace read by a person."""
    seconds = round(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
    if seconds >= 60:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds}s"


def note_preset_pace(entry: dict) -> None:
    """Add a render just ended (construct_history()'s entry) to its preset's
    pace. Never raises: the render is recorded in its history either way."""
    record = pace_record(entry)
    if not record:
        return
    try:
        with locked_json(ConfigCache.get_path("farm_preset_pace")) as box:
            box["data"] = _merge(box["data"] or {}, {record[0]: [record[1]]})
            box["action"] = "to_write"
    except Exception as e:
        log("WARNING", "farm", f"Preset pace not updated: {e}")


def preset_averages(data: dict) -> dict:
    """{script: (seconds per frame, renders)} from preset_pace.json's data:
    weighted by frames -- a 200-frame shot counts more than a 10-frame one.
    Pure."""
    out = {}
    for script, records in ((data or {}).get("presets") or {}).items():
        frames = sum(r.get("frames") or 1 for r in records or [])
        if not frames:
            continue
        seconds = sum(
            (r.get("seconds_per_frame") or 0) * (r.get("frames") or 1) for r in records
        )
        if seconds:
            out[script] = (round(seconds / frames, 1), len(records))
    return out


# Project roots whose seed has started -> its findings, None while it reads.
_seeds: dict = {}


def ensure_preset_pace(project_root: Path) -> None:
    """Farm host, each tick: no preset_pace.json yet, fill it from the
    project's past renders -- read on a thread (read_past_paces()), written
    here on a later tick: locked_json() and log() read Blender's prefs,
    main thread only. Once per project and session."""
    key = str(project_root)
    if key not in _seeds:
        _seeds[key] = None
        if ConfigCache.get_path("farm_preset_pace").exists():
            _seeds[key] = {}  # nothing to seed
            return
        threading.Thread(
            target=read_past_paces, args=(Path(project_root), key), daemon=True
        ).start()
        return
    found = _seeds[key]
    if not found:
        return  # still reading, or done
    _seeds[key] = {}
    try:
        with locked_json(ConfigCache.get_path("farm_preset_pace")) as box:
            data = _merge(box["data"] or {}, found)
            data["seeded_at"] = now()
            box["data"] = data
            box["action"] = "to_write"
    except Exception as e:
        log("WARNING", "farm", f"Preset pace not written: {e}")
        return
    count = sum(len(v) for v in found.values())
    log("INFO", "farm", f"Preset pace: {count} past renders over {len(found)} presets.")


def read_past_paces(root: Path, key: str) -> None:
    """Every tracked folder's render_history.json read (one listing per
    folder, as the project scan), its timed renders by preset, left in
    _seeds[key] for ensure_preset_pace(). Thread-safe (pure os/json)."""
    found: dict = {}
    try:
        with background_work():
            for top in _DATA_ROOTS:
                for owner in _walk_owner_dirs(root / top):
                    history = owner / ".pipeline" / "render_history.json"
                    if not os.path.isfile(history):
                        continue
                    for entry in (read_json_quiet(history) or {}).get("entries") or []:
                        record = pace_record(entry)
                        if record:
                            found.setdefault(record[0], []).append(record[1])
    except Exception:
        pass  # what was read is still worth having
    _seeds[key] = found
