"""Navigation inside the monitoring windows (lib/monitoring.py): turning a
list's page, switching its view, going back from a detail, refreshing --
their buttons, and the keys register_monitoring_keymap() binds."""

import bpy

from ..farm import load_job_details, request_monitor_refresh
from ..lib import (
    get_active_project_root,
    monitoring_detail,
    monitoring_kind,
    neighbour_in_list,
    redraw_monitoring,
    set_monitoring_detail,
    turn_page,
)
from ..panels import (
    load_file_renders,
    load_file_thumbnail,
    load_pipeline_log,
    monitor_matches,
)

# What each window's detail is kept under (see lib/core.py); the log has none.
_DETAILS = {
    "project": ("file", "missing_file"),
    "farm": ("job", "worker"),
    "log": (),
    "welcome": (),
    "settings": (),
}
# Windows with no list to page through nor anything to read again.
_STILL = ("", "welcome", "settings")


def _showing_detail(kind: str) -> bool:
    return any(monitoring_detail(key) for key in _DETAILS[kind])


def _in_file_detail(context) -> bool:
    """Project monitoring on a file's detail (not a file not found)."""
    return monitoring_kind(context.screen) == "project" and bool(
        monitoring_detail("file")
    )


def _step_file(context, step: int, to_end: bool) -> bool:
    """File details: the previous / next file of Project monitoring's list,
    with its filters and sort (Ctrl: the first / last). False when there's
    none (an end of the list, a file outside it)."""
    root = get_active_project_root()
    if not root:
        return False
    matches, _filters = monitor_matches(
        context.window_manager.pipeline_monitoring, context, root
    )
    current = monitoring_detail("file")
    found = neighbour_in_list(
        "project", current, [str(d) for d, _ in matches], step, to_end
    )
    if not found:
        return False
    set_monitoring_detail("file", found)
    load_file_thumbnail(found)
    load_file_renders(found)
    return True


class M_PIPELINE_OT_monitoring_page(bpy.types.Operator):
    """Previous / next page of a monitoring window's list -- in Project
    monitoring's file detail, the previous / next file of its list."""

    bl_idname = "m_pipeline.monitoring_page"
    bl_label = "Change page"

    step: bpy.props.IntProperty(default=1, options={"SKIP_SAVE"})
    to_end: bpy.props.BoolProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        what = "file" if context and _in_file_detail(context) else "page"
        if properties.step < 0:
            return f"Previous {what}.\nCtrl+click: the first"
        return f"Next {what}.\nCtrl+click: the last"

    @classmethod
    def poll(cls, context):
        # Its window's list only: the arrow keys do nothing elsewhere. A
        # file's detail: its list's files.
        if _in_file_detail(context):
            return True
        kind = monitoring_kind(context.screen)
        if kind in _STILL or _showing_detail(kind):
            return False
        return kind != "farm" or context.window_manager.pipeline_farm_monitoring.view == "jobs"

    def invoke(self, context, event):
        self.to_end = self.to_end or event.ctrl
        return self.execute(context)

    def execute(self, context):
        kind = monitoring_kind(context.screen)
        if _in_file_detail(context):
            if not _step_file(context, self.step, self.to_end):
                return {"CANCELLED"}
            redraw_monitoring(kind)
            return {"FINISHED"}
        turn_page(kind, self.step, self.to_end)
        return {"FINISHED"}


class M_PIPELINE_OT_monitoring_switch(bpy.types.Operator):
    """Project monitoring: assets <-> shots. Farm monitoring: jobs <-> workers (Tab)."""

    bl_idname = "m_pipeline.monitoring_switch"
    bl_label = "Switch view"

    @classmethod
    def poll(cls, context):
        kind = monitoring_kind(context.screen)  # the log has one view
        return kind in ("project", "farm") and not _showing_detail(kind)

    def execute(self, context):
        kind = monitoring_kind(context.screen)
        wm = context.window_manager
        if kind == "project":
            state = wm.pipeline_monitoring
            state.file_type = "asset" if state.file_type == "shot" else "shot"
        else:
            state = wm.pipeline_farm_monitoring
            state.view = "workers" if state.view == "jobs" else "jobs"
        redraw_monitoring(kind)
        return {"FINISHED"}


class M_PIPELINE_OT_monitoring_back(bpy.types.Operator):
    """Back from a monitoring window's detail to its list (Esc)."""

    bl_idname = "m_pipeline.monitoring_back"
    bl_label = "Back to the list"

    @classmethod
    def poll(cls, context):
        kind = monitoring_kind(context.screen)
        return bool(kind) and _showing_detail(kind)

    def execute(self, context):
        kind = monitoring_kind(context.screen)
        for key in _DETAILS[kind]:
            set_monitoring_detail(key, "")
        redraw_monitoring(kind)
        return {"FINISHED"}


class M_PIPELINE_OT_monitoring_refresh(bpy.types.Operator):
    """Read a monitoring window's content again (F5): the project scanned,
    the farm read, the job shown reloaded, the log read."""

    bl_idname = "m_pipeline.monitoring_refresh"
    bl_label = "Refresh"

    @classmethod
    def poll(cls, context):
        return monitoring_kind(context.screen) not in _STILL

    def execute(self, context):
        kind = monitoring_kind(context.screen)
        if kind == "project":
            return bpy.ops.m_pipeline.tracking_refresh()
        if kind == "farm":
            job_id = monitoring_detail("job")
            if job_id:
                load_job_details(job_id)
            request_monitor_refresh()
        else:
            load_pipeline_log()
        redraw_monitoring(kind)
        return {"FINISHED"}
