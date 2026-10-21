"""Project monitoring, drawn in its own window (lib/monitoring.py): the list
of every tracked file, or one file's detail."""

import bpy

from ..lib import (
    ConfigCache,
    ensure_monitoring_tick,
    get_active_project_root,
    is_monitoring_screen,
    json_get,
    popup_detail,
)
from .tracking_panel import draw_file_details, draw_monitor_table


class M_PIPELINE_PT_monitoring(bpy.types.Panel):
    """Project monitoring window's content."""

    bl_label = "Project monitoring"
    bl_idname = "M_PIPELINE_PT_monitoring"
    # The Properties editor's Tool tab shows the 3D View sidebar's "Tool"
    # panels -- the only way into it. Headerless: drawn first, right under
    # Blender's own headerless active tool, the tab's other panels below.
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tool"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        # Only in the monitoring window: never the N panel's Tool tab, nor
        # another Properties editor.
        return (
            context.area is not None
            and context.area.type == "PROPERTIES"
            and is_monitoring_screen(context.screen)
        )

    def draw(self, context):
        layout = self.layout
        # The window may come back with a .blend saved with it open, no
        # operator run: the scan and redraws start from here then.
        ensure_monitoring_tick()
        project_root = get_active_project_root()
        if not project_root:
            layout.label(text="No active project.", icon="ERROR")
            return

        state = context.window_manager.pipeline_monitoring
        if popup_detail("file"):
            draw_file_details(state, context, layout)
            return

        filters = layout.box().split(factor=0.3)
        filters.label(text="Filters", icon="FILTER")
        filters_btn = filters.row()
        filters_btn.prop(state, "file_type", expand=True)

        if state.file_type == "asset":
            filters_btn.prop(state, "asset_prefix", text="")
            columns = json_get(ConfigCache.get(), "assets_departments", [])
        else:
            filters_btn.prop(state, "sequence", text="")
            columns = json_get(ConfigCache.get(), "shots_departments", [])

        filters_btn.prop(state, "search", text="", icon="VIEWZOOM")
        # Icon only: the property's description is the tooltip.
        filters_btn.prop(state, "only_farm", text="", icon="VIEW_CAMERA_UNSELECTED")
        filters_btn.prop(state, "only_rtk", text="", icon="LOOP_BACK")

        layout.separator(factor=0.5)
        draw_monitor_table(state, context, layout, columns, project_root)
