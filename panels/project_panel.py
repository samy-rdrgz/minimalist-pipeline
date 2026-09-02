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


class PIPELINE_PT_project_panel(bpy.types.Panel):
    """Project list and management."""

    bl_label = "Project"
    bl_idname = "PIPELINE_PT_project_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pipeline"
    bl_parent_id = "PIPELINE_PT_main"
    bl_options = {"HIDE_HEADER", "HEADER_LAYOUT_EXPAND"}

    def draw(self, context):
        layout = self.layout
        prefs = addon_pref(context)

        if not prefs:
            return
        active_path = get_active_project_root()

        if active_path:
            box = layout.box().column(align=True)

            row = box.row()
            row.scale_x = 0.8
            row.label(text=f"Project : {str(active_path.name).upper()}", icon="PINNED")
            row.operator(
                project_ops.PIPELINE_OT_edit_project.bl_idname,
                text="",
                icon="OPTIONS",
                emboss=False,
            ).project_path_selected = str(active_path)
            row.operator(
                project_ops.PIPELINE_OT_unset_active_project.bl_idname,
                text="",
                icon="PANEL_CLOSE",
                emboss=False,
            )

            box.separator()
            box.operator(
                asset_ops.PIPELINE_OT_create_asset.bl_idname,
                text="New asset",
                icon="ADD",
            )
            box.operator(
                shot_ops.PIPELINE_OT_create_shot.bl_idname,
                text="New shot",
                icon="BLANK1",
            )
            box.operator(
                batch_ops.PIPELINE_OT_batch_create.bl_idname,
                text="Batch create from CSV",
                icon="IMPORT",
            )

            box.separator()
            box.operator(
                browser_ops.PIPELINE_OT_open_file.bl_idname,
                text="Open file",
                icon="FILE_BLEND",
            )
            box.operator(
                "wm.open_folder", text="Open folder", icon="BLANK1"
            ).filepath = str(active_path)

            box.separator()
            box.operator(
                farm_ops.PIPELINE_OT_farm_request_render.bl_idname,
                text="Render",
                icon="RENDER_RESULT",
            )

            box.separator()
            box.operator(
                "pipeline.tracking_monitor",
                icon="DESKTOP",
                text="Project monitoring",
            )
        else:
            others = [
                item for item in prefs.opened_projects if item.path != str(active_path)
            ]

            # True first-run state (nothing active, nothing known yet): the
            # (?) in the main panel header is too easy to miss here, so put
            # an unmissable, un-gated entry point to the same popup right
            # where the user's first click is about to happen.
            if not others:
                welcome = layout.box().column(align=True)
                welcome.label(text="   First time here?")
                welcome.operator(
                    "pipeline.onboarding_popup",
                    text="What this addon does",
                    icon="QUESTION",
                )
            box = layout.box().column(align=True)

            col = box.column(align=True)
            header = col.column()
            header.scale_y = 0.8
            txt_header = header.row()
            txt_header.alignment = "LEFT"

            txt_header.prop(
                context.window_manager,
                "projects_collapse",
                icon="DOWNARROW_HLT"
                if context.window_manager.projects_collapse
                else "RIGHTARROW",
                text="No active project",
                emboss=False,
            )

            if context.window_manager.projects_collapse:
                if not others:
                    row = box.row()
                    row.separator(factor=2.5)
                    row.label(text="No other projects", icon="INFO")
                else:
                    header.separator(factor=0.5)

                    for item in others:
                        row = col.box().row()
                        row.scale_y = 0.6
                        row.scale_x = 0.8
                        row.operator(
                            project_ops.PIPELINE_OT_set_active_project.bl_idname,
                            text="",
                            icon="UNPINNED",
                            emboss=False,
                        ).project_path_selected = item.path
                        row.label(text=item.name.upper())
                        row.operator(
                            project_ops.PIPELINE_OT_edit_project.bl_idname,
                            text="",
                            icon="OPTIONS",
                            emboss=False,
                        ).project_path_selected = item.path
                        row.operator(
                            project_ops.PIPELINE_OT_remove_project.bl_idname,
                            text="",
                            icon="PANEL_CLOSE",
                            emboss=False,
                        ).project_path_selected = item.path

                    box.separator()

                box.separator()
                draw_box_tip(
                    box,
                    context,
                    "A project is one shared folder your whole team works "
                    "from. New project creates that folder and its "
                    "structure. Find existing project points this machine "
                    "at one that already exists (on a shared drive, or a "
                    "teammate's).",
                )

                box.operator(
                    project_ops.PIPELINE_OT_create_project.bl_idname,
                    text="New project",
                    icon="FILE_NEW",
                )
                box.operator(
                    project_ops.PIPELINE_OT_find_project.bl_idname,
                    text="Find existing project",
                    icon="ZOOM_ALL",
                )
