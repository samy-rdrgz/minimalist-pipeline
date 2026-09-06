"""Project management operators: create, find, edit, set active, remove."""

import json
import random
import re
from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    PipelineError,
    addon_pref,
    find_project_root,
    get_addon_version,
    get_config_filepath,
    install_default_ffmpeg_preset,
    install_default_preset,
    list_to_labels,
    log,
    path_reachable,
    read_project_config,
    save_project_data,
    set_active_project_root,
)

# ---------------------------------------------------------------------------
# Default config template
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "project_name": "",
    "pipeline_addon_version": "",
    "blender_version": "",
    "resolution": {"x": 1920, "y": 1080},
    "default_fps": 30,
    "default_frame_start": 1001,
    "naming": {
        "sequence": {"prefix": "sq", "digits": 3},
        "shot": {"prefix": "sh", "digits": 3},
        "version": {"prefix": "v", "digits": 3},
        "frame": {"prefix": ".", "digits": 5},
    },
    "structure": {
        "project_folders": [
            "config",
            "refs",
            "assets",
            "library",
            "shots",
            "renders",
            "exports",
        ],
        "asset_prefixes": ["ch", "pr", "env"],
        "library_prefixes": ["mat", "gn", "tech"],
    },
    "tags": ["stable"],
    "assets_departments": ["modeling", "texturing", "rigging", "tech"],
    "shots_departments": ["layout", "animation", "lighting", "render"],
    "farm": {
        "max_concurrent_local": 1,
        "stale_monitor_seconds": 90,
        "dead_monitor_seconds": 360,
    },
}


# ---------------------------------------------------------------------------
# Create Project
# ---------------------------------------------------------------------------


class PIPELINE_OT_create_project(bpy.types.Operator):
    """Create a new project with folder structure and config."""

    bl_idname = "pipeline.create_project"
    bl_label = "Create new project"
    bl_description = "Create folder structure and pipeline config."

    project_name: bpy.props.StringProperty(
        name="Project name",
        default="new_project",
        description="Lowercase, no spaces (use underscores).",
    )
    project_path: bpy.props.StringProperty(
        name="Parent directory",
        subtype="DIR_PATH",
        default="//",
        description="Where the project folder will be created.",
    )
    create_subfolder: bpy.props.BoolProperty(
        name="Create subfolder",
        default=True,
        description="Create a subfolder named after the project inside the parent directory.",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "project_name")
        layout.prop(self, "project_path")
        layout.prop(self, "create_subfolder")

        layout.separator()
        if self.create_subfolder:
            dest = Path(self.project_path) / self.project_name
        else:
            dest = Path(self.project_path)
        layout.label(text=f"Creates: {dest}", icon="DOT")
        layout.separator(type="LINE")

        errors, warnings = self._validate()
        col = layout.column()
        if errors:
            col.alert = True
            list_to_labels(col, errors, first_icon="ERROR")
            col.alert = False
        if warnings:
            list_to_labels(col, warnings)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):
        errors, _ = self._validate()
        if errors:
            self.report({"ERROR"}, "Validation failed.")
            return {"CANCELLED"}

        if self.create_subfolder:
            project_root = Path(self.project_path) / self.project_name
        else:
            project_root = Path(self.project_path)

        try:
            for folder in DEFAULT_CONFIG["structure"]["project_folders"]:
                (project_root / folder).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.report({"ERROR"}, f"Failed to create folders: {e}")
            return {"CANCELLED"}

        config = DEFAULT_CONFIG.copy()
        config["project_name"] = self.project_name
        config["pipeline_addon_version"] = get_addon_version()
        config["blender_version"] = str(bpy.app.version)

        config_file = get_config_filepath(project_root)
        try:
            config_file.write_text(json.dumps(config, indent=4), encoding="utf-8")
        except Exception as e:
            self.report({"ERROR"}, f"Failed to write config: {e}")
            return {"CANCELLED"}

        # Activate before installing presets: install_default_preset() /
        # install_default_ffmpeg_preset() resolve their destination via
        # ConfigCache.get_path(), which relies on the *active* project root.
        try:
            self._set_active(context, str(project_root), self.project_name)
        except PipelineError as e:
            log(e.level, "create_project", e.message)
            self.report({"WARNING"}, f"Project created, but not remembered: {e}")

        install_default_preset()
        install_default_ffmpeg_preset()

        # Deferred one timer tick -- see NOTES.md, "Popup-chaining".
        project_root_str = str(project_root)
        bpy.app.timers.register(
            lambda: bpy.ops.pipeline.edit_project(
                "INVOKE_DEFAULT", project_path_selected=project_root_str
            ),
            first_interval=0.05,
        )
        self.report({"INFO"}, f"Project created: {self.project_name}")
        return {"FINISHED"}

    def _validate(self):
        errors = []
        warnings = []

        if not Path(self.project_path).is_dir():
            errors.append([f"Path '{self.project_path}' is not valid."])

        if not re.fullmatch(r"[a-z0-9_]+", self.project_name):
            errors.append(
                [
                    f'Name "{self.project_name}" is invalid.',
                    "Use lowercase letters, digits, or underscores only.",
                ]
            )

        if self.create_subfolder:
            dest = Path(self.project_path) / self.project_name
            if dest.exists():
                warnings.append([f'Folder "{self.project_name}" already exists.'])

        return (errors or None, warnings or None)

    def _set_active(self, context, project_root, name):
        prefs = addon_pref(context)
        set_active_project_root(prefs, project_root)
        if not any(item.path == project_root for item in prefs.opened_projects):
            new_item = prefs.opened_projects.add()
            new_item.name = name
            new_item.path = project_root
        save_project_data(prefs)


# ---------------------------------------------------------------------------
# Find Existing Project
# ---------------------------------------------------------------------------


class PIPELINE_OT_find_project(bpy.types.Operator):
    """Locate and activate an existing project."""

    bl_idname = "pipeline.find_project"
    bl_label = "Find existing project"
    bl_description = "Select a folder containing a pipeline config."

    project_root_path: bpy.props.StringProperty(
        name="Project folder",
        subtype="DIR_PATH",
        description="Root folder (must contain config/project_config.json).",
        default="//",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Select the project root folder:", icon="FILE_FOLDER")
        layout.prop(self, "project_root_path")
        layout.label(text="Looking for config/project_config.json", icon="QUESTION")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):
        found = find_project_root(self.project_root_path)
        if not found:
            self.report(
                {"ERROR"}, "No project_config.json found here or in parent folders."
            )
            return {"CANCELLED"}
        root = found
        config_file = get_config_filepath(root)

        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
            name = data.get("project_name", root.name)
        except Exception:
            name = root.name

        prefs = addon_pref(context)
        set_active_project_root(prefs, str(root))

        if not any(item.path == str(root) for item in prefs.opened_projects):
            new_item = prefs.opened_projects.add()
            new_item.name = name
            new_item.path = str(root)

        save_project_data(prefs)
        install_default_preset()
        install_default_ffmpeg_preset()  # backfill for older projects

        bpy.ops.pipeline.text_popup(
            "INVOKE_DEFAULT", title="Project activated", message=name, icon="CHECKMARK"
        )
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Set Active Project
# ---------------------------------------------------------------------------


class PIPELINE_OT_set_active_project(bpy.types.Operator):
    """Set a project from the list as active."""

    bl_idname = "pipeline.set_active_project"
    bl_label = "Activate project"

    project_path_selected: bpy.props.StringProperty()

    def execute(self, context):
        project_root = self.project_path_selected
        if not project_root or not path_reachable(project_root):
            self.report({"ERROR"}, "Invalid or unreachable project path.")
            return {"CANCELLED"}

        prefs = addon_pref(context)
        set_active_project_root(prefs, project_root)
        try:
            save_project_data(prefs)
        except PipelineError as e:
            log(e.level, "set_active_project", e.message)
            self.report({"WARNING"}, f"Active, but not backed up: {e}")

        self.report({"INFO"}, f"Active: {Path(project_root).name}")
        return {"FINISHED"}


class PIPELINE_OT_unset_active_project(bpy.types.Operator):
    """Unset active project (no project active)."""

    bl_idname = "pipeline.unset_active_project"
    bl_label = "Unset active project"

    def execute(self, context):
        prefs = addon_pref(context)
        set_active_project_root(prefs, "")
        try:
            save_project_data(prefs)
        except PipelineError as e:
            log(e.level, "unset_active_project", e.message)
            self.report({"WARNING"}, f"Unset, but not backed up: {e}")

        self.report({"INFO"}, "No active project.")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Remove Project (from list, not from disk)
# ---------------------------------------------------------------------------


class PIPELINE_OT_remove_project(bpy.types.Operator):
    """Remove project from list (files stay on disk)."""

    bl_idname = "pipeline.remove_project"
    bl_label = ""
    bl_description = "Remove this project from your list."

    project_path_selected: bpy.props.StringProperty()

    def draw(self, context):
        layout = self.layout
        layout.label(text="Remove from list?", icon="QUESTION")
        layout.label(text=f"Path: {self.project_path_selected}", icon="TRASH")
        layout.separator()
        layout.label(text="Files on disk are NOT deleted.", icon="INFO")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=350)

    def execute(self, context):
        prefs = addon_pref(context)
        for idx, item in enumerate(prefs.opened_projects):
            if item.path == self.project_path_selected:
                name = item.name
                prefs.opened_projects.remove(idx)
                if prefs.active_project_root == self.project_path_selected:
                    prefs.active_project_root = ""
                try:
                    save_project_data(prefs)
                except PipelineError as e:
                    log(e.level, "remove_project", e.message)
                    self.report({"WARNING"}, f"Removed, but not backed up: {e}")
                    return {"FINISHED"}
                self.report({"INFO"}, f"Removed from list: {name}")
                return {"FINISHED"}
        return {"CANCELLED"}


# ---------------------------------------------------------------------------
# Edit Project Config
# ---------------------------------------------------------------------------


class PIPELINE_OT_edit_project(bpy.types.Operator):
    """Edit project configuration."""

    bl_idname = "pipeline.edit_project"
    bl_label = ""
    bl_description = "Edit project settings."

    project_path_selected: bpy.props.StringProperty()

    project_name: bpy.props.StringProperty()
    project_bl_version: bpy.props.StringProperty(name="")
    resolution_x: bpy.props.IntProperty(name="", min=128, max=8192, default=1920)
    resolution_y: bpy.props.IntProperty(name="", min=128, max=8192, default=1080)
    default_fps: bpy.props.IntProperty(name="", min=4, max=120, default=30)
    default_frame_start: bpy.props.IntProperty(name="", min=0, default=1001)

    sequence_prefix: bpy.props.StringProperty(name="", default="sq")
    shot_prefix: bpy.props.StringProperty(name="", default="sh")
    version_prefix: bpy.props.StringProperty(name="", default="v")
    frame_prefix: bpy.props.StringProperty(name="", default=".")
    sequence_digits: bpy.props.IntProperty(name="", default=3, min=1, max=8)
    shot_digits: bpy.props.IntProperty(name="", default=3, min=1, max=8)
    version_digits: bpy.props.IntProperty(name="", default=3, min=1, max=8)
    frame_digits: bpy.props.IntProperty(name="", default=5, min=1, max=8)

    asset_prefixes: bpy.props.StringProperty(name="", default="ch,pr,env")
    library_prefixes: bpy.props.StringProperty(name="", default="mat,gn,tech")
    project_folders: bpy.props.StringProperty(
        name="", default="config,refs,assets,library,shots,renders,exports"
    )
    tags: bpy.props.StringProperty(name="", default="stable")

    assets_departments: bpy.props.StringProperty(
        name="", default="modeling,texturing,rigging,tech"
    )
    shots_departments: bpy.props.StringProperty(
        name="", default="layout,animation,lighting,render"
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Editing: {self.project_name}", icon="FILE_TEXT")
        layout.separator()

        # Read-only
        box = layout.box()
        for label, icon, value in [
            ("NAME", "PINNED", self.project_name),
            ("PATH", "BLANK1", self.project_path_selected),
        ]:
            row = box.split(factor=0.33, align=True)
            row.label(text=label, icon=icon)
            sub = row.box()
            sub.scale_y = 0.6
            sub.label(text=value, icon="LOCKED")

        row = box.split(factor=0.33, align=True)
        row.label(text="BLENDER", icon="BLENDER")
        row.prop(self, "project_bl_version")

        # Resolution / FPS
        box = layout.box().column(align=False)
        row = box.row(align=True)
        row.label(text="RESOLUTION", icon="RESTRICT_VIEW_OFF")
        row.prop(self, "resolution_x")
        row.prop(self, "resolution_y")
        row = box.row(align=True)
        row.label(text="FRAME RATE", icon="PREVIEW_RANGE")
        row.prop(self, "default_fps")
        row.label(text="")
        row = box.row(align=True)
        row.label(text="SHOT START", icon="DECORATE_KEYFRAME")
        row.prop(self, "default_frame_start")
        row.label(text="")

        # Naming
        box = layout.box().column(align=False)
        row = box.row(align=True)
        row.label(text="")
        row.label(text="PREFIX", icon="SYNTAX_OFF")
        row.label(text="DIGITS", icon="SORTBYEXT")

        for label, icon, p_prop, d_prop in [
            ("SEQUENCE", "LAYER_ACTIVE", "sequence_prefix", "sequence_digits"),
            ("SHOT", "LAYER_USED", "shot_prefix", "shot_digits"),
            ("VERSION", "CHECKMARK", "version_prefix", "version_digits"),
            ("FRAME", "KEYFRAME_HLT", "frame_prefix", "frame_digits"),
        ]:
            row = box.row(align=True)
            row.label(text=label, icon=icon)
            row.prop(self, p_prop)
            row.prop(self, d_prop)

        box.separator(type="LINE")
        col = box.column()
        col.active = False
        col.scale_y = 0.5
        col.label(
            text=(
                f"e.g.: {self.sequence_prefix}{self._rdm(self.sequence_digits)}"
                f"_{self.shot_prefix}{self._rdm(self.shot_digits)}"
                f"_{self.version_prefix}{self._rdm(self.version_digits)}.blend"
            ),
            icon="BLANK1",
        )

        # Structure
        box = layout.box().column(align=False)
        for label, icon, prop in [
            ("FOLDERS", "OUTLINER", "project_folders"),
            ("ASSET PREFIX", "MESH_MONKEY", "asset_prefixes"),
            ("LIBRARY PREFIX", "TOOL_SETTINGS", "library_prefixes"),
            ("VERSION TAGS", "BOOKMARKS", "tags"),
            ("ASSETS DEPARTMENTS", "COPY_ID", "assets_departments"),
            ("SHOTS DEPARTMENTS", "COPY_ID", "shots_departments"),
        ]:
            row = box.split(factor=0.33, align=True)
            row.label(text=label, icon=icon)
            row.prop(self, prop)

        box.separator(type="LINE")
        col = box.column()
        col.active = False
        col.scale_y = 0.5
        all_pf = self.asset_prefixes + "," + self.library_prefixes
        col.label(
            text=(
                f"e.g.: {self._rdm_from(all_pf)}_asset-name"
                f"_{self.version_prefix}{self._rdm(self.version_digits)}.blend"
            ),
            icon="BLANK1",
        )

    def invoke(self, context, event):
        try:
            config = read_project_config(self.project_path_selected)
        except PipelineError as e:
            log(e.level, "edit_project", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}

        root = self.project_path_selected
        self.project_name = config.get("project_name", Path(root).name)
        self.project_bl_version = config.get(
            "blender_version", config.get("project_bl_version", "")
        )

        res = config.get("resolution", {})
        self.resolution_x = int(res.get("x", 1920))
        self.resolution_y = int(res.get("y", 1080))
        self.default_fps = int(config.get("default_fps", 30))
        self.default_frame_start = int(config.get("default_frame_start", 1001))

        naming = config.get("naming", {})
        for key in ("sequence", "shot", "version", "frame"):
            sub = naming.get(key, {})
            setattr(
                self, f"{key}_prefix", sub.get("prefix", getattr(self, f"{key}_prefix"))
            )
            setattr(
                self,
                f"{key}_digits",
                int(sub.get("digits", getattr(self, f"{key}_digits"))),
            )

        structure = config.get("structure", {})
        self.asset_prefixes = self._list_to_csv(
            structure.get("asset_prefixes", structure.get("assets_prefix", []))
        )
        self.library_prefixes = self._list_to_csv(structure.get("library_prefixes", []))
        self.project_folders = self._list_to_csv(structure.get("project_folders", []))
        self.tags = self._list_to_csv(config.get("tags", ["stable"]))
        self.assets_departments = self._list_to_csv(
            config.get(
                "assets_departments", ["modeling", "texturing", "rigging", "tech"]
            ),
        )
        self.shots_departments = self._list_to_csv(
            config.get(
                "shots_departments", ["layout", "animation", "lighting", "render"]
            ),
        )

        return context.window_manager.invoke_props_dialog(self, width=350)

    def execute(self, context):
        try:
            config = read_project_config(self.project_path_selected)
        except PipelineError as e:
            log("WARNING", "edit_project", f"{e.message} -- writing a fresh config.")
            config = {}

        config.update(
            {
                "project_name": self.project_name,
                "pipeline_addon_version": get_addon_version(),
                "blender_version": self.project_bl_version,
                "resolution": {"x": self.resolution_x, "y": self.resolution_y},
                "default_fps": self.default_fps,
                "default_frame_start": self.default_frame_start,
                "naming": {
                    "sequence": {
                        "prefix": self.sequence_prefix,
                        "digits": self.sequence_digits,
                    },
                    "shot": {"prefix": self.shot_prefix, "digits": self.shot_digits},
                    "version": {
                        "prefix": self.version_prefix,
                        "digits": self.version_digits,
                    },
                    "frame": {"prefix": self.frame_prefix, "digits": self.frame_digits},
                },
                "structure": {
                    "project_folders": self._csv_to_list(self.project_folders),
                    "asset_prefixes": self._csv_to_list(self.asset_prefixes),
                    "library_prefixes": self._csv_to_list(self.library_prefixes),
                },
                "tags": self._csv_to_list(self.tags),
                "assets_departments": self._csv_to_list(self.assets_departments),
                "shots_departments": self._csv_to_list(self.shots_departments),
                # "farm" is never touched here -- stays as read from the loaded config
            }
        )
        try:
            config_file = get_config_filepath(self.project_path_selected)
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(json.dumps(config, indent=4), encoding="utf-8")
            ConfigCache.invalidate()
        except Exception as e:
            self.report({"ERROR"}, f"Failed to save config: {e}")
            return {"CANCELLED"}

        try:
            save_project_data(addon_pref(context))
        except PipelineError as e:
            log(e.level, "edit_project", e.message)
            self.report({"WARNING"}, f"Config saved, but not backed up: {e}")

        self.report({"INFO"}, f"Config saved for {self.project_name}.")
        return {"FINISHED"}

    @staticmethod
    def _csv_to_list(csv_str):
        return [s.strip() for s in str(csv_str).split(",") if s.strip()]

    @staticmethod
    def _list_to_csv(data):
        if isinstance(data, (list, tuple)):
            return ",".join(str(s).strip() for s in data if str(s).strip())
        return str(data) if data else ""

    def _rdm(self, digits):
        return f"{random.randint(1, 10**digits - 1):0{digits}d}"

    def _rdm_from(self, csv_str):
        items = [s.strip() for s in csv_str.split(",") if s.strip()]
        return random.choice(items) if items else "xx"
