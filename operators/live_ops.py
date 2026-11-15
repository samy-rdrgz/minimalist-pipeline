"""Open the live page: the project's snapshot page served by Blender,
kept up to date (lib/live.py, NOTES.md "Live page")."""

import webbrowser
from pathlib import Path
from urllib.parse import quote

import bpy

from ..lib import get_active_project_root, live


class M_PIPELINE_OT_open_live_page(bpy.types.Operator):
    """Open the project's page in the browser, served by Blender and kept up to date"""

    bl_idname = "m_pipeline.open_live_page"
    bl_label = "Open in browser"
    bl_description = (
        "The project's page in the browser, served by this Blender and kept "
        "up to date as the project changes -- on this machine only"
    )

    # Where it opens: a file's details (its .blend's path or name), or a tab
    # ("farm"). Empty: the list.
    file: bpy.props.StringProperty(options={"SKIP_SAVE", "HIDDEN"})
    tab: bpy.props.StringProperty(options={"SKIP_SAVE", "HIDDEN"})

    def execute(self, context):
        root = get_active_project_root()
        if not root:
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        try:
            url = live.start(root)
        except OSError as e:
            self.report({"ERROR"}, f"Live page not started: {e}")
            return {"CANCELLED"}
        anchor = Path(self.file).stem if self.file else self.tab
        webbrowser.open(f"{url}#{quote(anchor)}" if anchor else url)
        self.report({"INFO"}, f"Live page: {url}")
        return {"FINISHED"}


class M_PIPELINE_OT_stop_live_page(bpy.types.Operator):
    """Stop serving the live page"""

    bl_idname = "m_pipeline.stop_live_page"
    bl_label = "Stop the live page"
    bl_description = "Stop serving the project's page: an open one waits for Blender to serve it again"

    @classmethod
    def poll(cls, context):
        return live.running()

    def execute(self, context):
        live.stop()
        return {"FINISHED"}


classes = (M_PIPELINE_OT_open_live_page, M_PIPELINE_OT_stop_live_page)
