"""Pipeline log popup operators."""

import bpy

from ..farm import clear_popup_regions, register_popup_region
from ..lib import get_active_project_root
from ..panels import (
    MONITOR_POPUP_WIDTH,
    draw_pipeline_logs,
    load_pipeline_log,
    log_read_at,
    log_values,
)

# Enum items must outlive the callback (Blender keeps no reference), and
# are only rebuilt after a new read: the callback runs on every redraw.
_items_cache: dict[str, tuple] = {"action": (None, []), "user": (None, [])}


def _items(key: str):
    def callback(self, context):
        read_at, items = _items_cache[key]
        if read_at != log_read_at() or not items:
            items = [("all", f"All {key}s", "")] + [
                (v, v, "") for v in log_values(key)
            ]
            _items_cache[key] = (log_read_at(), items)
        return items

    return callback


def _back_to_first_page(self, context):
    self.page = 1


class M_PIPELINE_OT_pipeline_logs(bpy.types.Operator):
    """Popup: the project's pipeline log, newest first, filterable."""

    bl_idname = "m_pipeline.pipeline_logs"
    bl_label = ""
    bl_description = (
        "Show the project's pipeline log, filterable by level, action and user."
    )

    level: bpy.props.EnumProperty(
        items=[
            ("all", "All", "Every line"),
            ("warning", "Warnings", "Warnings and errors"),
            ("error", "Errors", "Errors only"),
        ],
        default="all",
        update=_back_to_first_page,
    )
    action: bpy.props.EnumProperty(items=_items("action"), update=_back_to_first_page)
    user: bpy.props.EnumProperty(items=_items("user"), update=_back_to_first_page)
    search: bpy.props.StringProperty(
        name="",
        description="Filter by message (a job id, a file name...)",
        options={"SKIP_SAVE"},
        update=_back_to_first_page,
    )
    page: bpy.props.IntProperty(default=1, min=1, options={"SKIP_SAVE"})
    PAGE_SIZE = 20

    def invoke(self, context, event):
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        # A region left by an earlier popup, closed since, must never be
        # redrawn by load_pipeline_log()'s timer.
        clear_popup_regions()
        load_pipeline_log()
        return context.window_manager.invoke_props_dialog(
            self, width=MONITOR_POPUP_WIDTH
        )

    def draw(self, context):
        # Redrawn by load_pipeline_log()'s timer once the read is done.
        register_popup_region(getattr(context, "region_popup", None))
        filters = self.layout.box().split(factor=0.3)
        filters.label(text="Pipeline log", icon="TEXT")
        row = filters.row()
        row.prop(self, "level", expand=True)
        row.prop(self, "action", text="")
        row.prop(self, "user", text="")
        row.prop(self, "search", text="", icon="VIEWZOOM")
        draw_pipeline_logs(self, self.layout)

    def execute(self, context):
        return {"FINISHED"}


class M_PIPELINE_OT_pipeline_logs_refresh(bpy.types.Operator):
    """Re-read the pipeline log."""

    bl_idname = "m_pipeline.pipeline_logs_refresh"
    bl_label = ""
    bl_description = "Re-read the pipeline log (read once when the popup opens)."

    def execute(self, context):
        load_pipeline_log()
        return {"FINISHED"}


class M_PIPELINE_OT_copy_log_line(bpy.types.Operator):
    """Copy a whole log line to the clipboard."""

    bl_idname = "m_pipeline.copy_log_line"
    bl_label = ""

    text: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        return f"{properties.text}\n\nClick to copy."

    def execute(self, context):
        context.window_manager.clipboard = self.text
        self.report({"INFO"}, "Copied.")
        return {"FINISHED"}
