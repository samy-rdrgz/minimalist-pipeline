"""File management panel in the 3D View sidebar."""

from pathlib import Path

import bpy

from ..lib import (
    TrackingStatusCache,
    draw_box_tip,
    file_in_active_project,
    get_active_project_root,
    get_session_worked_departments,
    parse_filename,
    region_char_budget,
)
from .tracking_panel import ENTRIES_INDENT_FACTOR, draw_tracking_data


class PIPELINE_PT_file_panel(bpy.types.Panel):
    """File creation and versioning."""

    bl_label = "Shot"
    bl_idname = "PIPELINE_PT_file_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pipeline"
    bl_parent_id = "PIPELINE_PT_main"
    bl_options = {"HIDE_HEADER", "HEADER_LAYOUT_EXPAND"}

    @classmethod
    def poll(cls, context):

        if not bpy.data.filepath:
            return False
        if not file_in_active_project(
            bpy.data.filepath, str(get_active_project_root())
        ):
            return False
        return True

    def draw(self, context):

        filepath = bpy.data.filepath

        layout = self.layout

        if not get_active_project_root():
            layout.label(text="No active project. Set one first.", icon="ERROR")
            return

        box = layout.box().column(align=True)
        box.label(
            text=f"Actions on {Path(filepath).stem.rsplit('_', 1)[0]}",
            icon="OUTLINER_OB_CAMERA",
        )

        required = TrackingStatusCache.get(bpy.data.filepath).get(
            "departments_required", []
        )
        if required:
            box.separator(factor=0.1)
            worked = get_session_worked_departments(Path(bpy.data.filepath))
            row = box.row(align=True)
            txt = row.row(align=True)
            txt.enabled = False
            txt.label(text="Worked this session:", icon="BLANK1")

            row.label(icon="BLANK1")
            for d in required:
                op = row.operator(
                    "pipeline.toggle_worked_department",
                    text=d,
                    depress=d in worked,
                )
                op.department = d
            draw_box_tip(
                box,
                context,
                "Toggle the departments you worked on this session. This "
                "only feeds tracking and time stats. It changes nothing "
                "in your file.",
            )
            box.separator()
            box.separator(type="LINE")
            box.separator()
        else:
            box.separator()

        box.operator(
            "pipeline.increment_version", text="Increment version", icon="DUPLICATE"
        )
        draw_box_tip(
            box,
            context,
            "A version is a dated snapshot of your work. Incrementing "
            "makes a fresh working copy instead of overwriting. You "
            "never lose the previous state.",
        )
        box.operator(
            "pipeline.increment_version", text="Mark as stable", icon="CHECKMARK"
        ).tag = "stable"
        draw_box_tip(
            box,
            context,
            '"Stable" marks a validated version other files can link '
            "to. It opens read-only so nobody breaks it under you. "
            "Increment when you want to work again.",
        )

        box.separator()
        box.operator(
            "pipeline.farm_request_render",
            text="Render",
            icon="RENDER_RESULT",
        ).filepath = bpy.data.filepath

        box.separator()
        row = box.row(align=True)
        op = row.operator(
            "pipeline.compile_preview", text="Preview block", icon="SEQUENCE"
        )
        op.scope = "block"
        op.filepath = bpy.data.filepath
        op = row.operator(
            "pipeline.compile_preview", text="Preview sequence", icon="SEQUENCE"
        )
        op.scope = "sequence"
        op.filepath = bpy.data.filepath
        draw_box_tip(
            box,
            context,
            "A preview compiles a disposable playback mp4 on the farm, "
            "not a final render. Block covers just this block's shots; "
            "sequence covers the whole sequence.",
        )

        parsed = parse_filename(Path(filepath).name)
        if parsed and parsed.get("shot"):
            box.separator()
            box.operator(
                "pipeline.branch_shot", text="Branch block", icon="UV_SYNC_SELECT"
            ).filepath = bpy.data.filepath

        box.separator()
        box.operator(
            "wm.open_folder", text="Open folder", icon="FOLDER_REDIRECT"
        ).filepath = str(Path(bpy.data.filepath).parent)

        box.separator()
        width = int(region_char_budget(context) * ENTRIES_INDENT_FACTOR)
        draw_tracking_data(box, filepath, required, width=width)
