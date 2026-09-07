# templates/farm_entry_render_setup.py
import sys

import addon_utils

# Fresh subprocess: Blender's own extension loader already makes the addon
# importable, no manual sys.path edit needed here.
addon_utils.enable("minimalist_pipeline", default_set=False, persistent=False)

from minimalist_pipeline.farm import run_render_setup_entry

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
job_id = argv[argv.index("--job-id") + 1]

run_render_setup_entry(job_id)
