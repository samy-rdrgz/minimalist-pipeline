# templates/batch_create_entry.py
"""Headless entry point for batch asset/shot creation from a CSV (see
lib/batch.py / operators/batch_ops.py). Runs once per row in its own
disposable Blender process, always reset to the empty template first, so
nothing accumulates between rows and the artist's live session is untouched."""

import importlib
import json
import sys
from pathlib import Path

import addon_utils
import bpy

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
request_path = Path(argv[0])

with open(request_path, "r", encoding="utf-8") as f:
    request = json.load(f)

result = {"status": "error", "message": "Unknown error."}
try:
    # Real (possibly namespaced) module name from the request -- see
    # NOTES.md, "CSV batch: the subprocess couldn't import itself".
    addon_module = request["addon_module"]
    addon_utils.enable(addon_module, default_set=False, persistent=False)
    lib = importlib.import_module(f"{addon_module}.lib")

    bpy.ops.wm.read_homefile(use_empty=True)

    project_root = Path(request["project_root"])
    # Background process never loads a .blend, so get_active_project_root()
    # has nothing else to resolve the project from -- point it at the one
    # the request was made for, before anything below touches ConfigCache.
    lib.set_daemon_active_project_root(project_root)
    row = request["row"]
    config = lib.ConfigCache.get()

    if request["kind"] == "asset":
        valid = lib.json_get(
            config, "assets_departments", lib.DEFAULT_ASSET_DEPARTMENTS
        )
        departments = lib.resolve_batch_departments(
            row.get("departments", ""),
            default=lib.DEFAULT_ASSET_DEPARTMENTS,
            valid=valid,
        )
        path = lib.create_asset_file(
            project_root,
            prefix=row["prefix"].strip(),
            name=row["name"],
            departments=departments,
            description=row.get("description", "") or "",
        )
    else:
        valid = lib.json_get(config, "shots_departments", lib.DEFAULT_SHOT_DEPARTMENTS)
        departments = lib.resolve_batch_departments(
            row.get("departments", ""),
            default=lib.DEFAULT_SHOT_DEPARTMENTS,
            valid=valid,
        )
        # "shot"/"timeline" -- see NOTES.md, "CSV batch: multi-shot rows".
        shot_numbers = lib.shots_in_segment(row["shot"])
        timeline_raw = row.get("timeline", "").strip()
        if timeline_raw:
            timeline = lib.parse_timeline(timeline_raw)
            if len(timeline) != len(shot_numbers) + 1:
                raise lib.PipelineError(
                    f"timeline has {len(timeline)} value(s), expected "
                    f"{len(shot_numbers) + 1} for {len(shot_numbers)} "
                    "shot(s) -- one start per shot, plus the block's end."
                )
        else:
            timeline = lib.resolve_timeline(
                frame_start=int(row["frame_start"]) if row.get("frame_start") else None,
                frame_end=int(row["frame_end"]) if row.get("frame_end") else None,
                frame_duration=int(row["frame_duration"])
                if row.get("frame_duration")
                else None,
                shot_count=len(shot_numbers),
                config=config,
            )
        path = lib.create_shot_file(
            project_root,
            sequence_number=int(row["sequence"]),
            shot_number=shot_numbers,
            departments=departments,
            description=row.get("description", "") or "",
            timeline=timeline,
        )
    result = {"status": "ok", "message": str(path)}
except Exception as e:
    result = {"status": "error", "message": str(e)}

with open(request_path, "w", encoding="utf-8") as f:
    json.dump(result, f)
