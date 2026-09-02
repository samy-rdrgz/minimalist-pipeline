"""Asset management operators: create."""

import bpy

from ..lib import (
    ConfigCache,
    PipelineError,
    asset_department_items,
    create_asset_file,
    get_active_project_root,
    json_get,
    log,
    path_reachable,
    prefix_to_parent_folder,
    sanitize_name,
)

# ---------------------------------------------------------------------------
# Dynamic enum builders
# ---------------------------------------------------------------------------


def _get_prefix_items(self, context):
    """Build enum items from both asset_prefixes and library_prefixes."""
    try:
        config = ConfigCache.get()
        structure = config.get("structure", {})

        items = []
        for p in structure.get("asset_prefixes", []):
            items.append((p, p, "Asset"))
        for p in structure.get("library_prefixes", []):
            items.append((p, p, "Library"))

        return items if items else [("ch", "ch", "Character")]
    except Exception:
        return [("ch", "ch", "Character"), ("pr", "pr", "Prop")]


# ---------------------------------------------------------------------------
# Create Asset
# ---------------------------------------------------------------------------


class PIPELINE_OT_create_asset(bpy.types.Operator):
    """Create a new asset with proper naming and folder placement."""

    bl_idname = "pipeline.create_asset"
    bl_label = "New asset"
    bl_description = "Create a new versioned asset in the active project."

    asset_prefix: bpy.props.EnumProperty(items=_get_prefix_items)
    asset_name: bpy.props.StringProperty(name="Name", default="")
    asset_description: bpy.props.StringProperty(
        name="Description",
        description="What this asset is, shown in its tracking panel.",
        default="",
    )
    create_clean: bpy.props.BoolProperty(
        name="Start with a new clean file", default=False
    )
    asset_departments: bpy.props.EnumProperty(
        items=asset_department_items,
        options={"ENUM_FLAG"},
        name="Departments",
        default=0,
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Create new asset", icon="ASSET_MANAGER")
        layout.separator()
        layout.prop(self, "asset_prefix")
        layout.prop(self, "asset_name")
        layout.textbox(self, "asset_description")
        layout.prop(self, "create_clean")
        layout.prop_menu_enum(self, "asset_departments")

        safe = sanitize_name(self.asset_name)
        v_digits = self._get_v_digits(context)
        full_name = f"{self.asset_prefix}_{safe}_v{1:0{v_digits}d}.blend"
        parent = self._get_parent_folder_name(context)

        layout.separator()
        col = layout.column()
        col.active = False
        col.scale_y = 0.5
        col.label(text=f"File: {full_name}", icon="FILE")
        col.label(text=f"In: {parent}/{self.asset_prefix}_{safe}/", icon="FILE_FOLDER")

    def invoke(self, context, event):
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        config = ConfigCache.get()
        deps = config.get("assets_departments", ["modeling", "rigging", "texturing"])
        self.asset_departments = {d for d in deps}
        self.asset_name = "new-asset"
        return context.window_manager.invoke_props_dialog(self, width=300)

    def execute(self, context):
        project_root = get_active_project_root()

        if not path_reachable(project_root):
            self.report({"ERROR"}, "Project path does not exist or is unreachable.")
            return {"CANCELLED"}

        if sanitize_name(self.asset_name) == "unnamed":
            self.report({"ERROR"}, "Asset name is required.")
            return {"CANCELLED"}

        try:
            # create_clean starts from a blank scene; otherwise the file is
            # created from whatever is currently in this session (the
            # artist's own WIP content) -- create_asset_file() below just
            # saves bpy.data as-is, it never resets the scene itself.
            if self.create_clean:
                bpy.ops.wm.read_homefile(use_empty=True)
            elif bpy.data.filepath and bpy.data.is_dirty:
                bpy.ops.wm.save_mainfile()

            dest_path = create_asset_file(
                project_root,
                prefix=self.asset_prefix,
                name=self.asset_name,
                departments=list(self.asset_departments),
                description=self.asset_description,
            )
        except PipelineError as e:
            log(e.level, "create_asset", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}

        log("SUCCESS", "create_asset", f"Created {dest_path.name}")
        self.report({"INFO"}, f"Asset created: {dest_path.name} ({dest_path.parent})")
        return {"FINISHED"}

    def _get_v_digits(self, context):
        try:
            config = ConfigCache.get()
            return int(json_get(config, "naming.version.digits", 3))
        except Exception:
            return 3

    def _get_parent_folder_name(self, context):
        """Determine 'assets' or 'library' from current prefix."""
        try:
            config = ConfigCache.get()
            return prefix_to_parent_folder(self.asset_prefix, config)
        except Exception:
            return "assets"
