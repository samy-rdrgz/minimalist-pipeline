"""Right-click menus on the addon's own buttons -- Blender's button context
menu: a note or task (the File panel's Notes & tasks). A button offers one
by its operator's hidden "rmb" property ("entry")."""

import bpy

from ..lib import TrackingStatusCache


class WM_MT_button_context(bpy.types.Menu):
    """Blender's hook into every button's right-click menu: defined by the
    first addon that needs it, then appended to."""

    bl_label = ""

    def draw(self, context):
        pass


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
    if kind == "entry":
        _entry_menu(layout, op.id, op.filepath)


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
