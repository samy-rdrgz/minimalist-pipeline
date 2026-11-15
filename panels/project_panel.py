"""Project management panel in the 3D View sidebar."""

import bpy

from ..lib import (
    addon_pref,
    blender_version_mismatch,
    get_active_project_root,
)
from ..lib.ui import draw_items, icon_button
from ..operators import (
    asset_ops,
    browser_ops,
    farm_ops,
    project_ops,
    shot_ops,
)
from ..operators.migration_ops import project_needs_migration


class M_PIPELINE_PT_project_panel(bpy.types.Panel):
    """Project list and management."""

    bl_label = ""
    bl_idname = "M_PIPELINE_PT_project_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pipeline"

    bl_options = {"HEADER_LAYOUT_EXPAND"}

    def draw_header(self, context):
        prefs = addon_pref(context)
        layout = self.layout.row(align=True)
        layout.separator(factor=0.4)

        if not prefs:
            layout.label(text="Project")
        else:
            active_path = get_active_project_root()
            if active_path:
                layout.label(
                    text=f"Project: {str(active_path.name).upper()}", icon="PINNED"
                )
                layout.operator(
                    project_ops.M_PIPELINE_OT_edit_project.bl_idname,
                    text="",
                    icon="OPTIONS",
                    emboss=False,
                ).project_path_selected = str(active_path)
                layout.operator(
                    "m_pipeline.pipeline_logs", text="", icon="TEXT", emboss=False
                )
                layout.operator(
                    project_ops.M_PIPELINE_OT_unset_active_project.bl_idname,
                    text="",
                    icon="PANEL_CLOSE",
                    emboss=False,
                )
                layout.separator(factor=1.5)
            else:
                layout.label(text="No active project")

    def draw(self, context):
        layout = self.layout.column(align=True)
        prefs = addon_pref(context)

        if not prefs:
            return
        active_path = get_active_project_root()

        if active_path:
            try:
                mismatch = blender_version_mismatch()
            except Exception:
                mismatch = None  # config unreadable this redraw: no warning
            if mismatch:
                warn = layout.row()
                warn.alert = True
                warn.label(
                    text=f"Blender {mismatch[1]} -- project is {mismatch[0]}",
                    icon="ERROR",
                )
                layout.separator()
            if project_needs_migration():
                warn = layout.row()
                warn.alert = True
                warn.label(text="Data from an older version: migrate it", icon="ERROR")
                layout.operator(
                    "m_pipeline.migrate_data", text="Migrate old data...", icon="FILE_REFRESH"
                )
                layout.separator()
            # A list: side by side when the sidebar is wide enough.
            draw_items(layout, [
                [
                    (asset_ops.M_PIPELINE_OT_create_asset.bl_idname, "New asset", "ADD"),
                    (shot_ops.M_PIPELINE_OT_create_shot.bl_idname, "New shot", "ADD"),
                ],
                None,
                (browser_ops.M_PIPELINE_OT_open_file.bl_idname, "Open file", "FILE_BLEND"),
                ("wm.open_folder", "Open folder", "BLANK1",
                 {"filepath": str(active_path), "custom_tooltip": "Open the project's root folder"}),
                None,
                (farm_ops.M_PIPELINE_OT_farm_request_render.bl_idname, "Render", "RENDER_RESULT"),
                ("m_pipeline.push_rushes", "Push rushes to editing", "SEQUENCE"),
                None,
                ("m_pipeline.tracking_monitor", "Project monitoring", "WORKSPACE"),
                ("tip", "Snapshot: an HTML progress page for production, to review "
                 "on. Import review reads the review it downloads: its notes "
                 "land on the files."),
                ("m_pipeline.open_live_page", "Open in browser", "URL"),
                [
                    ("m_pipeline.export_snapshot", "Snapshot", "EXPORT"),
                    ("m_pipeline.import_review", "Import review", "IMPORT"),
                ],
            ], context)
        else:
            others = [
                item for item in prefs.opened_projects if item.path != str(active_path)
            ]

            if not others:
                welcome = layout.column(align=True)
                welcome.label(text="   First time here?")
                welcome.operator(
                    "m_pipeline.onboarding_popup",
                    text="What this addon does",
                    icon="QUESTION",
                )

                row = layout.row()
                row.separator(factor=2.5)
                row.label(text="No other projects", icon="INFO")

            else:
                for item in others:
                    row = layout.box().row()
                    row.scale_y = 0.6
                    row.scale_x = 0.8
                    for op_name, text, icon in (
                        (project_ops.M_PIPELINE_OT_set_active_project.bl_idname, item.name.upper(), "UNPINNED"),
                        (project_ops.M_PIPELINE_OT_edit_project.bl_idname, "", "OPTIONS"),
                        (project_ops.M_PIPELINE_OT_remove_project.bl_idname, "", "PANEL_CLOSE"),
                    ):
                        icon_button(row, op_name, icon, text=text, project_path_selected=item.path)

                layout.separator()

            draw_items(layout, [
                None,
                ("tip", "A project is one shared folder your whole team works "
                 "from. New project creates that folder and its "
                 "structure. Find existing project points this machine "
                 "at one that already exists (on a shared drive, or a "
                 "teammate's)."),
                (project_ops.M_PIPELINE_OT_create_project.bl_idname, "New project", "FILE_NEW"),
                (project_ops.M_PIPELINE_OT_find_project.bl_idname, "Find existing project", "ZOOM_ALL"),
            ], context)
