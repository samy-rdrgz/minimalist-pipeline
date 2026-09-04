"""Top bar "Pipeline" menu, plus a prepended read-only indicator on the
same row -- see read_only_indicator() below."""

import bpy

from ..farm import get_monitor_cache
from ..lib import (
    ConfigCache,
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


class PIPELINE_MT_topbar_menu(bpy.types.Menu):
    """Pipeline actions, mirroring the sidebar panels."""

    bl_idname = "PIPELINE_MT_topbar_menu"
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
                        project_ops.PIPELINE_OT_set_active_project.bl_idname,
                        text=item.name.upper(),
                        icon="DOT",
                    ).project_path_selected = item.path
                layout.separator()

            layout.operator(
                "pipeline.create_project", text="New project", icon="FILE_NEW"
            )
            layout.operator(
                "pipeline.find_project",
                text="Find existing project...",
                icon="ZOOM_ALL",
            )
            return

        layout.operator("pipeline.open_file", text="Open file", icon="FILE_BLEND")
        recent = RecentFilesCache.get()
        if recent:
            col = layout.column()
            col.active = False
            col.label(text="Recent:")
            for name, recent_filepath in recent:
                layout.operator(
                    "pipeline.open_file_version", text=name, icon="FILE_BLEND"
                ).filepath = recent_filepath
        layout.separator()
        layout.operator("pipeline.create_asset", text="New asset", icon="ADD")
        layout.operator("pipeline.create_shot", text="New shot", icon="BLANK1")
        layout.operator(
            "pipeline.batch_create", text="Batch create from CSV", icon="BLANK1"
        )
        layout.separator()

        layout.operator(
            "pipeline.tracking_monitor", text="Tracking monitor", icon="BLANK1"
        )

        filepath = bpy.data.filepath
        if filepath and file_in_active_project(filepath, str(project_root)):
            f_type = type_by_folder(filepath, str(project_root))
            if f_type in ("asset", "library", "shot"):
                layout.separator()
                layout.operator("wm.safe_save", text="Save", icon="FILE_TICK")
                layout.operator(
                    "pipeline.increment_version",
                    text="Increment version",
                    icon="DUPLICATE",
                )
                layout.operator(
                    "pipeline.increment_version",
                    text="Mark as stable",
                    icon="CHECKMARK",
                ).tag = "stable"
                layout.operator(
                    "pipeline.farm_request_render",
                    text="Render this file",
                    icon="RENDER_STILL",
                ).filepath = filepath

        layout.separator()
        layout.operator(
            "pipeline.edit_project", text="Project settings", icon="OPTIONS"
        ).project_path_selected = str(project_root)
        layout.operator(
            "wm.open_folder", text="Open project folder", icon="BLANK1"
        ).filepath = str(project_root)

        layout.separator()
        layout.operator(
            "pipeline.farm_request_render", text="Render", icon="RENDER_RESULT"
        )
        layout.operator("pipeline.farm_monitor", text="Farm monitor", icon="BLANK1")
        monitor_lock = ConfigCache.get_path("monitor_file")
        if not monitor_lock.exists():
            layout.operator(
                "pipeline.farm_launch_monitor",
                text="Launch farm",
                icon="BLANK1",
            )
        else:
            status = get_monitor_cache().get("status")
            if status == "running":
                layout.operator(
                    "pipeline.farm_kill_monitor",
                    text="Stop farm",
                    icon="BLANK1",
                )
            else:
                # stale/dead/unread lock -- always safe to offer: the
                # operator re-checks live and confirms before taking over.
                layout.operator(
                    "pipeline.farm_launch_monitor",
                    text="Launch farm",
                    icon="BLANK1",
                )
                if status == "stale":
                    layout.operator(
                        "pipeline.farm_kill_monitor",
                        text="Stop farm",
                        icon="BLANK1",
                    )

        if context.scene.is_worker:
            layout.operator(
                "pipeline.farm_kill_self_worker",
                text="Stop this worker",
                icon="BLANK1",
            )
        else:
            layout.operator(
                "pipeline.farm_add_self_worker",
                text="Add this machine as worker",
                icon="BLANK1",
            )

        layout.separator()
        layout.operator(
            "pipeline.unset_active_project",
            text="Unset active project",
            icon="PANEL_CLOSE",
        )


def top_bar_menu(self, context):
    layout = self.layout
    layout.menu(PIPELINE_MT_topbar_menu.bl_idname)


class PIPELINE_MT_read_only_menu(bpy.types.Menu):
    """Why the current file opened read-only, plus a way out."""

    bl_idname = "PIPELINE_MT_read_only_menu"
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
                "pipeline.increment_version",
                text="Increment version",
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
    row.menu("PIPELINE_MT_read_only_menu", text="", icon="DOWNARROW_HLT")
    self.layout.separator()


def _purge_stale(name: str):
    """Remove every draw callback named `name`, not just one identity match.
    A dev-reload (VS Code extension, "Reload Scripts") replaces top_bar_menu/
    read_only_indicator with fresh function objects, so an `in`/`remove`
    identity check misses leftovers from a previous register() that
    registered fine but then crashed before its own unregister() ever ran
    (e.g. the register()-time _RestrictData issue) -- those orphans stack up
    as visible duplicate menus across reloads. Matching by __name__ instead
    self-heals on the next register(), no Blender restart needed."""
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
