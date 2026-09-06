"""File browser operator: open a versioned project file via cascade dropdowns."""

from pathlib import Path

import bpy

from ..lib import (
    asset_folder_items,
    dir_version_items,
    get_active_project_root,
    get_folder,
    parse_filename,
    prefix_items,
    sequence_items,
    shot_items,
    version_items,
)

# ---------------------------------------------------------------------------
# Folder resolution helper (used by enum callbacks and _resolve)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------


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
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        MAX_ROW = 15
        layout = self.layout

        row = layout.row()
        row.prop(self, "file_type", expand=True)
        layout.separator()

        if self.file_type == "asset":
            row = layout.split(align=True, factor=0.5)
            if len(prefix_items(self, context)) < MAX_ROW:
                row.column().prop(self, "asset_prefix", expand=True)
            else:
                row.column().prop(self, "asset_prefix", text="")
            if len(asset_folder_items(self, context)) < MAX_ROW:
                row.column().prop(self, "asset_folder", expand=True)
            else:
                row.column().prop(self, "asset_folder", text="")

        else:
            row = layout.split(align=True, factor=0.5)
            if len(sequence_items(self, context)) < MAX_ROW:
                row.column().prop(self, "sequence", expand=True)
            else:
                row.column().prop(self, "sequence", text="")

            if len(shot_items(self, context)) < MAX_ROW:
                row.column().prop(self, "shot", expand=True)
            else:
                row.column().prop(self, "shot", text="")

        layout.separator()

        row = layout.row()
        row.prop(self, "version_mode", expand=True)
        if self.version_mode == "custom":
            layout.prop(self, "custom_version", text="")

        layout.separator()
        col = layout.column()
        col.scale_y = 0.6
        col.active = False
        resolved = self._resolve(context)
        if resolved:
            col.label(text=resolved.name, icon="FILE_BLEND")
        else:
            col.label(text="No matching file found.", icon="ERROR")

    def execute(self, context):
        resolved = self._resolve(context)
        if not resolved:
            self.report({"ERROR"}, "No matching file found.")
            return {"CANCELLED"}
        try:
            bpy.ops.wm.open_mainfile(filepath=str(resolved))
        except RuntimeError as e:
            self.report({"ERROR"}, f"Could not open {resolved.name}: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Opened: {resolved.name}")
        return {"FINISHED"}

    def _resolve(self, context) -> Path | None:
        """Return the Path of the file matching current selections, or None."""
        folder = get_folder(self, context)
        if not folder or not folder.exists():
            return None

        candidates = []
        for f in folder.iterdir():
            if f.suffix != ".blend":
                continue
            parsed = parse_filename(f.name)
            if parsed:
                candidates.append((f, int(parsed["number"]), parsed.get("tag")))

        if not candidates:
            return None

        if self.version_mode == "last":
            return max(candidates, key=lambda x: x[1])[0]

        if self.version_mode == "stable":
            stable = [(f, v, t) for f, v, t in candidates if t == "stable"]
            return max(stable, key=lambda x: x[1])[0] if stable else None

        if self.version_mode == "custom":
            if self.custom_version and self.custom_version != "NONE":
                p = Path(self.custom_version)
                return p if p.exists() else None

        return None


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
            return self.execute(context)

        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
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
        col = layout.column()
        col.scale_y = 0.6
        col.active = False
        resolved = self._resolve(context)
        if resolved:
            col.label(text=resolved.name, icon="FILE_BLEND")
        else:
            col.label(text="No matching file found.", icon="ERROR")

    def execute(self, context):
        target = Path(self.filepath)
        if not (target.exists() and target.is_file()):
            target = self._resolve(context)
            if not target:
                self.report({"ERROR"}, "No matching file found.")
                return {"CANCELLED"}

        try:
            bpy.ops.wm.open_mainfile(filepath=str(target))
        except RuntimeError as e:
            self.report({"ERROR"}, f"Could not open {target.name}: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Opened: {target.name}")
        return {"FINISHED"}

    def _resolve(self, context) -> Path | None:
        """Return the Path of the file matching current selections, or None."""
        folder = Path(self.filepath)
        if not folder or not folder.exists():
            return None

        candidates = []
        for f in folder.iterdir():
            if f.suffix != ".blend":
                continue
            parsed = parse_filename(f.name)
            if parsed:
                candidates.append((f, int(parsed["number"]), parsed.get("tag")))

        if not candidates:
            return None

        if self.version_mode == "last":
            return max(candidates, key=lambda x: x[1])[0]

        if self.version_mode == "stable":
            stable = [(f, v, t) for f, v, t in candidates if t == "stable"]
            return max(stable, key=lambda x: x[1])[0] if stable else None

        if self.version_mode == "custom":
            if self.custom_version and self.custom_version != "NONE":
                p = Path(self.custom_version)
                return p if p.exists() else None

        return None
