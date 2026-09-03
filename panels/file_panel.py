"""File management panel in the 3D View sidebar."""

from pathlib import Path

import bpy

from ..lib import (
    TrackingStatusCache,
    draw_box_tip,
    file_in_active_project,
    get_active_project_root,
    get_opened_as_read_only,
    get_read_only_reason,
    get_session_worked_departments,
    parse_filename,
    region_char_budget,
)
from .tracking_panel import ENTRIES_INDENT_FACTOR, draw_tracking_data


class PIPELINE_PT_file_panel(bpy.types.Panel):
    """File creation and versioning."""

    bl_label = ""
    bl_idname = "PIPELINE_PT_file_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pipeline"
    bl_options = {"HEADER_LAYOUT_EXPAND"}

    @classmethod
    def poll(cls, context):

        if not bpy.data.filepath:
            return False
        if not file_in_active_project(
            bpy.data.filepath, str(get_active_project_root())
        ):
            return False
        return True

    def draw_header(self, context):
        from .tracking_panel import TYPE_ICON

        filepath = bpy.data.filepath
        layout = self.layout.row(align=True)
        layout.separator(factor=0.4)
        layout.label(
            text=f"Actions on {Path(filepath).stem.rsplit('_', 1)[0].upper()}",
            icon=TYPE_ICON.get(Path(filepath).stem.split("_", 1)[0], "ASSET_MANAGER"),
        )

    def draw(self, context):

        filepath = bpy.data.filepath
        layout = self.layout.column(align=True)
        is_stable_ro = (
            get_opened_as_read_only() == filepath and get_read_only_reason() == "stable"
        )

        if not get_active_project_root():
            layout.label(text="No active project. Set one first.", icon="ERROR")
            return

        required = TrackingStatusCache.get(bpy.data.filepath).get(
            "departments_required", []
        )
        if required:
            layout.separator(factor=0.1)
            worked = get_session_worked_departments(Path(bpy.data.filepath))
            row = layout.row(align=True)
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
                layout,
                context,
                "Toggle the departments you worked on this session. This "
                "only feeds tracking and time stats. It changes nothing "
                "in your file.",
            )
            layout.separator()
            layout.separator(type="LINE")
            layout.separator()

        layout.operator(
            "pipeline.increment_version", text="Increment version", icon="DUPLICATE"
        )
        draw_box_tip(
            layout,
            context,
            "A version is a dated snapshot of your work. Incrementing "
            "makes a fresh working copy instead of overwriting. You "
            "never lose the previous state.",
        )
        if not is_stable_ro:
            # Already the stable version -- marking it stable again is a
            # no-op offer, and confusing next to the read-only indicator.
            layout.operator(
                "pipeline.increment_version", text="Mark as stable", icon="CHECKMARK"
            ).tag = "stable"
            draw_box_tip(
                layout,
                context,
                '"Stable" marks a validated version other files can link '
                "to. It opens read-only so nobody breaks it under you. "
                "Increment when you want to work again.",
            )

        layout.separator()
        layout.operator(
            "pipeline.farm_request_render",
            text="Render",
            icon="RENDER_RESULT",
        ).filepath = bpy.data.filepath

        layout.separator()
        row = layout.row(align=True)
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
            layout,
            context,
            "A preview compiles a disposable playback mp4 on the farm, "
            "not a final render. Block covers just this block's shots; "
            "sequence covers the whole sequence.",
        )

        parsed = parse_filename(Path(filepath).name)
        if parsed and parsed.get("shot"):
            layout.separator()
            layout.operator(
                "pipeline.branch_shot", text="Branch block", icon="UV_SYNC_SELECT"
            ).filepath = bpy.data.filepath

        layout.separator()
        layout.operator(
            "wm.open_folder", text="Open folder", icon="FOLDER_REDIRECT"
        ).filepath = str(Path(bpy.data.filepath).parent)

        layout.separator()
        width = int(region_char_budget(context) * ENTRIES_INDENT_FACTOR)
        draw_tracking_data(layout, filepath, required, width=width)
