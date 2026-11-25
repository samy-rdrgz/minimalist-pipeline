"""A Blender serving a project's live page for the screenshots (README.md): run headless,
the addon as an extension, the page's turn pumped by hand (no timers in -b), as samyr · prod."""
import bpy, addon_utils, time, sys, importlib
M = "bl_ext.user_default.minimalist_pipeline"
addon_utils.enable(M, default_set=True)
c = importlib.import_module(M + ".lib.config")
live = importlib.import_module(M + ".lib.monitoring.live")
root = sys.argv[-2]
c.set_daemon_active_project_root(root)
p = bpy.context.preferences.addons[M].preferences
p.user_name = "samyr"
try: p.validation_role = "prod"
except Exception as e: print("role", e)
try: p.experience_level = "ADVANCED"
except Exception as e: print("lvl", e)
ses = importlib.import_module(M + ".lib.session"); ses.get_user = lambda context=None: "samyr"; ses.get_user_role = lambda context=None: "prod"; live.get_user = ses.get_user
live.get_user_role = ses.get_user_role
u = live.start(root)
print("URL", u, flush=True)
end = time.time() + float(sys.argv[-1])
while time.time() < end:
    live._tick()
    time.sleep(0.25)
print("DONE", flush=True)
