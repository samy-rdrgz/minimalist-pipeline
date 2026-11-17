# templates/relink_entry.py
"""Headless entry point for Update links (lib/relink.py): run on the source
.blend, opened by Blender before this script (--factory-startup: none of
the addon's handlers). Each library whose path is an old one of the
request is pointed at its new path and reloaded, then the file is saved
as the request's new version -- the source untouched. Writes {"status",
"message"} back into the request file."""

import json
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
request_path = argv[0]
with open(request_path, "r", encoding="utf-8") as f:
    request = json.load(f)


def norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(bpy.path.abspath(p)))


result = {"status": "error", "message": "Unknown error."}
try:
    mapping = {norm(old): new for old, new in request["mapping"]}
    out = request["out"]
    if os.path.exists(out):
        raise RuntimeError(f"{os.path.basename(out)} exists already")
    done, missing = [], []
    for lib in bpy.data.libraries:
        new = mapping.get(norm(lib.filepath))
        if not new:
            continue
        if not os.path.isfile(new):
            missing.append(os.path.basename(new))
            continue
        old_name = os.path.basename(bpy.path.abspath(lib.filepath))
        # Relative to the new version's folder: the source's, the same.
        lib.filepath = bpy.path.relpath(new, start=os.path.dirname(out))
        lib.reload()
        done.append(f"{old_name} -> {os.path.basename(new)}")
    if missing:
        raise RuntimeError("not found: " + ", ".join(missing))
    if not done:
        raise RuntimeError("none of its libraries is one of the links to update")
    bpy.ops.wm.save_as_mainfile(filepath=out, copy=True, relative_remap=True)
    result = {"status": "ok", "message": f"{len(done)} link(s): " + "; ".join(done)}
except Exception as e:
    result = {"status": "error", "message": str(e)}

with open(request_path, "w", encoding="utf-8") as f:
    json.dump(result, f)
