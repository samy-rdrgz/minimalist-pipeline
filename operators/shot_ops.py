"""Shot management operators: create, branch."""

from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    PipelineError,
    active_shot_owners,
    archive_folder,
    copy_entries,
    create_shot_file,
    derive_shot_subranges,
    format_shot_segment,
    get_active_project_root,
    get_departments_required,
    json_get,
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


def _draw_shot_list(layout, context, op, config, TITLE_WIDTH):
    """Shared shot-list editor (rows + end frame). op needs its own
    "end_frame" IntProperty. Returns the shots collection."""
    shots = context.window_manager.shots_list_creation

    tabl = layout.split(factor=TITLE_WIDTH)
    tabl.label(text="Shot(s)", icon="CAMERA_DATA")
    tabl = tabl.column(align=True)
    if shots:
        row = tabl.row(align=True).box().row(align=True)
        row.scale_y = 0.55
        row.label(text="Number")
        row.label(text="Timeline")

        cols = tabl.row(align=True)
        number_col = cols.column(align=True)
        timeline_col = cols.column(align=True)

        for idx, s in enumerate(shots):
            number_col.prop(s, "shot_number", text=" ")
            timeline_col.prop(s, "start_frame", text=" " if idx != 0 else "Start")

        timeline_col.prop(op, "end_frame", text="End")

        last = shots[-1]
        btns_row = number_col.row(align=True)
        btns_row.active = False

        btn_row = btns_row.row(align=True)
        btn_row.enabled = len(shots) > 1
        btn_row.operator(
            "pipeline.remove_multishot_item", text="", icon="REMOVE"
        ).index = len(shots) - 1

        add_op = btns_row.operator("pipeline.add_multishot_item", icon="ADD", text="")
        add_op.shot_number = last.shot_number + 10
        add_op.start_frame = last.start_frame + 20

    else:
        tabl.operator(
            "pipeline.add_multishot_item", text="Add shot(s) number"
        ).start_frame = json_get(config, "default_frame_start", 1001)

    return shots


def _draw_block_warning(layout, context, shots):
    """Reminder of what a block is for, shown once there's an actual block
    (2+ shots)."""
    if len(shots) <= 1:
        layout.separator(type="LINE", factor=3)
        return
    text = (
        f"A block is ONE continuous action (like a character's move) played across "
        f"several cameras (not just successive shots in the same decor)."
        f"\nIt's worked by ONE person at a time and will lock these {len(shots)} "
        f"shots together.\nNot one continuous action? Use separate shots "
        f"instead."
    )
    # PIPELINE_OT_create_shot draws this inside its own invoke_props_dialog
    # (width=500) -- context.region there isn't that dialog's own region,
    # so region_char_budget(context) would size off a panel-sized guess.
    # Pass the dialog's own real width instead -- see region_char_budget()'s
    # docstring / POPUP_WIDTH_SCALE in lib/core.py for why it still needs
    # correcting.
    layout.separator()
    box = layout.box().column(align=True)
    box.alert = True
    box.enabled = False
    box.scale_y = 0.65
    for idx, t in enumerate(text.split("\n")):
        text_to_lines(
            box,
            t,
            max_width=region_char_budget(context, width_px=320),
            max_lines=6,
            icon="INFO" if idx == 0 else "NONE",
        )
    layout.separator(factor=2)


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

    preview_col = layout.column(align=True)
    preview_col.active = False
    preview_col.scale_y = 0.65
    preview_col.label(text=f"File: {full_name}", icon="FILE_BLEND")
    preview_col.label(text=f"In: shots/{sq}/{sh}/", icon="BLANK1")

    # Worst-case sidecar path (.stablemeta carries _meta_stem()'s "-stable"
    # tag, longer than .wipmeta) against Windows' 260-char MAX_PATH -- only
    # this machine's own mount, not a guarantee for every artist's (see
    # NOTES.md §6). Shown only once it's actually worth a look.
    if len(shots) > 2:
        path = (
            get_active_project_root()
            / "shots"
            / sq
            / sh
            / ".pipeline"
            / f"{v}-stable.stablemeta.tmp"
        )
        length = len(str(path))
        factor = length / 260
        if factor > 0.6:
            layout.separator()
            layout.progress(
                text=f"Path length on this machine: {length} / 260",
                factor=min(factor, 1.0),
            )

    return sq, sh


def _classify_shot_conflicts(project_root, sq, shots, config, exclude_dir=None):
    """Split shots' numbers against other active files in sq into
    (blocking, warnings) dicts of {shot_number: owner_folder}. blocking =
    a mono-shot duplicating another active mono-shot outright -- no
    legitimate reason for two files to claim the same lone shot. Anything
    else (a block absorbing a used number, or the reverse) is a warning."""
    owners = active_shot_owners(project_root, sq, config)
    shot_prefix = json_get(config, "naming.shot.prefix", "sh")
    mono = len(shots) == 1
    blocking, warnings = {}, {}
    for s in shots:
        owner = owners.get(s.shot_number)
        if owner is None or owner == exclude_dir:
            continue
        try:
            owner_mono = len(shots_in_segment(owner.name[len(shot_prefix) :])) == 1
        except ValueError:
            owner_mono = False
        (blocking if mono and owner_mono else warnings)[s.shot_number] = owner
    return blocking, warnings


def _draw_shot_conflicts(layout, op, project_root, sq, shots, config, exclude_dir=None):
    """Warn about a shot number already claimed elsewhere, or block outright
    for an exact mono-shot duplicate (see _classify_shot_conflicts)."""
    blocking, warnings = _classify_shot_conflicts(
        project_root, sq, shots, config, exclude_dir
    )
    if blocking:
        box = layout.box().column(align=True)
        box.alert = True
        for n, owner in sorted(blocking.items()):
            box.label(
                text=f"Shot {n:03d} already exists as {owner.name} -- pick another number.",
                icon="ERROR",
            )
    elif warnings:
        box = layout.box().column(align=True)
        box.alert = True
        for n, owner in sorted(warnings.items()):
            box.label(text=f"Shot {n:03d} already used by {owner.name}.", icon="ERROR")
        box.prop(op, "confirm_overlap")


class PIPELINE_OT_create_shot(bpy.types.Operator):
    """Create a new shot with proper naming and folder placement."""

    bl_idname = "pipeline.create_shot"
    bl_label = "New shot"
    bl_description = "Create a new versioned shot in the active project."

    sequence_number: bpy.props.IntProperty(name="Sequence", default=10, min=0, step=10)
    end_frame: bpy.props.IntProperty(name="End frame", default=1001, min=0, step=1)
    description: bpy.props.StringProperty(
        name="Description",
        description="What this shot is, shown in its tracking panel.",
        default="",
    )
    create_clean: bpy.props.BoolProperty(
        name="Start with a new clean scene", default=False
    )
    required_departments: bpy.props.EnumProperty(
        items=shot_department_items,
        options={"ENUM_FLAG"},
        name="Departments",
        default=0,
    )
    confirm_overlap: bpy.props.BoolProperty(
        name="Create anyway",
        description="A shot number above is already used by another active file",
        default=False,
    )

    def draw(self, context):
        TITLE_WIDTH = 0.35
        layout = self.layout.column(align=True)
        config = ConfigCache.get()

        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Sequence", icon="SEQUENCE")
        row.prop(self, "sequence_number", text=" ")
        layout.separator()
        shots = _draw_shot_list(layout, context, self, config, TITLE_WIDTH)
        _draw_block_warning(layout, context, shots)

        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Description", icon="TEXT")
        row.textbox(self, "description", initial_visible_lines=1)
        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Departments", icon="COLOR")
        row.prop_menu_enum(self, "required_departments")
        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Clean file", icon="FILE_BLANK")
        row.prop(self, "create_clean", text="")

        layout.separator(type="LINE", factor=3)

        _draw_timeline_warnings(layout, shots, self.end_frame)
        naming = _draw_naming_preview(layout, self.sequence_number, shots, config)
        if naming:
            sq, _sh = naming
            _draw_shot_conflicts(layout, self, get_active_project_root(), sq, shots, config)

    def invoke(self, context, event):
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        config = ConfigCache.get()
        deps = config.get(
            "shots_departments", ["layout", "animation", "lighting", "render"]
        )
        self.required_departments = {d for d in deps}
        default_start = json_get(config, "default_frame_start", 1001)
        self.end_frame = default_start + 100
        self.confirm_overlap = False

        # shots_list_creation is a WindowManager collection -- shared and
        # never cleared on its own, so without this it either starts empty
        # (nothing to click but a bare "Add" button, easy to miss and OK
        # straight into a shot with no number and no camera/marker at all --
        # see create_shot_file()'s own guard against that) or keeps
        # whatever was left over from the last shot created. Reset it to one
        # sensible default row every time, same as PIPELINE_OT_edit_block_structure's
        # own invoke() does.
        shots = context.window_manager.shots_list_creation
        shots.clear()
        item = shots.add()
        item.start_frame = default_start

        return context.window_manager.invoke_props_dialog(self, width=300)

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

        config = ConfigCache.get()
        naming = config.get("naming", {})
        if naming:
            n_prefix, n_digits = naming["sequence"]["prefix"], naming["sequence"]["digits"]
            sq = f"{n_prefix}{self.sequence_number:0{n_digits}d}"
            blocking, warnings = _classify_shot_conflicts(project_root, sq, shots, config)
            if blocking:
                n, owner = next(iter(blocking.items()))
                self.report({"ERROR"}, f"Shot {n:03d} already exists as {owner.name}.")
                return {"CANCELLED"}
            if warnings and not self.confirm_overlap:
                self.report(
                    {"ERROR"},
                    "Shot number(s) already used elsewhere -- tick 'Create anyway' to confirm.",
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
                departments=list(self.required_departments),
                description=self.description,
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
class PIPELINE_OT_edit_block_structure(bpy.types.Operator):
    """Archive this block's composition and create a new one with a
    different shot enumeration."""

    bl_idname = "pipeline.edit_block_structure"
    bl_label = "Edit block structure"
    bl_description = (
        "Archive this block and create a new one with a different shot enumeration."
    )

    filepath: bpy.props.StringProperty(default="")
    end_frame: bpy.props.IntProperty(name="End frame", default=10, min=0, step=1)
    description: bpy.props.StringProperty(
        name="Description",
        description="What this shot is, shown in its tracking panel.",
        default="",
    )
    create_clean: bpy.props.BoolProperty(
        name="Start with a new clean scene", default=False
    )
    required_departments: bpy.props.EnumProperty(
        items=shot_department_items,
        options={"ENUM_FLAG"},
        name="Departments",
        default=0,
    )
    confirm_overlap: bpy.props.BoolProperty(
        name="Branch anyway",
        description="A shot number above is already used by another active file",
        default=False,
    )

    def draw(self, context):
        TITLE_WIDTH = 0.35
        layout = self.layout
        config = ConfigCache.get()
        layout.label(text="Edit block structure", icon="UV_SYNC_SELECT")
        col = layout.column()
        col.active = False
        col.scale_y = 0.6
        col.label(text=f"Archiving: {Path(self.filepath).name}", icon="INFO")
        layout.separator()

        shots = _draw_shot_list(layout, context, self, config, TITLE_WIDTH)
        _draw_block_warning(layout, context, shots)

        layout.textbox(self, "description", initial_visible_lines=1)
        layout.prop(self, "create_clean")
        layout.prop_menu_enum(self, "required_departments")

        _draw_timeline_warnings(layout, shots, self.end_frame)
        parsed = parse_filename(Path(self.filepath).name)
        if parsed:
            naming = _draw_naming_preview(layout, int(parsed["sequence"]), shots, config)
            if naming:
                sq, _sh = naming
                _draw_shot_conflicts(
                    layout,
                    self,
                    get_active_project_root(),
                    sq,
                    shots,
                    config,
                    exclude_dir=Path(self.filepath).parent,
                )

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
        self.required_departments = {d for d in required}
        default_start = json_get(config, "default_frame_start", 1001)
        self.confirm_overlap = False

        # Seed from the scene's own live markers where the file being
        # edited is actually the open one -- derive_shot_subranges() only
        # makes sense against a genuinely open scene (same rule as the
        # farm's own split, see NOTES.md "Split at render"). Falls back to
        # default_start per shot / scene.frame_end for anything a marker
        # doesn't cover (missing marker, or filepath isn't the open file).
        naming = config.get("naming", {})
        shot_numbers = shots_in_segment(parsed["shot"])
        ranges = {}
        if naming and bpy.data.filepath == self.filepath:
            sequence_label = f"{naming['sequence']['prefix']}{parsed['sequence']}"
            found, _absorbed = derive_shot_subranges(
                context.scene, sequence_label, set(shot_numbers), config
            )
            ranges = {r["shot_number"]: r for r in found}
        self.end_frame = context.scene.frame_end if ranges else default_start

        shots = context.window_manager.shots_list_creation
        shots.clear()
        for n in shot_numbers:
            item = shots.add()
            item.shot_number = n
            item.start_frame = ranges[n]["frame_start"] if n in ranges else default_start

        return context.window_manager.invoke_props_dialog(self, width=380)

    def execute(self, context):
        project_root = get_active_project_root()
        old_path = Path(self.filepath)
        parsed = parse_filename(old_path.name)
        if not parsed:
            self.report({"ERROR"}, "Not a shot file.")
            return {"CANCELLED"}

        shots = context.window_manager.shots_list_creation
        sq = old_path.parent.parent.name
        config = ConfigCache.get()
        blocking, warnings = _classify_shot_conflicts(
            project_root, sq, shots, config, exclude_dir=old_path.parent
        )
        if blocking:
            n, owner = next(iter(blocking.items()))
            self.report({"ERROR"}, f"Shot {n:03d} already exists as {owner.name}.")
            return {"CANCELLED"}
        if warnings and not self.confirm_overlap:
            self.report(
                {"ERROR"},
                "Shot number(s) already used elsewhere -- tick 'Branch anyway' to confirm.",
            )
            return {"CANCELLED"}

        try:
            if self.create_clean:
                bpy.ops.wm.read_homefile(use_empty=True)
            elif bpy.data.filepath and bpy.data.is_dirty:
                bpy.ops.wm.save_mainfile()

            kept_numbers = {s.shot_number for s in shots}
            # Create the new file before archiving the old one, so a
            # failure here never leaves a block archived with no successor.
            dest_path = create_shot_file(
                project_root,
                sequence_number=int(parsed["sequence"]),
                shot_number=[s.shot_number for s in shots],
                timeline=[s.start_frame for s in shots] + [self.end_frame],
                departments=list(self.required_departments),
                description=self.description,
                start_version=int(parsed["number"]) + 1,
            )
            # Flag first -- still needed for TrackingStatusCache.get_all(),
            # which would otherwise still pick up the tracking.json once
            # it's moved under old/ below (see NOTES.md, "Branch").
            old_tracking = old_path.parent / ".pipeline" / "tracking.json"
            with locked_json(old_tracking) as box:
                data = box["data"] or {}
                if not data:
                    raise PipelineError(f"Tracking file not found: {old_tracking}")
                data["archived"] = True
                box["action"] = "to_write"

            copy_entries(old_path, dest_path)

            # Physically move the branched-out composition into old/ --
            # visible outside the addon, and deliberately not link-safe.
            archive_folder(old_path.parent)

            # Shots dropped from the new enumeration: archive their renders
            # too (unless some other active block/shot still covers that
            # number), so "Preview sequence" stops pulling in a dead cut.
            # archive_folder() above already moved the old block out of
            # sq/, so its own numbers no longer show up as "still active".
            shot_prefix = json_get(config, "naming.shot.prefix", "sh")
            shot_digits = json_get(config, "naming.shot.digits", 3)
            active_numbers = active_shot_owners(project_root, sq, config)
            for n in shots_in_segment(parsed["shot"]):
                if n in kept_numbers or n in active_numbers:
                    continue
                render_dir = (
                    project_root / "renders" / sq / f"{shot_prefix}{n:0{shot_digits}d}"
                )
                if render_dir.is_dir():
                    archive_folder(render_dir)
        except PipelineError as e:
            log(e.level, "edit_block_structure", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}

        log("SUCCESS", "edit_block_structure", f"{old_path.name} -> {dest_path.name}")
        self.report(
            {"INFO"}, f"Branched: {old_path.name} archived, created {dest_path.name}"
        )
        return {"FINISHED"}
