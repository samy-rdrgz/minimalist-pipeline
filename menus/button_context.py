"""Right-click menus on the addon's own buttons -- Blender's button context
menu: a file of Project monitoring's list, a note or task, a farm job.
A button offers one by its operator's hidden "rmb" property ("file",
"entry", "job", "pending:<job id>")."""

from pathlib import Path

import bpy

from ..farm import REMOVABLE_STAGES, RETRYABLE_STAGES, get_monitor_cache
from ..lib import (
    ConfigCache,
    TrackingStatusCache,
    get_active_project_root,
    render_root,
    resolve_version_file,
)


class WM_MT_button_context(bpy.types.Menu):
    """Blender's hook into every button's right-click menu: defined by the
    first addon that needs it, then appended to."""

    bl_label = ""

    def draw(self, context):
        pass


def _file_menu(layout, folder: str) -> None:
    """A file of Project monitoring's list: its folders, a render."""
    folder = Path(folder)
    root = get_active_project_root()
    if root:
        try:
            renders = render_root(root, folder)
        except ValueError:
            renders = None
        # Never rendered yet: its sequence's (or prefix's) render folder.
        shown = renders if renders is None or renders.is_dir() else renders.parent
        if shown is not None and shown.is_dir():
            op = layout.operator("wm.open_folder", text="Open render folder", icon="RENDER_RESULT")
            op.filepath = str(shown)
    layout.operator("wm.open_folder", text="Open file folder", icon="FILE_FOLDER").filepath = str(folder)
    latest = resolve_version_file(folder, "last")
    if latest:
        op = layout.operator(
            "m_pipeline.farm_request_render", text=f"Render {latest.stem}", icon="RENDER_ANIMATION"
        )
        op.filepath = str(latest)


def _entry_menu(layout, entry_id: str, filepath: str) -> None:
    """A note or task: reply, edit, tick, delete."""
    entries = TrackingStatusCache.get(filepath).get("entries") or []
    entry = next((e for e in entries if e.get("id") == entry_id), {})
    op = layout.operator("m_pipeline.create_entry", text="Reply", icon="FORWARD")
    op.response, op.filepath = entry_id, filepath
    op = layout.operator("m_pipeline.edit_entry", text="Edit", icon="GREASEPENCIL")
    op.id, op.filepath = entry_id, filepath
    if entry.get("done") is not None:
        op = layout.operator(
            "m_pipeline.toggle_entry_task",
            text="Reopen" if entry["done"] else "Mark done",
            icon="CHECKBOX_DEHLT" if entry["done"] else "CHECKMARK",
        )
        op.id, op.filepath = entry_id, filepath
    layout.separator()
    op = layout.operator("m_pipeline.delete_entry", text="Delete", icon="TRASH")
    op.id, op.filepath = entry_id, filepath


def _job_menu(layout, job_id: str, pending: bool) -> None:
    """A farm job: what its stage allows, its folder, its file."""
    job = next(
        (
            j
            for j in get_monitor_cache().get("jobs") or []
            if j.get("job_id") == job_id and (j.get("stage") == "pending") == pending
        ),
        None,
    )
    if job is None:
        layout.label(text="Gone from the queue meanwhile", icon="INFO")
        return
    stage = job.get("stage", "")
    if pending or stage in REMOVABLE_STAGES:
        op = layout.operator("m_pipeline.farm_remove_job", text="Remove from queue", icon="X")
        op.job_id, op.pending = job_id, pending
    if stage == "render_start":
        layout.operator("m_pipeline.farm_cancel_job", text="Cancel", icon="X").job_id = job_id
    if stage in RETRYABLE_STAGES:
        layout.operator("m_pipeline.farm_retry_job", text="Retry", icon="LOOP_BACK").job_id = job_id
    if job.get("output_dir"):
        op = layout.operator("wm.open_folder", text="Open render folder", icon="FILE_FOLDER")
        op.filepath = job["output_dir"]
    if not pending:
        for kind in ("farm_actives", "farm_archives"):
            path = ConfigCache.get_path(kind) / f"{job_id}.json"
            if path.is_file():
                layout.operator("wm.open_folder", text="Open job file", icon="FILE_TEXT").filepath = str(path)
                break


def draw_button_menu(self, context):
    """Appended to WM_MT_button_context: the menu of the clicked button's
    operator, if it offers one ("rmb")."""
    op = getattr(context, "button_operator", None)
    kind = getattr(op, "rmb", "") if op is not None else ""
    if not kind:
        return
    layout = self.layout
    layout.separator()
    layout.operator_context = "INVOKE_DEFAULT"
    if kind == "file":
        _file_menu(layout, op.filepath)
    elif kind == "entry":
        _entry_menu(layout, op.id, op.filepath)
    elif kind == "job":
        _job_menu(layout, op.job_id, False)
    elif kind.startswith("pending:"):
        _job_menu(layout, kind.split(":", 1)[1], True)


def register():
    # Another addon may have defined it already: append to theirs.
    if not hasattr(bpy.types, "WM_MT_button_context"):
        bpy.utils.register_class(WM_MT_button_context)
    bpy.types.WM_MT_button_context.append(draw_button_menu)


def unregister():
    # The menu itself stays: another addon may have appended to it since.
    menu = getattr(bpy.types, "WM_MT_button_context", None)
    if menu is not None:
        menu.remove(draw_button_menu)
