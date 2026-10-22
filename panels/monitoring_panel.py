"""The monitoring windows' content (lib/monitoring.py): Project monitoring --
every tracked file, or one file's detail -- and Farm monitoring -- the
farm's jobs or machines, or one job's detail."""

import bpy

from ..lib import (
    ConfigCache,
    ensure_monitoring_tick,
    get_active_project_root,
    json_get,
    monitoring_detail,
    monitoring_kind,
)
from .farm_panel import (
    draw_farm_job_details,
    draw_farm_jobs,
    draw_farm_worker_details,
    draw_farm_workers,
)
from .tracking_panel import draw_file_details, draw_monitor_table


class _MonitoringPanel:
    # The Properties editor's Tool tab shows the 3D View sidebar's "Tool"
    # panels -- the only way into it. Headerless: drawn first, right under
    # Blender's own headerless active tool (a panel with a header goes after
    # the tab's own, Options and Workspace).
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tool"
    bl_options = {"HIDE_HEADER"}
    kind = ""

    @classmethod
    def poll(cls, context):
        # Only in its own window: never the N panel's Tool tab, nor another
        # Properties editor.
        return (
            context.area is not None
            and context.area.type == "PROPERTIES"
            and monitoring_kind(context.screen) == cls.kind
        )

    def draw(self, context):
        # The window may come back with a .blend saved with it open, no
        # operator run: the scan and redraws start from here then.
        ensure_monitoring_tick()
        layout = self.layout
        if not get_active_project_root():
            layout.label(text="No active project.", icon="ERROR")
        else:
            self.draw_content(context, layout)
        # A window's height of blank below: the Tool tab's other panels
        # (Options, Workspace) out of sight, even scrolled.
        spacer = layout.column()
        spacer.scale_y = context.region.height / (20 * (context.preferences.system.ui_scale or 1.0))
        spacer.label(text="")


class M_PIPELINE_PT_monitoring(_MonitoringPanel, bpy.types.Panel):
    """Project monitoring window's content."""

    bl_label = "Pipeline: Project monitoring"
    bl_idname = "M_PIPELINE_PT_monitoring"
    kind = "project"

    def draw_content(self, context, layout):
        state = context.window_manager.pipeline_monitoring
        missing = monitoring_detail("missing_file")
        if missing:
            row = layout.row(align=True)
            row.box().operator(
                "m_pipeline.tracking_file_details", text="", icon="BACK", emboss=False
            )
            row.box().label(
                text=f"File not found in this project: {missing}", icon="ERROR"
            )
            return
        if monitoring_detail("file"):
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
        filters_btn.prop(state, "sort", text="", icon="SORTTIME")

        layout.separator(factor=0.5)
        draw_monitor_table(state, context, layout, columns, get_active_project_root())


class M_PIPELINE_PT_farm_monitoring(_MonitoringPanel, bpy.types.Panel):
    """Farm monitoring window's content."""

    bl_label = "Pipeline: Farm monitoring"
    bl_idname = "M_PIPELINE_PT_farm_monitoring"
    kind = "farm"

    def draw_content(self, context, layout):
        if monitoring_detail("job"):  # opened from a worker's too: on top
            draw_farm_job_details(layout.box(), context)
            return
        if monitoring_detail("worker"):
            draw_farm_worker_details(layout.box(), context)
            return

        state = context.window_manager.pipeline_farm_monitoring
        filter_box = layout.box()
        filters = filter_box.split(factor=0.5)
        filters.label(text="Filters", icon="FILTER")
        tabs = filters.row()
        tabs.prop(state, "view", expand=True)
        # get_path(): a plain join, memoized -- no disk access in draw().
        op = tabs.operator("wm.open_folder", text="", icon="FILE_FOLDER", emboss=False)
        op.filepath = str(ConfigCache.get_path("farm"))
        op.custom_tooltip = "Open the farm's folder (config/.farm: queue, workers, logs)"
        if state.view == "jobs":
            job_filters = filter_box.split(factor=0.5)
            job_filters.prop(state, "search", text="", icon="VIEWZOOM")
            job_btn = job_filters.row()
            job_btn.prop(state, "state", expand=True)
            job_btn.prop(state, "only_mine", text="Mine", icon="USER")

        box = layout.box()
        if state.view == "jobs":
            draw_farm_jobs(state, context, box)
        else:
            draw_farm_workers(context, box)
