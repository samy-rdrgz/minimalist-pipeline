"""Project management operators: create, find, edit, set active, remove."""

import json
import os
import random
import re
from pathlib import Path

import bpy

from ..lib.monitoring.status import departments_text, parse_departments
from ..lib import (
    install_department_presets,
    project_team,
    DEFAULT_ASSET_DEPARTMENTS,
    DEFAULT_SHOT_DEPARTMENTS,
    PROGRESS_WEIGHTS,
    WORK_WEEK,
    ConfigCache,
    PipelineError,
    addon_pref,
    find_project_root,
    get_addon_version,
    get_config_filepath,
    get_user,
    install_default_ffmpeg_preset,
    install_default_preset,
    json_get,
    list_to_labels,
    log,
    parse_day,
    path_reachable,
    progress_weights,
    project_schedule,
    read_project_config,
    report_error,
    save_project_data,
    set_active_project_root,
    thumbnail_size,
    validation_roles,
    warn_blender_version_mismatch,
)
from ..lib.migration import migration_record
from ..lib.presets import presets_without_department, preset_rename_problem, rename_preset
from ..lib.core import cached_scandir, write_json_atomic
from ..lib import formats
from ..lib.monitoring.status import preset_department
from .farm_ops import (
    _NO_SCRIPT,
    _stable_enum_items,
    default_pre_render_script,
    pre_render_script_items,
)

_edited_pre_render_scripts: list[tuple[str, str, str]] = []


def _edited_project_scripts(self, context):
    """Pre-render presets of the project being edited -- not necessarily
    the active one."""
    root = self.project_path_selected
    presets = Path(root) / "config" / "presets" if root else None
    # The departments as typed in the fields, not yet saved.
    departments = [
        *parse_departments(self.shots_departments)[0],
        *parse_departments(self.assets_departments)[0],
    ]
    return _stable_enum_items(
        _edited_pre_render_scripts, pre_render_script_items(presets, departments)
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
    "assets_departments": DEFAULT_ASSET_DEPARTMENTS,
    "shots_departments": DEFAULT_SHOT_DEPARTMENTS,
    "thumbnails": {"size": 240},
    # The compiled video (farm/post_render.py VIDEO_FORMATS): an mp4 smooth
    # to edit; a project from before has none -- its preset file stays.
    "video": {"format": "mp4"},
    "farm": {
        "max_concurrent_local": 1,
        "stale_monitor_seconds": 90,
        "dead_monitor_seconds": 360,
        "stuck_frame_factor": 5,
        "priority_switch_minutes": 3,
        "chunk_size": 5,
    },
}


# ---------------------------------------------------------------------------
# Create Project
# ---------------------------------------------------------------------------


class M_PIPELINE_OT_create_project(bpy.types.Operator):
    """Create a new project with folder structure and config."""

    bl_idname = "m_pipeline.create_project"
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
        # Its data is this version's from the start: nothing to migrate.
        config["data_migrations"] = migration_record(get_user(context))

        config_file = get_config_filepath(project_root)
        try:
            write_json_atomic(config_file, config)
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
        # A render preset per department (<department>_default.py).
        install_department_presets([*config.get("shots_departments", []), *config.get("assets_departments", [])])

        # Deferred one timer tick -- see NOTES.md, "Popup-chaining".
        project_root_str = str(project_root)
        bpy.app.timers.register(
            lambda: bpy.ops.m_pipeline.edit_project(
                "INVOKE_DEFAULT", project_path_selected=project_root_str
            ),
            first_interval=0.05,
        )
        self.report({"INFO"}, f"Project created: {self.project_name}")
        return {"FINISHED"}

    def _validate(self):
        """(errors, warnings) of the new project's path and name, each a list of
        message lines."""
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
        """Make project_root the active project, added to the opened projects if
        it isn't there, and save the list."""
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


class M_PIPELINE_OT_find_project(bpy.types.Operator):
    """Locate and activate an existing project."""

    bl_idname = "m_pipeline.find_project"
    bl_label = "Find existing project"
    bl_description = "Select a folder containing a pipeline config."

    # The file browser straight away: its Accept activates the project (a
    # dialog first only held a path field opening the same browser).
    directory: bpy.props.StringProperty(
        name="Project folder",
        subtype="DIR_PATH",
        description="The project's folder, or any folder inside it: "
        "config/project_config.json is looked for there and above",
    )
    filter_folder: bpy.props.BoolProperty(default=True, options={"HIDDEN"})
    # Scripts and older calls: a path given, no browser.
    project_root_path: bpy.props.StringProperty(
        name="Project folder", subtype="DIR_PATH", default="", options={"HIDDEN"}
    )

    def invoke(self, context, event):
        if self.project_root_path:
            return self.execute(context)
        # Starts beside the projects already known, the last one's parent.
        known = [item.path for item in addon_pref(context).opened_projects]
        parent = next(
            (str(Path(p).parent) for p in reversed(known) if path_reachable(p)), ""
        )
        if parent:
            self.directory = parent + os.sep
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        folder = self.project_root_path or self.directory
        found = find_project_root(bpy.path.abspath(folder)) if folder else None
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
        # Deferred: a popup can't open from inside this operator's execute().
        bpy.app.timers.register(warn_blender_version_mismatch, first_interval=0.1)

        if not any(item.path == str(root) for item in prefs.opened_projects):
            new_item = prefs.opened_projects.add()
            new_item.name = name
            new_item.path = str(root)

        save_project_data(prefs)
        install_default_preset()
        install_default_ffmpeg_preset()  # backfill for older projects

        bpy.ops.m_pipeline.text_popup(
            "INVOKE_DEFAULT", title="Project activated", message=name, icon="CHECKMARK"
        )
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Set Active Project
# ---------------------------------------------------------------------------


class M_PIPELINE_OT_set_active_project(bpy.types.Operator):
    """Set a project from the list as active."""

    bl_idname = "m_pipeline.set_active_project"
    bl_label = "Activate project"

    project_path_selected: bpy.props.StringProperty()

    def execute(self, context):
        project_root = self.project_path_selected
        if not project_root or not path_reachable(project_root):
            self.report({"ERROR"}, "Invalid or unreachable project path.")
            return {"CANCELLED"}

        prefs = addon_pref(context)
        set_active_project_root(prefs, project_root)
        # Deferred: a popup can't open from inside this operator's execute().
        bpy.app.timers.register(warn_blender_version_mismatch, first_interval=0.1)
        try:
            save_project_data(prefs)
        except PipelineError as e:
            log(e.level, "set_active_project", e.message)
            self.report({"WARNING"}, f"Active, but not backed up: {e}")

        self.report({"INFO"}, f"Active: {Path(project_root).name}")
        return {"FINISHED"}


class M_PIPELINE_OT_unset_active_project(bpy.types.Operator):
    """Unset active project (no project active)."""

    bl_idname = "m_pipeline.unset_active_project"
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


class M_PIPELINE_OT_remove_project(bpy.types.Operator):
    """Remove project from list (files stay on disk)."""

    bl_idname = "m_pipeline.remove_project"
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


def _example(box, text: str) -> None:
    """A settings box's greyed example, under a line."""
    box.separator(type="LINE")
    col = box.column()
    col.active = False
    col.scale_y = 0.5
    col.label(text=text, icon="BLANK1")


# A field's "?" in Project settings: (title, how to fill it, with examples).
_HELP = {
    "project_folders": ("Folders", "Made at the project's root, a comma between them:\n"
                        "    config, refs, assets, library, shots, renders, exports"),
    "asset_prefixes": ("Asset prefixes", "An asset's kind, its name's start, a comma between them:\n"
                       "    ch, pr, env, fx\n-> ch_bob, pr_lamp, env_forest"),
    "library_prefixes": ("Library prefixes", "The library's kinds, as the assets':\n"
                         "    mat, gn, tech\n-> mat_wood, gn_scatter"),
    "tags": ("Version tags", "Words a version may carry after its number:\n"
             "    stable, approved\n-> sq010_sh010_v003-stable.blend"),
    "assets_departments": ("Departments", "In their order, a comma between them:\n"
                           "    modeling, texturing, rigging\n"
                           "Stages: > between them -- after a >, it waits for the ones\n"
                           "before it, and is to redo when they change:\n"
                           "    modeling > texturing, rigging\n"
                           "A render preset named after one (rigging_hd) is its renders'."),
    "shots_departments": ("Departments", "In their order, a comma between them:\n"
                          "    layout, animation, lighting, render\n"
                          "Stages: > between them -- after a >, it waits for the ones\n"
                          "before it, and is to redo when they change:\n"
                          "    layout > animation > fx, lighting > render\n"
                          "A render preset named after one (animation_hd) is its renders'."),
    "validation_roles": ("Validation roles", "role:level, a comma between them -- a higher level\n"
                         "covers the lower ones, the same level is equivalent:\n"
                         "    sup:1, prod:2\n    sup:1, prod:2, real:2"),
    "team": ("Team", "Names, a comma between them:\n    léa, tom, sam\n"
             "Each picks theirs as user name (Preferences); departments\n"
             "are assigned to them (File details)."),
    "sequence_prefix": ("Naming", "Each part a prefix, then its number on so many digits:\n"
                        "    sq + 3 -> sq010    sh + 3 -> sh040    v + 3 -> v003\n"
                        "-> sq010_sh040_v003.blend; a frame: . + 4 -> name.1001.png"),
    "shot_prefix": ("Naming", "A shot's prefix and digits: sh + 3 -> sh040.\n"
                    "A block of shots joins them with -: sq010_sh010-020-030."),
    "schedule_start": ("Schedule", "First and last day, day first:\n    05/01/2026    30/06/2026\n"
                       "Both empty: no schedule."),
    "schedule_days_off": ("Days off", "Public holidays and days off, day first, a comma\n"
                          "between them:\n    25/12/2026, 01/01/2027"),
}


# Project settings' grid: each line's cells on this many equal slots
# (ProjectSettings._rows()).
_SLOTS = 3


def _settings_row(box, label: str, icon: str, help: str = ""):
    """One Project settings line: a split, its label on the first third
    (with its "?", _HELP[help], when it has one), then each item added
    shares the rest equally -- a row would size them by their content, and
    the columns would drift from line to line."""
    split = box.split(factor=0.33, align=True)
    head = split.row(align=True)
    head.label(text=label, icon=icon)
    if help in _HELP:
        title, text = _HELP[help]
        op = head.operator("m_pipeline.text_popup", text="", icon="QUESTION", emboss=False)
        op.icon, op.title, op.message = "QUESTION", title, text
    return split


class ProjectSettings:
    """Project settings' fields, drawing, reading and writing -- shared by
    the window (PIPELINE_PG_project_settings, on the WindowManager) and the
    dialog it falls back on (M_PIPELINE_OT_edit_project). Their properties
    are this class's annotations, copied onto each."""

    project_path_selected: bpy.props.StringProperty()

    project_name: bpy.props.StringProperty()
    project_bl_version: bpy.props.StringProperty(name="")
    resolution_x: bpy.props.IntProperty(name="", min=128, default=1920)
    resolution_y: bpy.props.IntProperty(name="", min=128, default=1080)
    default_fps: bpy.props.IntProperty(name="", min=4, max=120, default=30)
    default_frame_start: bpy.props.IntProperty(name="", min=0, default=1001)
    thumbnail_size: bpy.props.IntProperty(
        name="",
        min=32,
        max=2048,
        default=240,
        subtype="PIXEL",
        description=(
            "Longest side of the render thumbnails (snapshot, file details). "
            "Existing ones are remade at the next snapshot export"
        ),
    )

    stuck_frame_factor: bpy.props.IntProperty(
        name="",
        min=0,
        max=100,
        default=5,
        description=(
            "A worker kills its render when the frame it's on takes this many "
            "times its usual time (5 min at least): the frames left go to the "
            "other machines. 0: never"
        ),
    )

    priority_switch_minutes: bpy.props.IntProperty(
        name="",
        min=0,
        max=600,
        default=3,
        description=(
            "A machine on a lower-priority render moves to a higher-priority "
            "job short of machines once its chunk is done -- unless its render "
            "has less than this many minutes left. 0: it always moves"
        ),
    )

    default_prerender_script: bpy.props.EnumProperty(
        items=_edited_project_scripts,
        name="",
        description="Pre-render script the Render dialog starts with",
    )  # type: ignore

    video_format: bpy.props.EnumProperty(
        name="",
        items=[
            ("mp4", "MP4 · H.264", "Smooth to scrub in an editing timeline, light, played as is by the page"),
            ("prores_lt", "MOV · ProRes 422 LT", "What editing software reads best (Resolve's free version on Linux "
             "reads no H.264); about 100 Mb/s in 1080p. The page plays a light mp4 copy, made in the same pass"),
            ("preset", "Preset file", "config/presets/ffmpeg_presets/default.json, as written there"),
        ],
        default="mp4",
        description="The video compiled from a render's frames, for the edit; the page always plays an mp4",
    )  # type: ignore

    chunk_size: bpy.props.IntProperty(
        name="",
        min=1,
        max=200,
        default=5,
        description=(
            "Frames per chunk: a worker claims this many frames at a time. "
            "Fixed for a render once it's sent out"
        ),
    )

    # Snapshot "Done" weights, see PROGRESS_WEIGHTS (lib/monitoring/snapshot.py).
    progress_wip: bpy.props.IntProperty(
        name="WIP",
        min=0,
        max=100,
        default=PROGRESS_WEIGHTS["wip"],
        subtype="PERCENTAGE",
        description="Share of a department counted as done while in progress",
    )
    progress_rework: bpy.props.IntProperty(
        name="Reworked",
        min=0,
        max=100,
        default=PROGRESS_WEIGHTS["rework"],
        subtype="PERCENTAGE",
        description="Share counted as done when validated, then reworked since",
    )
    progress_rtk: bpy.props.IntProperty(
        name="Open RTK",
        min=0,
        max=100,
        default=PROGRESS_WEIGHTS["rtk"],
        subtype="PERCENTAGE",
        description="Share counted as done when validated, with an open RTK",
    )
    # Snapshot schedule (snapshot.schedule, ISO dates in the config): typed
    # day first, see parse_day(). Both empty: no schedule.
    schedule_start: bpy.props.StringProperty(
        name="Start",
        description=(
            "First day of the project (DD/MM/YYYY). With the end date, the "
            "snapshot compares the progress with where it should be at an "
            "even pace. Empty: no schedule"
        ),
    )
    schedule_end: bpy.props.StringProperty(
        name="End", description="Last day of the project (DD/MM/YYYY)"
    )
    schedule_days_off: bpy.props.StringProperty(
        name="",
        description=(
            "Public holidays and days off, left out of the working days -- "
            "DD/MM/YYYY, comma-separated"
        ),
    )
    # Monday first: snapshot.schedule.worked_days holds ISO numbers, 1..7.
    schedule_worked_days: bpy.props.BoolVectorProperty(
        size=7,
        default=[d in WORK_WEEK for d in range(1, 8)],
        description="Days of the week the project works",
    )

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
        name="", default="modeling,texturing,rigging,tech",
        description="The departments, in order: a comma between them. Stages: a > b, c > d "
        "-- a department after a > waits for the ones before it and is to redo when "
        "they change; a comma, the same stage (in parallel). Commas only: no stages",
    )
    shots_departments: bpy.props.StringProperty(
        name="", default="layout,animation,lighting,render",
        description="The departments, in order: a comma between them. Stages: a > b, c > d "
        "-- a department after a > waits for the ones before it and is to redo when "
        "they change; a comma, the same stage (in parallel). Commas only: no stages",
    )
    team: bpy.props.StringProperty(
        name="",
        default="",
        description="The team's names, a comma between them: each one's user name picks "
        "from them (Preferences), departments are assigned to them (File details)",
    )
    validation_roles: bpy.props.StringProperty(
        name="",
        default="sup:1,prod:2",
        description="Who validates a done department, as role:level -- a "
        "higher level covers the lower ones, the same level is equivalent "
        "(e.g. sup:1,prod:2,real:2). Empty: none",
    )

    def _rows(self, box, rows) -> None:
        """Every Project settings line, one way: _settings_row() (its label
        a third, its "?"), then its cells on a grid of _SLOTS equal slots --
        a number one slot, a text field or a menu alone the whole line, a
        label (text[, icon[, slots]]) the rest of it by default, "" an
        empty slot, a function (of a layout) the whole line. The same slot
        the same width on every line, of every box."""
        for label, icon, *cells in rows:
            first = next((c for c in cells if isinstance(c, str) and c), "")
            self._cells(_settings_row(box, label, icon, first), cells)

    def _cells(self, layout, cells) -> None:
        """cells on _SLOTS slots (_rows()), split once each: a row would
        size them by their content."""
        def span(cell, left):
            if callable(cell):
                return left
            if isinstance(cell, tuple):
                return cell[2] if len(cell) > 2 else left
            if cell and self.bl_rna.properties[cell].type in ("STRING", "ENUM") and len(cells) == 1:
                return left
            return 1

        left = _SLOTS
        for n, cell in enumerate(cells):
            width = min(span(cell, left), left)
            last = n == len(cells) - 1 and width == left
            if last:
                target = layout.row(align=True)
            else:
                split = layout.split(factor=width / left, align=True)
                target, layout = split.row(align=True), split
            left -= width
            if callable(cell):
                cell(target)
            elif isinstance(cell, tuple):
                target.label(text=cell[0], icon=cell[1] if len(cell) > 1 else "NONE")
            elif cell:
                target.prop(self, cell)
            else:
                target.label(text="")
            if last:
                break
        else:
            layout.label(text="")  # the slots left: blank, the grid kept

    def draw_settings(self, layout):
        """Left: the project and how it names things. Right: what's tracked
        (snapshot, validation, schedule) and the farm. Returns the right
        column -- the window adds its Maintenance there."""
        layout.label(text=f"Editing: {self.project_name}", icon="FILE_TEXT")
        layout.separator()
        # Two columns side by side: one ran past the screen's height.
        columns = layout.split(factor=0.5)
        left = columns.column()
        right = columns.column()

        # Read-only, then the Blender version: on the same grid.
        def locked(value):
            def draw(layout):
                layout.active = False
                layout.label(text=value, icon="LOCKED")

            return draw

        self._rows(left.box().column(align=False), [
            ("NAME", "PINNED", locked(self.project_name)),
            ("PATH", "BLANK1", locked(self.project_path_selected)),
            ("BLENDER", "BLENDER", "project_bl_version"),
        ])

        # Resolution / FPS
        left.separator()
        self._rows(left.box().column(align=False), [
            ("RESOLUTION", "RESTRICT_VIEW_OFF", "resolution_x", "resolution_y"),
            ("FRAME RATE", "PREVIEW_RANGE", "default_fps", ""),
            ("SHOT START", "DECORATE_KEYFRAME", "default_frame_start", ""),
        ])

        # Naming
        left.separator()
        box = left.box().column(align=False)
        self._rows(box, [
            ("", "NONE", ("PREFIX", "SYNTAX_OFF", 1), ("DIGITS", "SORTBYEXT", 1)),
            ("SEQUENCE", "LAYER_ACTIVE", "sequence_prefix", "sequence_digits"),
            ("SHOT", "LAYER_USED", "shot_prefix", "shot_digits"),
            ("VERSION", "CHECKMARK", "version_prefix", "version_digits"),
            ("FRAME", "KEYFRAME_HLT", "frame_prefix", "frame_digits"),
        ])
        _example(
            box,
            f"e.g.: {self.sequence_prefix}{self._rdm(self.sequence_digits)}"
            f"_{self.shot_prefix}{self._rdm(self.shot_digits)}"
            f"_{self.version_prefix}{self._rdm(self.version_digits)}.blend",
        )

        # Structure: folders, prefixes, tags, departments
        left.separator()
        box = left.box().column(align=False)
        self._rows(box, [
            ("FOLDERS", "OUTLINER", "project_folders"),
            ("ASSET PREFIX", "MESH_MONKEY", "asset_prefixes"),
            ("LIBRARY PREFIX", "TOOL_SETTINGS", "library_prefixes"),
            ("VERSION TAGS", "BOOKMARKS", "tags"),
            ("ASSETS DEPARTMENTS", "COPY_ID", "assets_departments"),
            ("SHOTS DEPARTMENTS", "COPY_ID", "shots_departments"),
        ])
        all_pf = self.asset_prefixes + "," + self.library_prefixes
        _example(
            box,
            f"e.g.: {self._rdm_from(all_pf)}_asset-name"
            f"_{self.version_prefix}{self._rdm(self.version_digits)}.blend",
        )

        # Tracking: thumbnails, snapshot Done (validated 100 %, not started
        # 0 %), who validates, the schedule
        box = right.box().column(align=False)
        self._rows(box, [
            ("THUMBNAILS", "IMAGE_DATA", "thumbnail_size", ""),
            ("SNAPSHOT DONE", "SORTSIZE", "progress_wip", "progress_rework", "progress_rtk"),
            ("VALIDATION ROLES", "SOLO_ON", "validation_roles"),
            ("TEAM", "COMMUNITY", "team"),
        ])
        box.separator(type="LINE")
        self._rows(box, [
            ("SCHEDULE", "TIME", "schedule_start", "schedule_end"),
            ("DAYS OFF", "BLANK1", "schedule_days_off"),
        ])
        def week(layout):
            for i, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
                layout.prop(self, "schedule_worked_days", index=i, text=name, toggle=True)

        self._rows(box, [("WORKED DAYS", "BLANK1", week)])

        # Farm
        right.separator()
        farm = right.box().column(align=False)
        self._rows(farm, [
            ("VIDEO", "FILE_MOVIE", "video_format"),
            ("CHUNK SIZE", "RENDER_RESULT", "chunk_size"),
            ("PRE-RENDER", "SCRIPT", "default_prerender_script"),
            ("STUCK FRAME", "ERROR", "stuck_frame_factor",
             ("x usual time: kill" if self.stuck_frame_factor else "0 = never kill",)),
            ("PRIORITY SWITCH", "SORT_DESC", "priority_switch_minutes",
             ("min left: stays" if self.priority_switch_minutes else "0 = always switch",)),
        ])
        self._draw_presets(farm)
        return right

    def _departments(self) -> list[str]:
        """The departments as typed in the fields, not yet saved."""
        return [*parse_departments(self.shots_departments)[0], *parse_departments(self.assets_departments)[0]]

    def _draw_presets(self, box) -> None:
        """The render presets whose name gives no department, and Rename
        preset -- the name is what gives a render its department."""
        root = self.project_path_selected
        if not root:
            return
        names = [
            Path(e.name).stem
            for e in cached_scandir(Path(root) / "config" / "presets")
            if e.name.endswith(".py") and e.name != "asset_file_preset.py"
        ]
        loose = sorted(n for n in names if not preset_department(n, self._departments()))
        row = box.row()
        if loose:
            warn = row.row()
            warn.alert = True
            warn.label(text=f"No department: {', '.join(loose)}", icon="ERROR")
        else:
            row.label(text="")
        op = row.operator("m_pipeline.rename_preset", text="Rename preset…", icon="GREASEPENCIL")
        op.project_root = root

    def load(self, context) -> None:
        """The fields from project_path_selected's config. Raises
        PipelineError."""
        config = read_project_config(self.project_path_selected)
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
        self.thumbnail_size = thumbnail_size(config)
        weights = progress_weights(config)
        self.progress_wip = weights["wip"]
        self.progress_rework = weights["rework"]
        self.progress_rtk = weights["rtk"]
        schedule = project_schedule(config) or {}
        self.schedule_start = self._days([schedule["start"]]) if schedule else ""
        self.schedule_end = self._days([schedule["end"]]) if schedule else ""
        self.schedule_days_off = self._days(schedule.get("days_off", []))
        worked = schedule.get("worked_days", WORK_WEEK)
        self.schedule_worked_days = [d in worked for d in range(1, 8)]
        self.default_prerender_script = default_pre_render_script(
            config, _edited_project_scripts(self, context)
        )
        self.chunk_size = max(
            1, int((config.get("farm") or {}).get("chunk_size", 5) or 5)
        )
        fmt = (config.get("video") or {}).get("format", "preset")
        self.video_format = fmt if fmt in ("mp4", "prores_lt", "preset") else "preset"
        stuck = (config.get("farm") or {}).get("stuck_frame_factor", 5)
        self.stuck_frame_factor = max(0, int(5 if stuck is None else stuck))
        switch = (config.get("farm") or {}).get("priority_switch_minutes", 3)
        self.priority_switch_minutes = max(0, int(3 if switch is None else switch))

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
        # One field each: the list and its stages (lib/monitoring/status.py).
        stages = config.get("department_stages") or {}
        self.assets_departments = departments_text(
            config.get("assets_departments", DEFAULT_ASSET_DEPARTMENTS), stages.get("assets")
        )
        self.team = ", ".join(project_team(config))
        self.shots_departments = departments_text(
            config.get("shots_departments", DEFAULT_SHOT_DEPARTMENTS), stages.get("shots")
        )
        self.validation_roles = ",".join(
            f"{r['name']}:{r['level']}" for r in validation_roles(config)
        )

    def save(self, context) -> list[tuple[str, str]]:
        """The fields written to the config: what to report, [(level,
        message)]."""
        try:
            config = read_project_config(self.project_path_selected)
        except PipelineError as e:
            log("WARNING", "edit_project", f"{e.message} -- writing a fresh config.")
            config = {}

        # A date it can't read leaves the schedule as it was, not the rest.
        schedule_error = None
        try:
            schedule = self._schedule()
        except PipelineError as e:
            schedule = json_get(config, "snapshot.schedule", {})
            schedule_error = e.message

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
                "assets_departments": parse_departments(self.assets_departments)[0],
                "shots_departments": parse_departments(self.shots_departments)[0],
                "validation_roles": self._roles_from_csv(self.validation_roles),
                "team": project_team({"team": self._csv_to_list(self.team)}),
                "department_stages": {
                    "assets": parse_departments(self.assets_departments)[1],
                    "shots": parse_departments(self.shots_departments)[1],
                },
                # "farm": only stuck_frame_factor, priority_switch_minutes,
                # chunk_size and default_prerender_script are edited here, the
                # rest stays as read from the loaded config.
                "farm": (config.get("farm") or {})
                | {
                    "stuck_frame_factor": self.stuck_frame_factor,
                    "priority_switch_minutes": self.priority_switch_minutes,
                    "chunk_size": self.chunk_size,
                    "default_prerender_script": (
                        ""
                        if self.default_prerender_script == _NO_SCRIPT
                        else self.default_prerender_script
                    ),
                },
                "thumbnails": (config.get("thumbnails") or {})
                | {"size": self.thumbnail_size},
                "video": (config.get("video") or {}) | {"format": self.video_format},
                "snapshot": (config.get("snapshot") or {})
                | {
                    "progress": {
                        "wip": self.progress_wip,
                        "rework": self.progress_rework,
                        "rtk": self.progress_rtk,
                    },
                    "schedule": schedule,
                },
            }
        )
        try:
            config_file = get_config_filepath(self.project_path_selected)
            config_file.parent.mkdir(parents=True, exist_ok=True)
            newer = formats.too_new(config_file, config)
            if newer is not None:
                return [("ERROR", f"This project's settings were written by a newer Minimalist Pipeline ({newer}): update the addon first.")]
            write_json_atomic(config_file, config)
            ConfigCache.invalidate()
        except Exception as e:
            return [("ERROR", f"Failed to save config: {e}")]

        out = []
        # A department with no render preset yet gets its default one.
        made = install_department_presets(
            [*config["shots_departments"], *config["assets_departments"]],
            Path(self.project_path_selected) / "config" / "presets",
        )
        if made:
            out.append(("INFO", f"Render presets made: {', '.join(made)}"))
        try:
            save_project_data(addon_pref(context))
        except PipelineError as e:
            log(e.level, "edit_project", e.message)
            out.append(("WARNING", f"Config saved, but not backed up: {e}"))

        if schedule_error:
            out.append(("WARNING", f"Config saved, schedule left as it was: {schedule_error}"))
        else:
            out.append(("INFO", f"Config saved for {self.project_name}."))
        return out

    def _schedule(self) -> dict:
        """The schedule fields as snapshot.schedule: ISO dates, {} when start
        and end are both empty. Raises PipelineError on a date it can't read,
        only one of start/end, an end before the start, or no worked day."""
        start, end = self.schedule_start.strip(), self.schedule_end.strip()
        if not start and not end:
            return {}
        if not start or not end:
            raise PipelineError("a schedule needs both a start and an end date.")
        start, end = parse_day(start), parse_day(end)
        if end < start:
            raise PipelineError("the end date is before the start date.")
        days_off = sorted(
            {parse_day(d) for d in self.schedule_days_off.split(",") if d.strip()}
        )
        worked = [i + 1 for i, on in enumerate(self.schedule_worked_days) if on]
        if not worked:
            raise PipelineError("no day of the week is worked.")
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days_off": [d.isoformat() for d in days_off],
            "worked_days": worked,
        }

    @staticmethod
    def _days(dates) -> str:
        """Dates as typed in the schedule fields: DD/MM/YYYY, comma-separated."""
        return ", ".join(f"{d:%d/%m/%Y}" for d in sorted(dates))

    @classmethod
    def _roles_from_csv(cls, csv_str) -> list[dict]:
        """ "sup:1,prod:2" -> [{"name": "sup", "level": 1}, ...]; a role
        without a level gets its position (1, 2...)."""
        roles = []
        for i, item in enumerate(cls._csv_to_list(csv_str)):
            name, _, level = item.partition(":")
            try:
                level = int(level) if level.strip() else i + 1
            except ValueError:
                level = i + 1
            if name.strip():
                roles.append({"name": name.strip().lower(), "level": level})
        return validation_roles({"validation_roles": roles})

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


_SETTINGS_PROPS = dict(ProjectSettings.__annotations__)


class PIPELINE_PG_project_settings(ProjectSettings, bpy.types.PropertyGroup):
    """Project settings as the window edits them (WindowManager
    .pipeline_project_settings): loaded when it opens, written by Save."""

    __annotations__ = dict(_SETTINGS_PROPS)


class M_PIPELINE_OT_edit_project(ProjectSettings, bpy.types.Operator):
    """Edit project configuration."""

    bl_idname = "m_pipeline.edit_project"
    bl_label = ""
    bl_description = "Edit project settings."

    __annotations__ = dict(_SETTINGS_PROPS)

    def invoke(self, context, event):
        # A window, like the welcome: it stays while edited. The dialog only
        # if Blender couldn't open one.
        from ..lib.monitoring.windows import (
            bring_monitoring_to_front,
            monitoring_windows,
            open_monitoring_window,
        )

        settings = context.window_manager.pipeline_project_settings
        open_one = monitoring_windows("settings")
        if open_one and settings.project_path_selected == self.project_path_selected:
            # Already open on that project: its edits kept, brought forward.
            if bring_monitoring_to_front(context, "settings"):
                return {"FINISHED"}
        settings.project_path_selected = self.project_path_selected
        try:
            settings.load(context)
        except PipelineError as e:
            return report_error(self, "edit_project", e)
        if open_one:
            from ..lib.monitoring.windows import redraw_monitoring

            redraw_monitoring("settings")
            bring_monitoring_to_front(context, "settings")
            return {"FINISHED"}
        if open_monitoring_window(context, "settings", size=(0.6, 0.8)):
            return {"FINISHED"}
        try:
            self.load(context)
        except PipelineError as e:
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=900)

    def draw(self, context):
        self.draw_settings(self.layout)

    def execute(self, context):
        out = self.save(context)
        for level, message in out:
            self.report({level}, message)
        return {"CANCELLED"} if out and out[0][0] == "ERROR" else {"FINISHED"}


_rename_items: list = []


def _rename_preset_items(self, context):
    root = Path(self.project_root) if self.project_root else None
    names = sorted(
        Path(e.name).stem
        for e in (cached_scandir(root / "config" / "presets") if root else [])
        if e.name.endswith(".py") and e.name != "asset_file_preset.py"
    )
    return _stable_enum_items(_rename_items, [(n, n, "") for n in names] or [("", "No render preset", "")])


class M_PIPELINE_OT_rename_preset(bpy.types.Operator):
    """Rename a render preset, and everything citing it: its name gives its
    renders' department."""

    bl_idname = "m_pipeline.rename_preset"
    bl_label = "Rename preset"
    bl_description = (
        "Rename a render preset and every place citing it -- the default "
        "pre-render script, the renders' history, the farm's paces. Its name "
        "gives its renders' department: lighting_hd, lighting's"
    )
    bl_options = {"INTERNAL"}

    project_root: bpy.props.StringProperty(options={"HIDDEN"})
    old: bpy.props.EnumProperty(name="Preset", items=_rename_preset_items)
    new: bpy.props.StringProperty(name="New name")
    old_renders: bpy.props.BoolProperty(
        name="Its past renders too",
        default=False,
        description=(
            "Its renders made so far, with no department, get the one the new "
            "name gives -- right only if this preset always served that department"
        ),
    )

    def _departments(self, context) -> list[str]:
        settings = context.window_manager.pipeline_project_settings
        if settings.project_path_selected == self.project_root:
            return settings._departments()
        config = read_project_config(self.project_root)
        return [*(config.get("shots_departments") or []), *(config.get("assets_departments") or [])]

    def invoke(self, context, event):
        if not self.project_root:
            return {"CANCELLED"}
        # The first one giving no department, to start with: the reason to rename.
        loose = presets_without_department(Path(self.project_root) / "config" / "presets", self._departments(context))
        if loose:
            self.old = loose[0]
        self.new = self.old
        return context.window_manager.invoke_props_dialog(self, width=420, confirm_text="Rename")

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "old")
        col.prop(self, "new")
        deps = self._departments(context)
        was, dep = preset_department(self.old, deps), preset_department(self.new, deps)
        info = col.column(align=True)
        info.active = False
        info.label(text=f"Its renders: {was or 'no department'}  ->  {dep or 'no department'}", icon="RENDER_RESULT")
        info.label(text="A name starting with a department gives it: lighting_hd, lighting's.", icon="BLANK1")
        sub = col.row()
        sub.enabled = bool(dep) and dep != was
        sub.prop(self, "old_renders", text=f"Its past renders are {dep or 'a department'}'s too")
        tip = col.column(align=True)
        tip.active = False
        tip.scale_y = 0.8
        tip.label(text="Updated too: the default pre-render script, every render's", icon="INFO")
        tip.label(text="history, the farm's paces. Refused while the farm has jobs.", icon="BLANK1")

    def execute(self, context):
        new = self.new.strip()
        problem = preset_rename_problem(self.project_root, self.old, new)
        if problem:
            self.report({"WARNING"}, problem)
            return {"CANCELLED"}
        try:
            out = rename_preset(self.project_root, self.old, new, self._departments(context), self.old_renders)
        except (PipelineError, OSError) as e:
            self.report({"ERROR"}, f"Rename preset: {getattr(e, 'message', e)}")
            return {"CANCELLED"}
        settings = context.window_manager.pipeline_project_settings
        if settings.project_path_selected == self.project_root and out["default"]:
            # Its picker's items re-read: the default follows the new name.
            try:
                settings.default_prerender_script = new
            except TypeError:
                pass
        ConfigCache.invalidate()
        self.report({"INFO"}, f"{self.old} renamed {new}: {out['renders']} render(s) in its history updated.")
        return {"FINISHED"}


class M_PIPELINE_OT_save_project_settings(bpy.types.Operator):
    """Write the settings window's fields to the project's config"""

    bl_idname = "m_pipeline.save_project_settings"
    bl_label = "Save"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        out = context.window_manager.pipeline_project_settings.save(context)
        for level, message in out:
            self.report({level}, message)
        return {"CANCELLED"} if out and out[0][0] == "ERROR" else {"FINISHED"}
