"""Navigation inside the monitoring windows (lib/monitoring/windows.py) -- the
Pipeline log's: turning its list's page, reading it again; their buttons,
and the keys register_monitoring_keymap() binds. Project and Farm
monitoring are the live page's now (lib/monitoring/live.py)."""

import bpy

from ..lib import list_fits, monitoring_kind, redraw_monitoring, turn_page
from ..panels import load_pipeline_log

# Windows with no list to page through nor anything to read again.
_STILL = ("", "welcome", "settings")
# The wheel's events: pages on a list, the scroll everywhere else
# (M_PIPELINE_OT_monitoring_page.invoke()).
_WHEEL = ("WHEELUPMOUSE", "WHEELDOWNMOUSE")


class M_PIPELINE_OT_monitoring_page(bpy.types.Operator):
    """Previous / next page of a monitoring window's list."""

    bl_idname = "m_pipeline.monitoring_page"
    bl_label = "Change page"

    step: bpy.props.IntProperty(default=1, options={"SKIP_SAVE"})
    to_end: bpy.props.BoolProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        if properties.step < 0:
            return "Previous page.\nCtrl+click: the first"
        return "Next page.\nCtrl+click: the last"

    @classmethod
    def poll(cls, context):
        # Its window's list only: the arrow keys do nothing elsewhere.
        return monitoring_kind(context.screen) not in _STILL

    def invoke(self, context, event):
        # The wheel turns a list's pages, never a list taller than its window.
        if event.type in _WHEEL and not list_fits(monitoring_kind(context.screen)):
            return {"PASS_THROUGH"}
        self.to_end = self.to_end or event.ctrl
        return self.execute(context)

    def execute(self, context):
        turn_page(monitoring_kind(context.screen), self.step, self.to_end)
        return {"FINISHED"}


class M_PIPELINE_OT_monitoring_refresh(bpy.types.Operator):
    """Read a monitoring window's content again (F5): the log."""

    bl_idname = "m_pipeline.monitoring_refresh"
    bl_label = "Refresh"

    @classmethod
    def poll(cls, context):
        return monitoring_kind(context.screen) not in _STILL

    def execute(self, context):
        load_pipeline_log()
        redraw_monitoring(monitoring_kind(context.screen))
        return {"FINISHED"}
