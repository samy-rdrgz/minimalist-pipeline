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
    responsive_layout,
    shots_in_segment,
)
from ..lib.icons import icon_kw
from ..lib.ui import draw_items
from .tracking_panel import ENTRIES_INDENT_FACTOR, draw_tracking_data


class M_PIPELINE_PT_file_panel(bpy.types.Panel):
    """File creation and versioning."""

    bl_label = ""
    bl_idname = "M_PIPELINE_PT_file_panel"
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
        parsed = parse_filename(Path(filepath).name) if filepath else None
        is_stable_file = bool(parsed and parsed.get("tag") == "stable")
        is_stable_ro = is_stable_file or (
            get_opened_as_read_only() == filepath and get_read_only_reason() == "stable"
        )

        if not get_active_project_root():
            layout.label(text="No active project. Set one first.", icon="ERROR")
            return

        required = TrackingStatusCache.get(bpy.data.filepath).get(
            "departments_required", []
        )
        if get_opened_as_read_only() != filepath and not is_stable_file and required:
            layout.separator(factor=0.1)
            worked = get_session_worked_departments(Path(bpy.data.filepath))
            work = responsive_layout(context, layout.box(), 200)
            work.label(text="Working on:", icon="MOD_DYNAMICPAINT")
            col = work.column(align=True)
            col.scale_y = 0.7

            # Waiting / To redo (lib/status.py stage_flags()): said on the
            # toggle; a department to redo has its Still done beside it.
            flags = TrackingStatusCache.get(bpy.data.filepath).get("flags") or {}
            for d in required:
                flag = flags.get(d) or {}
                row = col.row(align=True)
                op = row.operator(
                    "m_pipeline.toggle_worked_department",
                    text=d + (f" · waiting: {flag['waiting']}" if flag.get("waiting")
                              else f" · to redo: {flag['to_redo']}" if flag.get("to_redo") else ""),
                    **icon_kw("mark:waiting" if flag.get("waiting") else "mark:to_redo" if flag.get("to_redo") else "NONE"),
                    depress=d in worked,
                )
                op.department = d
                if flag.get("to_redo"):
                    still = row.operator("m_pipeline.department_still_done", text="", icon="CHECKMARK")
                    still.filepath = str(Path(bpy.data.filepath).parent)
                    still.department = d
                    still.custom_tooltip = (f"To redo: {flag['to_redo']}.\nStill done: the work "
                                            "done holds -- not a validation")
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

        # Preview compile only makes sense for shots -- an asset file's parsed
        # dict simply won't have a "shot" key here. "Preview block" only
        # means something for an actual block (2+ shots): on a mono-shot it
        # would just re-encode that one shot's own latest render. Edit block
        # structure: the top bar menu.
        shot = bool(parsed and parsed.get("shot"))
        block = shot and len(shots_in_segment(parsed["shot"])) > 1
        here = bpy.data.filepath
        # Side by side when the sidebar is wide enough, tips under the row.
        draw_items(layout, [
            [
                ("m_pipeline.increment_version", "Increment", "DUPLICATE"),
                # Already the stable version: marking it stable again is a
                # no-op offer, confusing next to the read-only indicator.
                not is_stable_ro and ("m_pipeline.increment_version", "Mark as stable", "CHECKMARK", {"tag": "stable"}),
            ],
            ("tip", "A version is a dated snapshot of your work. Incrementing "
             "makes a fresh working copy instead of overwriting. You "
             "never lose the previous state."),
            not is_stable_ro and ("tip", '"Stable" marks a validated version other files can link '
                                  "to. It opens read-only so nobody breaks it under you. "
                                  "Increment when you want to work again."),
            None,
            [
                ("m_pipeline.farm_request_render", "Render", "RENDER_RESULT", {"filepath": here}),
                block and ("m_pipeline.compile_preview", "Preview block", "SEQUENCE", {
                    "scope": "block", "filepath": here,
                    "custom_tooltip": "Compile a disposable preview from just this block's own shots.",
                }),
                shot and ("m_pipeline.compile_preview", "Preview sequence", "SEQUENCE", {
                    "scope": "sequence", "filepath": here,
                    "custom_tooltip": "Compile a disposable preview from every rendered shot in this sequence.",
                }),
            ],
            shot and ("tip", "A preview compiles a disposable playback mp4 on the farm, "
                      "not a final render. Block covers just this block's shots; "
                      "sequence covers the whole sequence."),
            None,
            # Its departments, renders, links: Project monitoring's file detail.
            ("m_pipeline.tracking_monitor", "Details", "INFO", {"open_file": True}),
            ("wm.open_folder", "Open folder", "FOLDER_REDIRECT", {
                "filepath": str(Path(here).parent), "custom_tooltip": "Open this file's folder",
            }),
        ], context)

        layout.separator()
        width = int(region_char_budget(context) * ENTRIES_INDENT_FACTOR)
        draw_tracking_data(context, layout, filepath, required, width=width)
