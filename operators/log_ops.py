"""Pipeline log window operators (lib/monitoring.py, kind "log")."""

import bpy

from ..lib import (
    bring_monitoring_to_front,
    get_active_project_root,
    memory_enum,
    memory_prop,
    monitoring_windows,
    open_monitoring_window,
    redraw_monitoring,
)
from ..panels import load_pipeline_log, log_read_at, log_values

# Enum items must outlive the callback (Blender keeps no reference), and
# are only rebuilt after a new read: the callback runs on every redraw.
_items_cache: dict[str, tuple] = {"action": (None, []), "user": (None, [])}


def _items(key: str):
    """An enum items callback for the Pipeline log's key filter ("action",
    "user"): "all", then every value in the log, cached per log read."""

    def callback(self, context):
        read_at, items = _items_cache[key]
        if read_at != log_read_at() or not items:
            items = [("all", f"All {key}s", "")] + [
                (v, v, "") for v in log_values(key)
            ]
            _items_cache[key] = (log_read_at(), items)
        return items

    return callback


# The Pipeline log's filters: in memory only, like the other monitoring
# windows' (see memory_prop()).
_log_filters: dict = {}


class PIPELINE_PG_log_monitoring(bpy.types.PropertyGroup):
    """Pipeline log window's filters (WindowManager.pipeline_log_monitoring)."""

    level: memory_enum(
        _log_filters,
        "level",
        [
            ("all", "All levels", "Every line"),
            ("warning", "Warnings", "Warnings and errors"),
            ("error", "Errors", "Errors only"),
        ],
    )
    action: memory_enum(_log_filters, "action", _items("action"))
    user: memory_enum(_log_filters, "user", _items("user"))
    search: memory_prop(
        _log_filters,
        "search",
        bpy.props.StringProperty,
        "",
        name="",
        description="Filter by message (a job id, a file name...)",
    )


class M_PIPELINE_OT_pipeline_logs(bpy.types.Operator):
    """Open the Pipeline log in its own window (panels/monitoring_panel.py)."""

    bl_idname = "m_pipeline.pipeline_logs"
    bl_label = "Pipeline log"
    bl_description = (
        "Open a window with the project's pipeline log, filterable by level, "
        "action and user. It stays open, resizable, while you work"
    )

    # Set by a job's or a worker's log button: the window opens filtered on it.
    search: bpy.props.StringProperty(options={"SKIP_SAVE", "HIDDEN"})

    def execute(self, context):
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        state = context.window_manager.pipeline_log_monitoring
        if self.search:
            state.search = self.search
        # Read after the window: a thread running through window_new()
        # crashed Blender (see lib/background.py).
        if monitoring_windows("log"):
            redraw_monitoring("log")
            if not bring_monitoring_to_front(context, "log"):
                self.report({"INFO"}, "The pipeline log is already open.")
            load_pipeline_log()
            return {"FINISHED"}
        if not open_monitoring_window(context, "log"):
            self.report({"ERROR"}, "Blender could not open a new window.")
            return {"CANCELLED"}
        load_pipeline_log()
        return {"FINISHED"}


class M_PIPELINE_OT_pipeline_logs_refresh(bpy.types.Operator):
    """Re-read the pipeline log."""

    bl_idname = "m_pipeline.pipeline_logs_refresh"
    bl_label = ""
    bl_description = "Read the pipeline log again (F5)."

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
