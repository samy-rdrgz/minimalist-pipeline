# templates/worker_render_entry.py
import sys

import addon_utils
import bpy

# Fresh subprocess: Blender's own extension loader already makes the addon
# importable, no manual sys.path edit needed here.
addon_utils.enable("minimalist_pipeline", default_set=False, persistent=False)

from minimalist_pipeline.farm import apply_custom_preset

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
job_id = argv[argv.index("--job-id") + 1]
preset = argv[argv.index("--preset") + 1]

scene = bpy.context.scene

scene.render.use_placeholder = True
scene.render.use_overwrite = False
apply_custom_preset(preset, scene, job_id)

bpy.ops.render.render(animation=True)  # renders HERE, after the presets
