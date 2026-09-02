"""Shot management operators: create, branch."""

from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    PipelineError,
    copy_entries,
    create_shot_file,
    format_shot_segment,
    get_active_project_root,
    get_departments_required,
    json_get,
    lines_budget,
    locked_json,
    log,
    parse_filename,
    path_reachable,
    region_char_budget,
    shot_department_items,
    shots_in_segment,
    text_to_lines,
)


# ---------------------------------------------------------------------------
# Create Shots
# ---------------------------------------------------------------------------
class PipelineShotItem(bpy.types.PropertyGroup):
    """A shot."""

    shot_number: bpy.props.IntProperty(name="", default=10, min=0, step=10)
    start_frame: bpy.props.IntProperty(name="", min=0)


class PIPELINE_OT_add_multishot_item(bpy.types.Operator):
    """"""

    bl_idname = "pipeline.add_multishot_item"
    bl_label = "Add"

    shot_number: bpy.props.IntProperty(name="", default=10)
    start_frame: bpy.props.IntProperty(name="", default=1001)

    def execute(self, context):
        shots = context.window_manager.shots_list_creation
        new_item = shots.add()
        new_item.shot_number = self.shot_number
        new_item.start_frame = self.start_frame
        return {"FINISHED"}


class PIPELINE_OT_remove_multishot_item(bpy.types.Operator):
    """"""

    bl_idname = "pipeline.remove_multishot_item"
    bl_label = "Remove line"

    index: bpy.props.IntProperty(name="")

    def execute(self, context):
        shots = context.window_manager.shots_list_creation
        shots.remove(self.index)
        return {"FINISHED"}


def _draw_shot_list(layout, context, op, config):
    """Shared shot-list editor (rows + end frame). op needs its own
    "end_frame" IntProperty. Returns the shots collection."""
    shots = context.window_manager.shots_list_creation
    if shots:
        tabl = layout.split(factor=0.25, align=True)
        col = tabl.column(align=True)
        col.box().label(text="Shot number", icon="CAMERA_DATA")
        col.box().label(text="Timeline", icon="ACTION")
        tabl = tabl.row(align=True)

        for idx, s in enumerate(shots):
            col = tabl.column(align=True)
            row_number = col.box().row(align=False)
            row_number.prop(s, "shot_number", emboss=False, text=" ")
            btn = row_number.row(align=True)
            btn.scale_x = 0.5
            btn.operator(
                "pipeline.remove_multishot_item",
                text="",
                icon="REMOVE",
                emboss=False,
            ).index = idx
            col.box().prop(s, "start_frame", emboss=False, text=" ")
        last = shots[-1]
        col = tabl.column(align=True)
        btn_row = col.box().row()
        btn_row.active = False
        btn_row.alignment = "RIGHT"
        add_op = btn_row.operator(
            "pipeline.add_multishot_item", emboss=False, icon="ADD", text=""
        )
        add_op.shot_number = last.shot_number
        add_op.start_frame = last.start_frame
        col.box().prop(op, "end_frame", emboss=False, text="END")
    else:
        layout.operator(
            "pipeline.add_multishot_item", text="Add shot(s) number"
        ).start_frame = json_get(config, "default_frame_start", 1001)
    return shots


def _draw_block_warning(layout, context, shots):
    """Reminder of what a block is for, shown once there's an actual block
    (2+ shots)."""
    if len(shots) <= 1:
        return
    text = (
        f"A block is for cuts sharing DECOR and LIGHTING, worked by ONE "
        f"person. This locks all {len(shots)} shots together as a single "
        f"unit. Different needs (fx on one, separate lighting on another)? "
        f"Use separate shots instead."
    )
    # PIPELINE_OT_create_shot draws this inside its own invoke_props_dialog
    # (width=500) -- context.region there isn't that dialog's own region,
    # so region_char_budget(context) would size off a panel-sized guess.
    # Pass the dialog's own real width instead -- see region_char_budget()'s
    # docstring / POPUP_WIDTH_SCALE in lib/core.py for why it still needs
    # correcting.
    layout = layout.box().column(align=True)
    layout.alert = True
    layout.enabled = False
    layout.scale_y = 0.65
    text_to_lines(
        layout,
        text,
        max_width=region_char_budget(context, width_px=500),
        max_lines=lines_budget(text),
        icon="INFO",
    )


def _draw_timeline_warnings(layout, shots, end_frame):
    """Ordering/sign sanity checks -- warnings, never blockers."""
    if not shots:
        return
    numbers = [s.shot_number for s in shots]
    timeline = [s.start_frame for s in shots] + [end_frame]
    warning = layout.column(align=True)
    warning.alert = True
    if numbers != sorted(set(numbers)) or timeline != sorted(set(timeline)):
        warning.box().label(
            text="Inconsistent timeline ! Shot numbers or start frames are not ordered.",
            icon="ERROR",
        )
    if min(numbers) < 0 or min(timeline) < 0:
        warning.box().label(
            text="Invalid numbers! Shot numbers or start frames can't be negative."
        )


def _draw_naming_preview(layout, sequence_number, shots, config):
    """File/folder name preview. Returns (sq, sh), or None if config is missing."""
    naming = config.get("naming", {})
    if not naming:
        # draw() must never raise -- Blender gives it no way to report an
        # error, an uncaught exception here would break the popup.
        layout.separator()
        layout.label(text="Project config is missing or invalid.", icon="ERROR")
        return None

    sq = f"{naming['sequence']['prefix']}{sequence_number:0{naming['sequence']['digits']}d}"
    segment = format_shot_segment([s.shot_number for s in shots], config)
    sh = f"{naming['shot']['prefix']}{segment}"
    v = f"{naming['version']['prefix']}{1:0{naming['version']['digits']}d}"
    full_name = f"{sq}_{sh}_{v}.blend"

    layout.separator()
    col = layout.column()
    col.active = False
    col.scale_y = 0.75
    col.label(text=f"File: {full_name}", icon="FILE")
    col.label(text=f"In: shots/{sq}/{sh}/", icon="FILE_FOLDER")
    return sq, sh


class PIPELINE_OT_create_shot(bpy.types.Operator):
    """Create a new shot with proper naming and folder placement."""

    bl_idname = "pipeline.create_shot"
    bl_label = "New shot"
    bl_description = "Create a new versioned shot in the active project."

    sequence_number: bpy.props.IntProperty(name="Sequence", default=10, min=0, step=10)
    end_frame: bpy.props.IntProperty(name="End frame", default=10, min=0, step=1)
    shot_description: bpy.props.StringProperty(
        name="Description",
        description="What this shot is, shown in its tracking panel.",
        default="",
    )
    create_clean: bpy.props.BoolProperty(
        name="Start with a new clean scene", default=False
    )
    shot_departments: bpy.props.EnumProperty(
        items=shot_department_items,
        options={"ENUM_FLAG"},
        name="Departments",
        default=0,
    )

    def draw(self, context):
        layout = self.layout.column(align=True)
        config = ConfigCache.get()

        row = layout.split(factor=0.25, align=True)
        row.box().label(text="Sequence number", icon="SEQUENCE")
        row.box().prop(self, "sequence_number", emboss=False, text=" ")
        shots = _draw_shot_list(layout, context, self, config)
        _draw_block_warning(layout, context, shots)
        layout.separator()

        row = layout.split(factor=0.25, align=True)
        row.box().label(text="File description", icon="FILE_BLEND")
        row.box().textbox(self, "shot_description")
        row = layout.split(factor=0.25, align=True)
        row.box().label(text="Start w/ clean file", icon="FILE_BACKUP")
        row.box().prop(self, "create_clean", text="")
        row = layout.split(factor=0.25, align=True)
        row.box().label(text="Departments", icon="COPY_ID")
        row.box().prop_menu_enum(self, "shot_departments")

        layout.separator(factor=3)
        _draw_timeline_warnings(layout, shots, self.end_frame)
        _draw_naming_preview(layout, self.sequence_number, shots, config)

    def invoke(self, context, event):
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        config = ConfigCache.get()
        deps = config.get(
            "shots_departments", ["layout", "animation", "lighting", "render"]
        )
        self.shot_departments = {d for d in deps}
        default_start = json_get(config, "default_frame_start", 1001)
        self.end_frame = default_start

        # shots_list_creation is a WindowManager collection -- shared and
        # never cleared on its own, so without this it either starts empty
        # (nothing to click but a bare "Add" button, easy to miss and OK
        # straight into a shot with no number and no camera/marker at all --
        # see create_shot_file()'s own guard against that) or keeps
        # whatever was left over from the last shot created. Reset it to one
        # sensible default row every time, same as PIPELINE_OT_branch_shot's
        # own invoke() does.
        shots = context.window_manager.shots_list_creation
        shots.clear()
        item = shots.add()
        item.start_frame = default_start

        return context.window_manager.invoke_props_dialog(self, width=500)

    def execute(self, context):
        project_root = get_active_project_root()

        if not path_reachable(project_root):
            self.report({"ERROR"}, "Project path does not exist or is unreachable.")
            return {"CANCELLED"}

        shots = context.window_manager.shots_list_creation
        if not shots:
            self.report(
                {"ERROR"},
                "No shot added. Click Add to add at least one shot before creating.",
            )
            return {"CANCELLED"}

        try:
            # create_clean starts from a blank scene; otherwise the file is
            # created from whatever is currently in this session (the
            # artist's own WIP content) -- create_shot_file() below just
            # saves bpy.data as-is, it never resets the scene itself.
            if self.create_clean:
                bpy.ops.wm.read_homefile(use_empty=True)
            elif bpy.data.filepath and bpy.data.is_dirty:
                bpy.ops.wm.save_mainfile()

            dest_path = create_shot_file(
                project_root,
                sequence_number=self.sequence_number,
                shot_number=[s.shot_number for s in shots],
                timeline=[s.start_frame for s in shots] + [self.end_frame],
                departments=list(self.shot_departments),
                description=self.shot_description,
            )
        except PipelineError as e:
            log(e.level, "create_shot", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}

        log("SUCCESS", "create_shot", f"Created {dest_path.name}")
        self.report({"INFO"}, f"Shot created: {dest_path.name} ({dest_path.parent})")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Branch
# ---------------------------------------------------------------------------
class PIPELINE_OT_branch_shot(bpy.types.Operator):
    """Archive this block's composition and create a new one with a
    different shot enumeration."""

    bl_idname = "pipeline.branch_shot"
    bl_label = "Branch block"
    bl_description = (
        "Archive this block and create a new one with a different shot enumeration."
    )

    filepath: bpy.props.StringProperty(default="")
    end_frame: bpy.props.IntProperty(name="End frame", default=10, min=0, step=1)
    shot_description: bpy.props.StringProperty(
        name="Description",
        description="What this shot is, shown in its tracking panel.",
        default="",
    )
    create_clean: bpy.props.BoolProperty(
        name="Start with a new clean scene", default=False
    )
    shot_departments: bpy.props.EnumProperty(
        items=shot_department_items,
        options={"ENUM_FLAG"},
        name="Departments",
        default=0,
    )

    def draw(self, context):
        layout = self.layout
        config = ConfigCache.get()
        layout.label(text="Branch block", icon="UV_SYNC_SELECT")
        col = layout.column()
        col.active = False
        col.scale_y = 0.6
        col.label(text=f"Archiving: {Path(self.filepath).name}", icon="INFO")
        layout.separator()

        shots = _draw_shot_list(layout, context, self, config)
        _draw_block_warning(layout, context, shots)

        layout.textbox(self, "shot_description")
        layout.prop(self, "create_clean")
        layout.prop_menu_enum(self, "shot_departments")

        _draw_timeline_warnings(layout, shots, self.end_frame)
        parsed = parse_filename(Path(self.filepath).name)
        if parsed:
            _draw_naming_preview(layout, int(parsed["sequence"]), shots, config)

    def invoke(self, context, event):
        self.filepath = self.filepath or bpy.data.filepath
        if not self.filepath:
            self.report({"ERROR"}, "No block file to branch from.")
            return {"CANCELLED"}
        parsed = parse_filename(Path(self.filepath).name)
        if not parsed or not parsed.get("shot"):
            self.report({"ERROR"}, "Not a shot file.")
            return {"CANCELLED"}
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}

        config = ConfigCache.get()
        required = get_departments_required(Path(self.filepath)) or config.get(
            "shots_departments", ["layout", "animation", "lighting", "render"]
        )
        self.shot_departments = {d for d in required}
        default_start = json_get(config, "default_frame_start", 1001)
        self.end_frame = default_start

        # Seed the shot list from the old block's own enumeration.
        shots = context.window_manager.shots_list_creation
        shots.clear()
        for n in shots_in_segment(parsed["shot"]):
            item = shots.add()
            item.shot_number = n
            item.start_frame = default_start

        return context.window_manager.invoke_props_dialog(self, width=380)

    def execute(self, context):
        project_root = get_active_project_root()
        old_path = Path(self.filepath)
        parsed = parse_filename(old_path.name)
        if not parsed:
            self.report({"ERROR"}, "Not a shot file.")
            return {"CANCELLED"}

        try:
            if self.create_clean:
                bpy.ops.wm.read_homefile(use_empty=True)
            elif bpy.data.filepath and bpy.data.is_dirty:
                bpy.ops.wm.save_mainfile()

            shots = context.window_manager.shots_list_creation
            # Create the new file before archiving the old one, so a
            # failure here never leaves a block archived with no successor.
            dest_path = create_shot_file(
                project_root,
                sequence_number=int(parsed["sequence"]),
                shot_number=[s.shot_number for s in shots],
                timeline=[s.start_frame for s in shots] + [self.end_frame],
                departments=list(self.shot_departments),
                description=self.shot_description,
                start_version=int(parsed["number"]) + 1,
            )
            # Flag only -- name/path untouched.
            old_tracking = old_path.parent / ".pipeline" / "tracking.json"
            with locked_json(old_tracking) as box:
                data = box["data"] or {}
                if not data:
                    raise PipelineError(f"Tracking file not found: {old_tracking}")
                data["archived"] = True
                box["action"] = "to_write"

            copy_entries(old_path, dest_path)
        except PipelineError as e:
            log(e.level, "branch_shot", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}

        log("SUCCESS", "branch_shot", f"{old_path.name} -> {dest_path.name}")
        self.report(
            {"INFO"}, f"Branched: {old_path.name} archived, created {dest_path.name}"
        )
        return {"FINISHED"}
