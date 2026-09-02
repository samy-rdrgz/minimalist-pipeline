"""Farm management panel in the 3D View sidebar."""

import json
from pathlib import Path

import bpy

from ..farm import get_monitor_cache
from ..lib import ConfigCache, addon_pref, draw_box_tip, get_active_project_root

FIRST_COLUMN = 0.4


class PIPELINE_PT_farm_panel(bpy.types.Panel):
    """Farm monitoring."""

    bl_label = ""
    bl_idname = "PIPELINE_PT_farm_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pipeline"
    bl_parent_id = "PIPELINE_PT_main"
    bl_options = {"HIDE_HEADER", "HEADER_LAYOUT_EXPAND"}

    def _get_jobs(self, jobs_dir: Path) -> list[dict]:
        jobs = []
        for i in jobs_dir.glob("job_*.json"):
            filepath = jobs_dir / i.name
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                jobs.append(data)
            except Exception:
                pass
        return jobs

    @classmethod
    def poll(cls, context):
        return addon_pref(context) is not None and get_active_project_root()

    def draw(self, context):
        layout = self.layout

        draw_box_tip(
            layout,
            context,
            "Monitor runs the render queue (one per project). Worker "
            "means this machine renders jobs. Both coordinate through "
            "files in the project (no server, no network setup).",
        )

        box = layout.box().column(align=True)

        monitor = ConfigCache.get_path("monitor_file")
        is_monitor = monitor.exists()

        if not is_monitor:
            box.label(text=" Farm : not running", icon="LAYER_ACTIVE")
            box.separator()
            box.operator(
                "pipeline.farm_launch_monitor", text="Launch farm", icon="TRIA_RIGHT"
            )
        else:
            cache = get_monitor_cache()
            # Monitor status
            status = cache["status"]
            last_seen = (
                cache["last_tick"].strftime("%H:%M:%S") if cache["last_tick"] else "?"
            )
            icons = {"running": "CHECKMARK", "stale": "ERROR", "dead": "PANEL_CLOSE"}
            loading = (
                f"{(cache['counter'] % 4) * '.'}{(3 - (cache['counter'] % 4)) * ' '}"
            )
            labels = {
                "running": f"Farm running {loading} {cache['lock_user']} @ {cache['lock_machine']}",
                "stale": f"Farm stale: {cache['lock_user']} (last seen {last_seen})",
                "dead": f"Farm dead: {cache['lock_user']} (last seen {last_seen})",
                "unknown": "...",
            }
            box.label(
                text=labels.get(status, "..."), icon=icons.get(status, "QUESTION")
            )
            box.separator()
            if status == "running":
                box.operator("pipeline.farm_kill_monitor", text="Kill farm", icon="X")
            elif status == "stale":
                # Lock not confirmed dead yet -- offer both: kill in case
                # it's still ticking, or take over outright.
                box.operator("pipeline.farm_kill_monitor", text="Kill farm", icon="X")
                box.operator(
                    "pipeline.farm_launch_monitor",
                    text="Take over",
                    icon="TRIA_RIGHT",
                )
            elif status == "dead":
                box.operator(
                    "pipeline.farm_launch_monitor",
                    text="Launch Farm",
                    icon="TRIA_RIGHT",
                )

        box.operator("pipeline.farm_monitor", text="Farm monitor", icon="CONSOLE")
