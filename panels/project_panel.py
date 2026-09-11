"""Project management panel in the 3D View sidebar."""

import bpy

from ..lib import addon_pref, draw_box_tip, get_active_project_root
from ..operators import (
    asset_ops,
    batch_ops,
    browser_ops,
    farm_ops,
    project_ops,
    shot_ops,
)


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
                    text=f"Project : {str(active_path.name).upper()}", icon="PINNED"
                )
                layout.operator(
                    project_ops.M_PIPELINE_OT_edit_project.bl_idname,
                    text="",
                    icon="OPTIONS",
                    emboss=False,
                ).project_path_selected = str(active_path)
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
            layout.operator(
                asset_ops.M_PIPELINE_OT_create_asset.bl_idname,
                text="New asset",
                icon="ADD",
            )
            layout.operator(
                shot_ops.M_PIPELINE_OT_create_shot.bl_idname,
                text="New shot",
                icon="BLANK1",
            )
            layout.operator(
                batch_ops.M_PIPELINE_OT_batch_create.bl_idname,
                text="Batch create from CSV",
                icon="IMPORT",
            )

            layout.separator()
            layout.operator(
                browser_ops.M_PIPELINE_OT_open_file.bl_idname,
                text="Open file",
                icon="FILE_BLEND",
            )
            op = layout.operator(
                "wm.open_folder", text="Open folder", icon="BLANK1"
            )
            op.filepath = str(active_path)
            op.custom_tooltip = "Open the project's root folder"

            layout.separator()
            layout.operator(
                farm_ops.M_PIPELINE_OT_farm_request_render.bl_idname,
                text="Render",
                icon="RENDER_RESULT",
            )

            layout.separator()
            layout.operator(
                "m_pipeline.tracking_monitor",
                icon="DESKTOP",
                text="Project monitoring",
            )
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
                    row.operator(
                        project_ops.M_PIPELINE_OT_set_active_project.bl_idname,
                        text=item.name.upper(),
                        icon="UNPINNED",
                        emboss=False,
                    ).project_path_selected = item.path
                    row.operator(
                        project_ops.M_PIPELINE_OT_edit_project.bl_idname,
                        text="",
                        icon="OPTIONS",
                        emboss=False,
                    ).project_path_selected = item.path
                    row.operator(
                        project_ops.M_PIPELINE_OT_remove_project.bl_idname,
                        text="",
                        icon="PANEL_CLOSE",
                        emboss=False,
                    ).project_path_selected = item.path

                layout.separator()

            layout.separator()
            draw_box_tip(
                layout,
                context,
                "A project is one shared folder your whole team works "
                "from. New project creates that folder and its "
                "structure. Find existing project points this machine "
                "at one that already exists (on a shared drive, or a "
                "teammate's).",
            )

            layout.operator(
                project_ops.M_PIPELINE_OT_create_project.bl_idname,
                text="New project",
                icon="FILE_NEW",
            )
            layout.operator(
                project_ops.M_PIPELINE_OT_find_project.bl_idname,
                text="Find existing project",
                icon="ZOOM_ALL",
            )
