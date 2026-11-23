"""The monitoring windows' content (lib/monitoring/windows.py): the Pipeline log,
the welcome, Project settings."""

import bpy

from ..lib import (
    addon_pref,
    draw_onboarding,
    ensure_monitoring_tick,
    get_active_project_root,
    monitor_filters,
    end_filters,
    monitoring_kind,
    region_char_budget,
)
from ..operators.migration_ops import project_needs_migration
from .logs_panel import draw_pipeline_logs


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
            self.draw_content(context, layout, detail=True)
        # A window's height of blank below: the Tool tab's other panels
        # (Options, Workspace) out of sight, even scrolled.
        spacer = layout.column()
        spacer.scale_y = context.region.height / (
            20 * (context.preferences.system.ui_scale or 1.0)
        )
        spacer.label(text="")


class M_PIPELINE_PT_log_monitoring(_MonitoringPanel, bpy.types.Panel):
    """Pipeline log window's content."""

    bl_label = "Pipeline: Pipeline log"
    bl_idname = "M_PIPELINE_PT_log_monitoring"
    kind = "log"

    def draw_content(self, context, layout, detail=True):
        state = context.window_manager.pipeline_log_monitoring
        # the live page's filters, the same way (monitor_filters()).
        row, next_row = monitor_filters(context, layout)
        row.prop(state, "level", expand=True)
        row = next_row()
        row.prop(state, "action", text="")
        row.prop(state, "user", text="")
        row = next_row()
        row.prop(state, "search", text="", icon="VIEWZOOM")
        end_filters(row, layout)
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
            level = layout.box().column(align=True)
            level.label(
                text="Familiar with the add-on? Advanced hides the tips.",
                icon="HIDE_OFF",
            )
            level.row(align=True).prop(prefs, "experience_level", expand=True)
            layout.separator(factor=1)
        # A project to make or join: START, at the top.
        actions = layout.row()
        actions.scale_y = 1.2
        actions.operator("wm.window_close", text="Close", icon="CHECKMARK")
        # A window's height of blank below, as the others: the Tool tab's
        # Options and Workspace out of sight.
        spacer = self.layout.column()
        spacer.scale_y = context.region.height / (
            20 * (context.preferences.system.ui_scale or 1.0)
        )
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
            layout.label(
                text="No project loaded: open Project settings again.", icon="ERROR"
            )
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
                col.operator(
                    "m_pipeline.clean_renders",
                    text="Clean old renders...",
                    icon="RENDER_RESULT",
                )
                col.operator(
                    "m_pipeline.delete_owner_pick",
                    text="Delete a shot or an asset...",
                    icon="TRASH",
                )
                col.operator(
                    "m_pipeline.revert_review",
                    text="Revert a review...",
                    icon="LOOP_BACK",
                )
                migrate = col.row()
                migrate.alert = project_needs_migration()
                migrate.operator(
                    "m_pipeline.migrate_data",
                    text="Migrate old data...",
                    icon="FILE_REFRESH",
                )
            layout.separator(factor=2)
            actions = layout.box().row()
            actions.scale_y = 1.2
            actions.operator(
                "m_pipeline.save_project_settings", text="Save", icon="FILE_TICK"
            )
            actions.operator("wm.window_close", text="Close", icon="CHECKMARK")
        spacer = self.layout.column()
        spacer.scale_y = context.region.height / (
            20 * (context.preferences.system.ui_scale or 1.0)
        )
        spacer.label(text="")
