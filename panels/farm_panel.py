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

    bl_options = {"HEADER_LAYOUT_EXPAND", "DEFAULT_CLOSED"}

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

    def draw_header(self, context):
        layout = self.layout.row(align=True)
        layout.separator(factor=0.4)

        monitor = ConfigCache.get_path("monitor_file")
        is_monitor = monitor.exists()

        if not is_monitor:
            layout.label(text="Farm : not running", icon="GHOST_DISABLED")
            layout.operator(
                "pipeline.farm_launch_monitor",
                text="",
                icon="TRIA_RIGHT",
                emboss=False,
            )

        else:
            cache = get_monitor_cache()
            status = cache["status"]
            icons = {
                "running": "CHECKMARK",
                "stale": "FREEZE",
                "dead": "GHOST_DISABLED",
            }

            labels = {
                "running": "Farm : Running",
                "stale": "Farm : Stale",
                "dead": "Farm : Dead",
                "unknown": "Farm : ...",
            }
            layout.label(
                text=labels.get(status, "Farm : ..."),
                icon=icons.get(status, "GHOST_DISABLED"),
            )
            if status != "running":
                layout.operator(
                    "pipeline.farm_launch_monitor",
                    text="",
                    icon="TRIA_RIGHT",
                    emboss=False,
                )
        layout.operator(
            "pipeline.farm_monitor", text="", icon="SEQ_STRIP_MODIFIER", emboss=False
        )
        layout.separator(factor=1.5)

    def draw(self, context):
        layout = self.layout.column(align=True)

        draw_box_tip(
            layout,
            context,
            "Monitor runs the render queue (one per project). Worker "
            "means this machine renders jobs. Both coordinate through "
            "files in the project (no server, no network setup).",
        )

        monitor = ConfigCache.get_path("monitor_file")

        is_monitor = monitor.exists()

        if is_monitor:
            cache = get_monitor_cache()
            status = cache["status"]

            if status in ("running", "stale"):
                layout.operator(
                    "pipeline.farm_kill_monitor", text="Kill farm", icon="X"
                )
            if status not in ("running", "stale"):
                layout.operator(
                    "pipeline.farm_launch_monitor",
                    text="Launch farm",
                    icon="TRIA_RIGHT",
                )

            last_seen = (
                cache["last_tick"].strftime("%H:%M:%S") if cache["last_tick"] else "?"
            )

            labels = {
                "running": f"Running {cache['lock_user']} @ {cache['lock_machine']}",
                "stale": f"Stale: {cache['lock_user']} (last seen {last_seen})",
                "dead": f"Dead: {cache['lock_user']} (last seen {last_seen})",
                "unknown": "...",
            }
            info = layout.row()
            info.active = False
            info.label(text=labels.get(status, "..."), icon="DOT")
        else:
            layout.operator(
                "pipeline.farm_launch_monitor", text="Launch farm", icon="TRIA_RIGHT"
            )
        layout.operator(
            "pipeline.farm_monitor", text="Farm monitor", icon="SEQ_STRIP_MODIFIER"
        )
