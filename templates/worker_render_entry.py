# templates/worker_render_entry.py
import importlib
import sys

import addon_utils
import bpy

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
job_id = argv[argv.index("--job-id") + 1]
preset = argv[argv.index("--preset") + 1]
# Real (possibly namespaced) module name, passed by execute_render_request()
# -- see NOTES.md, "CSV batch: the subprocess couldn't import itself".
addon_module = argv[argv.index("--addon-module") + 1]

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

bpy.ops.render.render(animation=True)  # renders HERE, after the presets
