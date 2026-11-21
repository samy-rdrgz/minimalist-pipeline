"""File browser operator: open a versioned project file via cascade dropdowns."""

from pathlib import Path

import bpy

from ..lib import (
    asset_folder_items,
    dir_version_items,
    get_active_project_root,
    get_folder,
    open_mainfile,
    prefix_items,
    resolve_version_file,
    scan_descriptions,
    sequence_items,
    shot_items,
    version_items,
)
from ..lib.session import elsewhere_text, open_elsewhere
from ..lib.ui import choice

# ---------------------------------------------------------------------------
# Folder resolution helper (used by enum callbacks and _resolve)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------


_ELSEWHERE_TTL = 3.0  # seconds: draw() runs on every redraw, the sessions on a share
_elsewhere_cache: dict = {"key": None, "at": 0.0, "value": []}


def _elsewhere(resolved: Path | None) -> list:
    """open_elsewhere() for the file a pick resolves to, kept a few seconds."""
    import time

    if not resolved:
        return []
    key = str(resolved.parent)
    c = _elsewhere_cache
    if c["key"] != key or time.monotonic() - c["at"] > _ELSEWHERE_TTL:
        c.update(key=key, at=time.monotonic(), value=open_elsewhere(str(resolved)))
    return c["value"]


def _draw_resolved(layout, resolved: Path | None) -> None:
    """The file a pick resolves to, greyed -- or none found; and who else
    has its shot or asset open now, any version (a warning, not a lock)."""
    col = layout.column()
    col.scale_y = 0.6
    col.active = False
    if resolved:
        col.label(text=resolved.name, icon="FILE_BLEND")
    else:
        col.label(text="No matching file found.", icon="ERROR")
    for o in _elsewhere(resolved):
        row = layout.row()
        row.alert = True
        row.label(text=f"Also open: {o['user'] or '?'} on {o['machine']} ({o['file']})", icon="ERROR")


class M_PIPELINE_OT_open_file(bpy.types.Operator):
    """Browse and open a versioned file from the active project."""

    bl_idname = "m_pipeline.open_file"
    bl_label = "Open project file"
    bl_description = "Open an asset or shot from the active project."

    file_type: bpy.props.EnumProperty(
        items=[
            ("asset", "Asset / Library", "Asset and Library files"),
            ("shot", "Shot", "Shot sequence files"),
        ],
        default="asset",
    )

    # Asset cascade: prefix → folder
    asset_prefix: bpy.props.EnumProperty(items=prefix_items)
    asset_folder: bpy.props.EnumProperty(items=asset_folder_items)

    # Shot cascade: sequence → shot
    sequence: bpy.props.EnumProperty(items=sequence_items)
    shot: bpy.props.EnumProperty(
        items=shot_items,
    )

    # Version selection
    version_mode: bpy.props.EnumProperty(
        items=[
            ("last", "Last", "Most recent version"),
            ("stable", "Last stable", "Most recent -stable version"),
            ("custom", "Custom", "Pick a specific version"),
        ],
        default="last",
    )
    custom_version: bpy.props.EnumProperty(items=version_items)

    def invoke(self, context, event):
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        scan_descriptions(get_active_project_root())  # menu tooltips
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        MAX_ROW = 10

        TITLE_WIDTH = 0.25
        layout = self.layout.column(align=True)

        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Type", icon="FILE_BLEND")
        row.row(align=True).prop(self, "file_type", expand=True)

        layout.separator()
        row = layout.split(factor=TITLE_WIDTH, align=True)

        asset = self.file_type == "asset"
        row.label(text="Asset" if asset else "Shot", icon="OUTLINER_OB_ARMATURE" if asset else "VIEW_CAMERA")
        row = row.split(align=True, factor=0.5)
        for prop, items in (
            (("asset_prefix", prefix_items), ("asset_folder", asset_folder_items))
            if asset
            else (("sequence", sequence_items), ("shot", shot_items))
        ):
            choice(row.column(align=True), self, prop, len(items(self, context)), MAX_ROW)

        layout.separator()

        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Version", icon="COPY_ID")
        row.row(align=True).prop(self, "version_mode", expand=True)
        if self.version_mode == "custom":
            row = layout.split(factor=TITLE_WIDTH, align=True)
            row.label(text="", icon="BLANK1")
            row.prop(self, "custom_version", text="")

        layout.separator(type="LINE", factor=3)

        _draw_resolved(layout, self._resolve(context))

    def execute(self, context):
        resolved = self._resolve(context)
        if not resolved:
            self.report({"ERROR"}, "No matching file found.")
            return {"CANCELLED"}
        try:
            open_mainfile(str(resolved))
        except RuntimeError as e:
            self.report({"ERROR"}, f"Could not open {resolved.name}: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Opened: {resolved.name}")
        return {"FINISHED"}

    def _resolve(self, context) -> Path | None:
        """Return the Path of the file matching current selections, or None.
        Called from draw() on every redraw -- see resolve_version_file()."""
        folder = get_folder(self, context)
        return resolve_version_file(folder, self.version_mode, self.custom_version)


class M_PIPELINE_OT_open_file_version(bpy.types.Operator):
    """Open a versioned file from the active project."""

    bl_idname = "m_pipeline.open_file_version"
    bl_label = "Open project file"
    bl_description = "Open an asset or shot from the active project."

    filepath: bpy.props.StringProperty(name="Filepath", default="")
    version_mode: bpy.props.EnumProperty(
        items=[
            ("last", "Last", "Most recent version"),
            ("stable", "Last stable", "Most recent -stable version"),
            ("custom", "Custom", "Pick a specific version"),
        ],
        default="last",
    )
    custom_version: bpy.props.EnumProperty(items=dir_version_items)

    def invoke(self, context, event):
        if Path(self.filepath).exists() and Path(self.filepath).is_file():
            others = open_elsewhere(self.filepath)
            if others:  # its shot or asset open in another Blender: asked first
                return context.window_manager.invoke_confirm(
                    self,
                    event,
                    title="Already open elsewhere",
                    message=f"Also open: {elsewhere_text(others)}. Open all the same?",
                    confirm_text="Open",
                    icon="ERROR",
                )
            return self.execute(context)

        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        scan_descriptions(get_active_project_root())  # menu tooltips
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout

        layout.label(
            text=f"Select the version to open for: {Path(self.filepath).relative_to(get_active_project_root())!s}",
        )

        row = layout.row()
        row.prop(self, "version_mode", expand=True)
        if self.version_mode == "custom":
            layout.prop(self, "custom_version", text="")

        layout.separator()
        _draw_resolved(layout, self._resolve(context))

    def execute(self, context):
        target = Path(self.filepath)
        if not (target.exists() and target.is_file()):
            target = self._resolve(context)
            if not target:
                self.report({"ERROR"}, "No matching file found.")
                return {"CANCELLED"}

        try:
            open_mainfile(str(target))
        except RuntimeError as e:
            self.report({"ERROR"}, f"Could not open {target.name}: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Opened: {target.name}")
        return {"FINISHED"}

    def _resolve(self, context) -> Path | None:
        """Return the Path of the file matching current selections, or None.
        Called from draw() on every redraw -- see resolve_version_file()."""
        folder = Path(self.filepath)
        return resolve_version_file(folder, self.version_mode, self.custom_version)
