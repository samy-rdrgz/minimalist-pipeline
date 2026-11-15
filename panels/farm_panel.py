"""Farm management panel in the 3D View sidebar."""


import bpy

from ..farm import (
    get_monitor_cache,
    this_instance_is_worker,
)
from ..lib import (
    addon_pref,
    draw_box_tip,
    get_active_project_root,
)


class M_PIPELINE_PT_farm_panel(bpy.types.Panel):
    """Farm monitoring."""

    bl_label = ""
    bl_idname = "M_PIPELINE_PT_farm_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pipeline"

    bl_options = {"HEADER_LAYOUT_EXPAND", "DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return addon_pref(context) is not None and get_active_project_root()

    def draw_header(self, context):
        layout = self.layout.row(align=True)
        layout.separator(factor=0.4)
        # A button opening Farm monitoring, its text left-aligned like a label.
        status_row = layout.row(align=True)
        status_row.alignment = "LEFT"

        # From the status cache (refreshed by _status_tick() every 10 s),
        # never monitor.lock.exists() here: a disk call per redraw is a
        # network round-trip on a share, even with this panel collapsed.
        is_monitor = get_monitor_cache().get("status") not in ("not running", "unknown")

        if not is_monitor:
            status_row.operator(
                "m_pipeline.open_live_page",
                text="Farm: Not running",
                icon="GHOST_DISABLED",
                emboss=False,
            ).tab = "farm"
            layout.operator(
                "m_pipeline.farm_launch_monitor",
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
                "running": "Farm: Running",
                "stale": "Farm: Stale",
                "dead": "Farm: Dead",
                "unknown": "Farm: ...",
            }
            status_row.operator(
                "m_pipeline.open_live_page",
                text=labels.get(status, "Farm: ..."),
                icon=icons.get(status, "GHOST_DISABLED"),
                emboss=False,
            ).tab = "farm"
            if status != "running":
                layout.operator(
                    "m_pipeline.farm_launch_monitor",
                    text="",
                    icon="TRIA_RIGHT",
                    emboss=False,
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

        layout.operator("m_pipeline.open_live_page", text="Farm in browser", icon="WORKSPACE").tab = "farm"
        layout.separator()

        # Status cache, not monitor.lock.exists() -- see draw_header().
        is_monitor = get_monitor_cache().get("status") not in ("not running", "unknown")

        if is_monitor:
            cache = get_monitor_cache()
            status = cache["status"]

            if status in ("running", "stale"):
                layout.operator(
                    "m_pipeline.farm_kill_monitor", text="Kill farm", icon="X"
                )
            if status not in ("running", "stale"):
                layout.operator(
                    "m_pipeline.farm_launch_monitor",
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
                "m_pipeline.farm_launch_monitor", text="Launch farm", icon="TRIA_RIGHT"
            )
        if this_instance_is_worker():
            layout.operator(
                "m_pipeline.farm_kill_self_worker", text="Stop this worker", icon="X"
            )
        else:
            layout.operator(
                "m_pipeline.farm_add_self_worker",
                text="Add this machine as worker",
                icon="ADD",
            )


