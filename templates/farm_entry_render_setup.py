# templates/farm_entry_render_setup.py
import importlib
import sys

import addon_utils

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
job_id = argv[argv.index("--job-id") + 1]
# Real (possibly namespaced, e.g. bl_ext.user_default.minimalist_pipeline)
# module name, passed by run_render_setup() -- see NOTES.md, "CSV batch: the
# subprocess couldn't import itself".
addon_module = argv[argv.index("--addon-module") + 1]

# Fresh subprocess: Blender's own extension loader already makes the addon
# importable, no manual sys.path edit needed here.
addon_utils.enable(addon_module, default_set=False, persistent=False)
farm = importlib.import_module(f"{addon_module}.farm")

farm.run_render_setup_entry(job_id)
