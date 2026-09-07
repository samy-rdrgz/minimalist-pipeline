# templates/batch_create_entry.py
"""Headless entry point for batch asset/shot creation from a CSV (see
lib/batch.py / operators/batch_ops.py). Runs once per row in its own
disposable Blender process, always reset to the empty template first, so
nothing accumulates between rows and the artist's live session is untouched."""

import json
import sys
from pathlib import Path

import addon_utils
import bpy

# Fresh subprocess: Blender's own extension loader already makes the addon
# importable, no manual sys.path edit needed here.
addon_utils.enable("minimalist_pipeline", default_set=False, persistent=False)

from minimalist_pipeline.lib import (
    DEFAULT_ASSET_DEPARTMENTS,
    DEFAULT_SHOT_DEPARTMENTS,
    ConfigCache,
    create_asset_file,
    create_shot_file,
    json_get,
    resolve_batch_departments,
    resolve_timeline,
    set_daemon_active_project_root,
)

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
request_path = Path(argv[0])

with open(request_path, "r", encoding="utf-8") as f:
    request = json.load(f)

result = {"status": "error", "message": "Unknown error."}
try:
    bpy.ops.wm.read_homefile(use_empty=True)

    project_root = Path(request["project_root"])
    # Background process never loads a .blend, so get_active_project_root()
    # has nothing else to resolve the project from -- point it at the one
    # the request was made for, before anything below touches ConfigCache.
    set_daemon_active_project_root(project_root)
    row = request["row"]
    config = ConfigCache.get()

    if request["kind"] == "asset":
        valid = json_get(config, "assets_departments", DEFAULT_ASSET_DEPARTMENTS)
        departments = resolve_batch_departments(
            row.get("departments", ""),
            default=DEFAULT_ASSET_DEPARTMENTS,
            valid=valid,
        )
        path = create_asset_file(
            project_root,
            prefix=row["prefix"].strip(),
            name=row["name"],
            departments=departments,
            description=row.get("description", "") or "",
        )
    else:
        valid = json_get(config, "shots_departments", DEFAULT_SHOT_DEPARTMENTS)
        departments = resolve_batch_departments(
            row.get("departments", ""),
            default=DEFAULT_SHOT_DEPARTMENTS,
            valid=valid,
        )
        timeline = resolve_timeline(
            frame_start=int(row["frame_start"]) if row.get("frame_start") else None,
            frame_end=int(row["frame_end"]) if row.get("frame_end") else None,
            frame_duration=int(row["frame_duration"])
            if row.get("frame_duration")
            else None,
            config=config,
        )
        path = create_shot_file(
            project_root,
            sequence_number=int(row["sequence"]),
            shot_number=int(row["shot"]),
            departments=departments,
            description=row.get("description", "") or "",
            timeline=timeline,
        )
    result = {"status": "ok", "message": str(path)}
except Exception as e:
    result = {"status": "error", "message": str(e)}

with open(request_path, "w", encoding="utf-8") as f:
    json.dump(result, f)
