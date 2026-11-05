"""Delete a shot or an asset the addon's way (File details): out of every
list, its folder and renders into old/ -- never by hand, which leaves its
renders behind for the next file of the same shot (lib/tracking.py
delete_owner())."""

from pathlib import Path

import bpy

from ..lib import (
    PipelineError,
    TrackingStatusCache,
    delete_owner,
    find_linked_by,
    get_active_project_root,
    linked_by_ready,
    log,
    open_elsewhere,
    owner_render_dirs,
    redraw_monitoring,
    set_monitoring_detail,
)

_LINKS_SHOWN = 6


def _kind(root: Path, owner: Path) -> str:
    return "shot" if owner.parent.parent == Path(root) / "shots" else "asset"


class M_PIPELINE_OT_delete_owner(bpy.types.Operator):
    """Delete this shot or asset: out of every list, its folder moved into
    old/ beside it, its renders into old/ too or deleted"""

    bl_idname = "m_pipeline.delete_owner"
    bl_label = "Delete"
    bl_options = {"INTERNAL"}

    folder: bpy.props.StringProperty(options={"SKIP_SAVE"})
    renders: bpy.props.EnumProperty(
        name="Its renders",
        items=[
            ("ARCHIVE", "Into old/", "Moved into the renders' old/ folder: out of the way, still there"),
            ("DELETE", "Delete", "Deleted: the space freed"),
            ("KEEP", "Leave them", "Left where they are"),
        ],
        default="ARCHIVE",
    )

    def invoke(self, context, event):
        root = get_active_project_root()
        owner = Path(self.folder)
        if not root or not self.folder:
            return {"CANCELLED"}
        # Refused while it's in use: open here, open to work on elsewhere,
        # linked by another file (an asset).
        current = bpy.data.filepath
        if current and Path(current).parent == owner:
            self.report({"ERROR"}, "It's the file open here: open another one first.")
            return {"CANCELLED"}
        busy = open_elsewhere(owner)
        if busy:
            self.report({"ERROR"}, f"Open elsewhere to work on: {', '.join(busy)}.")
            return {"CANCELLED"}
        if not linked_by_ready(root):
            find_linked_by(root, owner)  # starts the scan
            self.report({"WARNING"}, "Still reading the project's links: try again in a moment.")
            return {"CANCELLED"}
        linked = find_linked_by(root, owner)
        if linked:
            names = ", ".join(p.name for p in linked[:_LINKS_SHOWN])
            more = f" and {len(linked) - _LINKS_SHOWN} more" if len(linked) > _LINKS_SHOWN else ""
            self.report({"ERROR"}, f"Linked by {names}{more}: remove those links first.")
            return {"CANCELLED"}
        self._renders = [d.relative_to(root).as_posix() for d in owner_render_dirs(root, owner, _kind(root, owner))]
        return context.window_manager.invoke_props_dialog(
            self, width=440, title=f"Delete {owner.name}", confirm_text=f"Delete {owner.name}"
        )

    def draw(self, context):
        col = self.layout.column(align=True)
        owner = Path(self.folder)
        col.label(text="Out of every list (monitoring, snapshot, menus).", icon="TRASH")
        col.label(text=f"Its folder moved into {owner.parent.name}/old/: still there to recover.", icon="BLANK1")
        col.separator()
        renders = getattr(self, "_renders", [])
        if renders:
            col.prop(self, "renders")
            box = col.box().column(align=True)
            box.scale_y = 0.8
            box.active = False
            for d in renders:
                box.label(text=d)
        else:
            col.label(text="No render.", icon="BLANK1")

    def execute(self, context):
        root = get_active_project_root()
        owner = Path(self.folder)
        try:
            result = delete_owner(root, owner, _kind(root, owner), self.renders.lower())
        except PipelineError as e:
            log(e.level, "delete_owner", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        TrackingStatusCache.forget(owner)
        log(
            "SUCCESS",
            "delete_owner",
            f"{owner.name} deleted: folder -> {result['folder']}"
            + (f"; renders: {', '.join(result['renders'])}" if result["renders"] else ""),
        )
        # Back to the list: the detail shown is gone.
        set_monitoring_detail("file", "")
        redraw_monitoring("project")
        self.report({"INFO"}, f"{owner.name} deleted (in old/).")
        return {"FINISHED"}
