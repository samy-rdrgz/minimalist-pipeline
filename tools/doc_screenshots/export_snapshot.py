"""The project's snapshot exported headless to $OUT, for the screenshots (README.md); nothing written in the project."""
import bpy, addon_utils, importlib, os, sys
from pathlib import Path, PurePath
M = "bl_ext.user_default.minimalist_pipeline"
addon_utils.enable(M, default_set=True)
I = lambda m: importlib.import_module(M + m)
c = I(".lib.config"); s = I(".lib.monitoring.snapshot"); pl = I(".lib.monitoring.progress_log")
root = Path(sys.argv[-1]); c.set_daemon_active_project_root(root)
cfg = c.ConfigCache.get()
lib = I(".lib")
thumbs = {"size": lib.thumbnail_size(cfg) if hasattr(lib, "thumbnail_size") else 240, "blender": bpy.app.binary_path, "ffmpeg": None}
try:
    thumbs["ffmpeg"] = lib.resolve_ffmpeg()
except Exception as e: print("ff", e)
data = s.read_snapshot_data(root, thumbs, c.json_get(cfg, "naming.version.prefix", "v"))
meta = {"project": "demo", "scan_started_at": None, "exported_by": "samyr", "addon_version": "2.0.0", "lang": "en_US"}
farm = I(".farm").farm_activity()
snap = s.build_snapshot(data, cfg, meta, farm=farm)
snap["meta"]["history"] = pl.days(root)
out = Path(os.environ["OUT"])
snap["meta"]["videos"] = {"mode": "none", "base": None, "files": [], "local": PurePath(os.path.relpath(root / "renders", out.parent)).as_posix()}
s.write_snapshot(snap, out)
print("WROTE", out, out.stat().st_size)
