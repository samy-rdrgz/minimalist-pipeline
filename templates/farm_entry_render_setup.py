# templates/farm_entry_render_setup.py
import sys
from pathlib import Path

# Fresh subprocess: make the addon importable, then actually registered.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import addon_utils

addon_utils.enable("minimalist_pipeline", default_set=False, persistent=False)

from minimalist_pipeline.farm import run_render_setup_entry

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
job_id = argv[argv.index("--job-id") + 1]

run_render_setup_entry(job_id)
