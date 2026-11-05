"""The monitoring windows' content (lib/monitoring.py): Project monitoring --
every tracked file, or one file's detail --, Farm monitoring -- the farm's
jobs or machines, or one job's detail -- and the Pipeline log."""

import bpy

from ..lib import (
    ConfigCache,
    addon_pref,
    draw_onboarding,
    region_char_budget,
    ensure_monitoring_tick,
    get_active_project_root,
    json_get,
    monitoring_detail,
    monitoring_kind,
)
from .logs_panel import draw_pipeline_logs
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
        filters_btn.prop(state, "only_to_validate", text="", icon="SOLO_OFF")
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


class M_PIPELINE_PT_log_monitoring(_MonitoringPanel, bpy.types.Panel):
    """Pipeline log window's content."""

    bl_label = "Pipeline: Pipeline log"
    bl_idname = "M_PIPELINE_PT_log_monitoring"
    kind = "log"

    def draw_content(self, context, layout):
        state = context.window_manager.pipeline_log_monitoring
        filters = layout.box().split(factor=0.3)
        filters.label(text="Pipeline log", icon="TEXT")
        row = filters.row()
        row.prop(state, "level", expand=True)
        row.prop(state, "action", text="")
        row.prop(state, "user", text="")
        row.prop(state, "search", text="", icon="VIEWZOOM")
        layout.separator(factor=0.5)
        draw_pipeline_logs(state, context, layout)


class M_PIPELINE_PT_welcome(_MonitoringPanel, bpy.types.Panel):
    """The welcome window's content (the onboarding): no project needed."""

    bl_label = "Pipeline: Welcome"
    bl_idname = "M_PIPELINE_PT_welcome"
    kind = "welcome"

    def draw(self, context):
        # Read at a line's length whatever the window's width: a centred
        # column, the text wrapped to it.
        width = context.region.width
        side = (1 - 900 / width) / 2 if width > 900 else 0.0
        layout = self.layout
        if side:
            # margin | text | margin: each split's first item takes its factor.
            outer = layout.split(factor=side)
            outer.column()
            inner = outer.split(factor=(1 - 2 * side) / (1 - side))
            layout = inner.column()
            inner.column()
        layout.separator(factor=2)
        draw_onboarding(
            layout,
            context,
            max_width=min(120, region_char_budget(context, width_px=None)),
            level_hint=False,
        )
        layout.separator(factor=2)
        prefs = addon_pref(context)
        if prefs:
            # Two lines: the question, then the switch -- on one, the text
            # was cut.
            level = layout.column(align=True)
            level.label(text="Familiar with the add-on? Advanced hides the tips.", icon="HIDE_OFF")
            level.row(align=True).prop(prefs, "experience_level", expand=True)
            layout.separator(factor=1)
        # How to start, at hand: a project to make, or one to find.
        actions = layout.box().row()
        actions.scale_y = 1.2
        actions.operator("m_pipeline.create_project", text="New project", icon="FILE_NEW")
        actions.operator("m_pipeline.find_project", text="Find existing project", icon="ZOOM_ALL")
        actions.operator("wm.window_close", text="Close", icon="CHECKMARK")
        # A window's height of blank below, as the others: the Tool tab's
        # Options and Workspace out of sight.
        spacer = self.layout.column()
        spacer.scale_y = context.region.height / (20 * (context.preferences.system.ui_scale or 1.0))
        spacer.label(text="")


class M_PIPELINE_PT_project_settings(_MonitoringPanel, bpy.types.Panel):
    """Project settings' window: the fields of the project being edited
    (WindowManager.pipeline_project_settings), Save to write them."""

    bl_label = "Pipeline: Project settings"
    bl_idname = "M_PIPELINE_PT_project_settings"
    kind = "settings"

    def draw(self, context):
        settings = context.window_manager.pipeline_project_settings
        layout = self.layout
        if not settings.project_path_selected:
            layout.label(text="No project loaded: open Project settings again.", icon="ERROR")
        else:
            right = settings.draw_settings(layout)
            # The active project's upkeep: both act on it, not on another
            # project whose settings are open here.
            from pathlib import Path

            root = get_active_project_root()
            if root and Path(settings.project_path_selected) == Path(root):
                right.separator()
                box = right.box().column(align=False)
                split = box.split(factor=0.33, align=True)
                split.label(text="MAINTENANCE", icon="TOOL_SETTINGS")
                col = split.column(align=True)
                col.operator("m_pipeline.clean_renders", text="Clean old renders...", icon="RENDER_RESULT")
                col.operator("m_pipeline.delete_owner_pick", text="Delete a shot or an asset...", icon="TRASH")
            layout.separator(factor=2)
            actions = layout.box().row()
            actions.scale_y = 1.2
            actions.operator("m_pipeline.save_project_settings", text="Save", icon="FILE_TICK")
            actions.operator("wm.window_close", text="Close", icon="CHECKMARK")
        spacer = self.layout.column()
        spacer.scale_y = context.region.height / (20 * (context.preferences.system.ui_scale or 1.0))
        spacer.label(text="")
