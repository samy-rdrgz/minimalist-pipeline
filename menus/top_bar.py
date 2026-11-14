"""Top bar "Pipeline" menu, plus a prepended read-only indicator on the
same row -- see read_only_indicator() below."""

import bpy

from ..farm import get_monitor_cache, this_instance_is_worker
from ..lib.ui import draw_items
from ..lib import (
    RecentFilesCache,
    addon_pref,
    file_in_active_project,
    get_active_project_root,
    get_opened_as_read_only,
    get_read_only_reason,
    region_char_budget,
    text_to_lines,
    type_by_folder,
)
from ..lib.actions import (
    LOCKED_FILE_EXPLANATION,
    READ_ONLY_EXPLANATION,
    STABLE_FILE_EXPLANATION,
)

READ_ONLY_REASON_LABELS = {
    "stable": "Stable version",
    "profile": "Read-only profile enabled",
    "reopened": "Already opened read-only this session",
    "locked": "Locked by another user",
}
READ_ONLY_REASON_EXPLANATIONS = {
    "stable": STABLE_FILE_EXPLANATION,
    "profile": READ_ONLY_EXPLANATION,
    "reopened": READ_ONLY_EXPLANATION,
    "locked": LOCKED_FILE_EXPLANATION,
}
from ..operators import project_ops


class M_PIPELINE_MT_recent_files(bpy.types.Menu):
    """The Pipeline menu's recent files, most recent first."""

    bl_idname = "M_PIPELINE_MT_recent_files"
    bl_label = "Recent files"

    def draw(self, context):
        for name, filepath in RecentFilesCache.get(limit=5):
            self.layout.operator(
                "m_pipeline.open_file_version", text=name, icon="FILE_BLEND"
            ).filepath = filepath


class M_PIPELINE_MT_topbar_menu(bpy.types.Menu):
    """Pipeline actions, mirroring the sidebar panels."""

    bl_idname = "M_PIPELINE_MT_topbar_menu"
    bl_label = "Pipeline"

    def draw(self, context):
        layout = self.layout
        # Menu.draw() defaults to EXEC_DEFAULT, which skips invoke() entirely --
        # nearly every operator here opens a dialog from invoke(), so without
        # this every click would silently run with default property values.
        layout.operator_context = "INVOKE_DEFAULT"

        project_root = get_active_project_root()
        if not project_root:
            prefs = addon_pref(context)
            if not prefs:
                return
            projects = [item for item in prefs.opened_projects]
            if projects:
                for item in projects:
                    layout.operator(
                        project_ops.M_PIPELINE_OT_set_active_project.bl_idname,
                        text=item.name.upper(),
                        icon="DOT",
                    ).project_path_selected = item.path
                layout.separator()

            layout.operator(
                "m_pipeline.create_project", text="New project", icon="FILE_NEW"
            )
            layout.operator(
                "m_pipeline.find_project",
                text="Find existing project...",
                icon="ZOOM_ALL",
            )
            return

        filepath = bpy.data.filepath
        f_type = (
            type_by_folder(filepath, str(project_root))
            if filepath and file_in_active_project(filepath, str(project_root))
            else None
        )
        this_file = f_type in ("asset", "library", "shot")
        # Status cache, not monitor.lock.exists() -- see farm_panel.draw_header().
        status = get_monitor_cache().get("status")
        # Launch: not running, or a stale/dead/unread lock -- always safe to
        # offer, the operator re-checks live and confirms before taking over.
        launch = status != "running"
        stop = status in ("running", "stale")
        worker = this_instance_is_worker()
        # draw_items(): (operator, text, icon, its properties), None a separator.
        items = [
            ("m_pipeline.open_file", "Open file", "FILE_BLEND", {}),
            ("recent",),
            None,
            ("m_pipeline.create_asset", "New asset", "ADD", {}),
            ("m_pipeline.create_shot", "New shot", "BLANK1", {}),
            ("m_pipeline.batch_create", "Batch create from CSV", "BLANK1", {"greyed": True}),
            None,
            ("m_pipeline.tracking_monitor", "Tracking monitor", "WORKSPACE", {}),
            ("m_pipeline.export_snapshot", "Snapshot", "BLANK1", {}),
            ("m_pipeline.import_review", "Import review", "BLANK1", {}),
            *(
                [
                    None,
                    ("wm.safe_save", "Save", "FILE_TICK", {}),
                    ("m_pipeline.increment_version", "Increment", "DUPLICATE", {}),
                    ("m_pipeline.increment_version", "Mark as stable", "CHECKMARK", {"tag": "stable"}),
                    ("m_pipeline.farm_request_render", "Render this file", "RENDER_STILL", {"filepath": filepath}),
                ]
                if this_file
                else []
            ),
            *(
                [("m_pipeline.edit_block_structure", "Edit block structure", "BLANK1", {"greyed": True, "filepath": filepath})]
                if f_type == "shot"
                else []
            ),
            None,
            ("m_pipeline.edit_project", "Project settings", "OPTIONS", {"project_path_selected": str(project_root)}),
            ("wm.open_folder", "Open project folder", "BLANK1",
             {"filepath": str(project_root), "custom_tooltip": "Open the project's root folder"}),
            ("m_pipeline.pipeline_logs", "Pipeline log", "BLANK1", {"greyed": True}),
            None,
            ("m_pipeline.farm_request_render", "Render", "RENDER_RESULT", {}),
            ("m_pipeline.push_rushes", "Push rushes to editing", "BLANK1", {"greyed": True}),
            ("m_pipeline.farm_monitor", "Farm monitor", "WORKSPACE", {}),
            launch and ("m_pipeline.farm_launch_monitor", "Launch farm", "BLANK1", {}),
            stop and ("m_pipeline.farm_kill_monitor", "Stop farm", "BLANK1", {}),
            ("m_pipeline.farm_kill_self_worker", "Stop this worker", "BLANK1", {})
            if worker
            else ("m_pipeline.farm_add_self_worker", "Add this machine as worker", "BLANK1", {}),
            None,
            ("m_pipeline.unset_active_project", "Unset active project", "PANEL_CLOSE", {"greyed": True}),
        ]
        for item in items:
            if item == ("recent",):
                if RecentFilesCache.get():
                    layout.menu(M_PIPELINE_MT_recent_files.bl_idname, icon="RECOVER_LAST")
            else:
                draw_items(layout, [item], context)


def top_bar_menu(self, context):
    layout = self.layout
    layout.menu(M_PIPELINE_MT_topbar_menu.bl_idname)


class M_PIPELINE_MT_read_only_menu(bpy.types.Menu):
    """Why the current file opened read-only, plus a way out."""

    bl_idname = "M_PIPELINE_MT_read_only_menu"
    bl_label = "READ-ONLY"

    def draw(self, context):
        layout = self.layout
        reason = get_read_only_reason()

        layout.label(text=READ_ONLY_REASON_LABELS.get(reason, "Read-only"), icon="INFO")
        layout.separator()

        pref = addon_pref(context)
        if pref and getattr(pref, "experience_level", "BEGINNER") == "BEGINNER":
            text_to_lines(
                layout,
                READ_ONLY_REASON_EXPLANATIONS.get(reason, READ_ONLY_EXPLANATION),
                max_width=region_char_budget(context, width_px=200),
                max_lines=8,
                scale_y=0.8,
                icon="NONE",
            )
            layout.separator()

        if reason != "locked":
            layout.operator(
                "m_pipeline.increment_version",
                text="Increment",
                icon="DUPLICATE",
            )


def read_only_indicator(self, context):
    """Persistent "READ-ONLY" warning, prepended to TOPBAR_MT_editor_menus --
    lands before its native draw() entirely, so before the Blender icon too
    (no hook point exists between the icon and "File", both hardcoded in
    the same native draw() -- see NOTES.md). Reuses saving.py's own
    read-only flag; draws nothing when the file isn't read-only."""
    filepath = bpy.data.filepath
    if not filepath or get_opened_as_read_only() != filepath:
        return
    row = self.layout.row(align=True)
    row.alert = True
    row.label(text="READ-ONLY", icon="LOCKED")
    row.menu("M_PIPELINE_MT_read_only_menu", text="", icon="DOWNARROW_HLT")
    self.layout.separator()


def _purge_stale(name: str):
    """Remove every top bar draw callback named name, matched by __name__
    (see NOTES.md, "Small gotchas, out of the docstrings")."""
    menus = bpy.types.TOPBAR_MT_editor_menus._dyn_ui_initialize()
    for f in [f for f in menus if getattr(f, "__name__", None) == name]:
        menus.remove(f)


def register():
    _purge_stale("top_bar_menu")
    _purge_stale("read_only_indicator")
    bpy.types.TOPBAR_MT_editor_menus.append(top_bar_menu)
    bpy.types.TOPBAR_MT_editor_menus.prepend(read_only_indicator)


def unregister():
    _purge_stale("top_bar_menu")
    _purge_stale("read_only_indicator")
