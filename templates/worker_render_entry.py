# templates/worker_render_entry.py
import importlib
import sys
import time

import addon_utils
import bpy

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
job_id = argv[argv.index("--job-id") + 1]
preset = argv[argv.index("--preset") + 1]
# Real (possibly namespaced) module name, passed by execute_render_request()
# -- see NOTES.md, "CSV batch: the subprocess couldn't import itself".
addon_module = argv[argv.index("--addon-module") + 1]
saved_file = argv[argv.index("--saved-file") + 1] if "--saved-file" in argv else ""
dispatch_id = argv[argv.index("--dispatch-id") + 1] if "--dispatch-id" in argv else ""

# Fresh subprocess: Blender's own extension loader already makes the addon
# importable, no manual sys.path edit needed here.
addon_utils.enable(addon_module, default_set=False, persistent=False)
farm = importlib.import_module(f"{addon_module}.farm")

scene = bpy.context.scene

scene.render.use_placeholder = True
scene.render.use_overwrite = False
# strict: a preset that can't be applied raises -- Blender exits with
# --python-exit-code before rendering anything, and the worker reports the
# render as failed. Never render with the .blend's own settings instead.
farm.apply_custom_preset(preset, scene, job_id, strict=True)


def record_saved(scene, *_):
    """After each frame Blender writes (never one it skips): one line, so the
    monitor can re-render a frame two machines both wrote -- see NOTES.md,
    "Frames written by two machines" -- and when (this machine's clock):
    the time between two lines is what a frame took (frame_seconds(),
    farm/workers.py)."""
    try:
        with open(saved_file, "a", encoding="utf-8") as f:
            f.write(f"{dispatch_id} {scene.frame_current} {time.time():.1f}\n")
    except OSError:
        pass


if saved_file:
    # A machine that left the render and came back appends to the same
    # record, same dispatch_id: this line keeps the time it was away out of
    # its first frame's (frame_seconds() starts again after it).
    try:
        with open(saved_file, "a", encoding="utf-8") as f:
            f.write(f"{dispatch_id} start {time.time():.1f}\n")
    except OSError:
        pass
    bpy.app.handlers.render_write.append(record_saved)

bpy.ops.render.render(animation=True)  # renders HERE, after the presets
