"""Farm operators: launch/kill the monitor, submit render requests, self as worker, farm monitor UI."""

import os
from pathlib import Path

import bpy

from ..farm import (
    archive,
    cancel_pending_renders,
    failed_stage,
    get_monitor_cache,
    job_cancel_request,
    job_request,
    job_state,
    local_jobs_in_flight,
    reserve_this_machine,
    kill_worker,
    launch_monitor,
    launch_worker,
    load_job_details,
    monitor_age_status,
    monitor_last_tick,
    recompilable,
    recompile_job,
    refresh_monitor_status,
    remove_waiting_job,
    request_monitor_kill,
    retry_job,
    scan_workers,
    stop_worker,
    worker_rendering,
)
from ..lib.monitoring.status import preset_department
from ..lib import (
    EARLIEST,
    ConfigCache,
    PipelineAction,
    PipelineError,
    asset_folder_items,
    cached_scandir,
    draw_box_tip,
    get_active_project_root,
    get_folder,
    get_machine_id,
    get_opened_as_read_only,
    get_user,
    json_get,
    locked_json,
    log,
    monitoring_detail,
    parse_filename,
    prefix_items,
    read_json_quiet,
    report_error,
    resolve_ffmpeg,
    resolve_version_file,
    scan_descriptions,
    sequence_items,
    set_pending_action,
    shot_items,
    shots_in_segment,
    version_items,
)
from .preview_ops import dropped_message, request_sequence_preview

_workers_items_cache: list[tuple[str, str, str]] = []
_pre_render_scripts: list[tuple[str, str, str]] = []
# The pre-render picker's "None" item. Never "": Blender draws an item with
# an empty identifier as a heading in the menu, not as a choice.
_NO_SCRIPT = "NONE"


def _stable_enum_items(cache: list, items: list) -> list:
    """Return cache holding items, for a dynamic EnumProperty callback.
    Blender keeps raw pointers to the strings of the list last returned,
    and calls the callback again on every redraw, open menu included: new
    but equal strings each time would free the ones it's still drawing --
    blank or garbled names. So the old ones stay while nothing changed."""
    if cache != items:
        cache[:] = items
    return cache


def _get_workers_items(self, context):
    """Enum items from live workers, tagged "(used)" when busy."""
    try:
        workers = scan_workers()

        items = []
        for uuid, d in workers.items():
            # Worker files carry get_user_data()'s fields (user/machine/uuid).
            user = d.get("user", "unknown")
            machine = d.get("machine", uuid[:8])
            tag = " (used)" if d.get("status") != "idle" else ""
            items.append((uuid, user, f"{user} ({machine}){tag}"))

        return _stable_enum_items(_workers_items_cache, items)

    except Exception as e:
        log("WARNING", "farm", f"Could not list machines: {e}")
        return _stable_enum_items(
            _workers_items_cache, [("NONE", "No worker found", "")]
        )


def pre_render_script_items(
    presets_dir: Path | None, departments=()
) -> list[tuple[str, str, str]]:
    """The pre-render picker's items: "no script", then every .py preset
    directly under presets_dir (matches apply_custom_preset()'s
    lookup), excluding asset_file_preset.py and the ffmpeg_presets/
    subfolder -- each with the department its name gives among
    departments (preset_department()): its renders are that department's."""
    items = [(_NO_SCRIPT, "No pre-render script", "Render with the file's own settings")]
    if presets_dir is None:
        return items
    try:
        names = set()
        # cached_scandir(): the pickers are re-evaluated on every redraw;
        # DirEntry.is_file() needs no extra stat.
        for f in cached_scandir(presets_dir):
            suffix = Path(f.name).suffix
            if (
                f.is_file()
                and suffix == ".py"
                and f.name != "asset_file_preset.py"
                and Path(f.name).stem != _NO_SCRIPT
            ):
                names.add(Path(f.name).stem)
        for name in sorted(names):
            dep = preset_department(name, departments)
            items.append((
                name,
                f"{name}  ·  {dep}" if dep else name,
                f"Apply preset '{name}' before render."
                + (f" Its renders are {dep}'s." if dep else " Its renders have no department."),
            ))
    except Exception as e:
        log("WARNING", "farm", f"Could not list pre-render presets: {e}")
    return items


def _get_pre_render_scripts(self, context):
    """The Render dialog's picker: the active project's presets."""
    try:
        presets_dir = ConfigCache.get_path("presets")
    except Exception as e:
        log("WARNING", "farm", f"Could not list pre-render presets: {e}")
        presets_dir = None
    config = ConfigCache.get() or {}
    departments = [*json_get(config, "shots_departments", []), *json_get(config, "assets_departments", [])]
    items = pre_render_script_items(presets_dir, departments)
    # The picked department's presets first (its name's, or set for it), then the others.
    dept = getattr(self, "department", _NO_DEPT)
    if dept and dept != _NO_DEPT and len(items) > 1:
        own = {(json_get(config, "farm.department_presets", {}) or {}).get(dept)}
        mine = [i for i in items[1:] if i[0] in own or preset_department(i[0], [dept])]
        if mine:
            items = [items[0], *mine, None, *[i for i in items[1:] if i not in mine]]
    return _stable_enum_items(_pre_render_scripts, items)


def default_pre_render_script(config: dict, items: list) -> str:
    """config's farm.default_prerender_script (Edit project) if it's still
    one of the picker's items, else _NO_SCRIPT."""
    name = json_get(config, "farm.default_prerender_script", "") or ""
    return name if name in {item[0] for item in items if item} else _NO_SCRIPT


_NO_DEPT = "NONE"
_department_items_cache: list = []


def _file_departments(filepath: str) -> list[str]:
    """The project's departments for filepath's kind (shots' or assets');
    both, shots first, for no file (the list, mixed)."""
    config = ConfigCache.get() or {}
    shots = list(json_get(config, "shots_departments", []) or [])
    assets = list(json_get(config, "assets_departments", []) or [])
    if not filepath:
        return list(dict.fromkeys([*shots, *assets]))
    is_shot = (parse_filename(Path(filepath).name) or {}).get("shot")
    return shots if is_shot else assets


def _get_departments(self, context):
    """The Render dialog's department picker: the file's kind's departments."""
    items = [(_NO_DEPT, "No department", "Its render counts for no department")]
    items += [(d, d, f"A render for {d}: its to check and last render") for d in _file_departments(self.filepath)]
    return _stable_enum_items(_department_items_cache, items)


def department_preset(config: dict, department: str, items: list) -> str:
    """The preset a department's renders start from: the one set in Project
    settings (Presets by department), else <department>_default, else the
    first whose name gives it, else no script."""
    names = {i[0] for i in items if i}
    set_ = (json_get(config, "farm.department_presets", {}) or {}).get(department)
    if set_ in names:
        return set_
    if f"{department}_default" in names:
        return f"{department}_default"
    for i in items:
        if i and i[0] != _NO_SCRIPT and preset_department(i[0], [department]):
            return i[0]
    return _NO_SCRIPT


def last_render(filepath: str, department: str | None = None) -> dict:
    """filepath's latest finished render (of department, if given) in its
    render_history.json, {} if none."""
    if not filepath:
        return {}
    history = read_json_quiet(Path(filepath).parent / ".pipeline" / "render_history.json") or {}
    for e in reversed(history.get("entries") or []):
        if e.get("status") == "split":
            continue
        if department is None or (e.get("department") or "") == department:
            return e
    return {}


def _department_changed(self, context):
    """A department picked: its preset -- the one this file was last
    rendered with for it, else the department's own (department_preset())."""
    items = _get_pre_render_scripts(self, context)
    names = {i[0] for i in items if i}
    if self.department == _NO_DEPT:
        self.pre_render_script = default_pre_render_script(ConfigCache.get(), items)
        return
    last = last_render(self.filepath, self.department).get("prerender_script")
    self.pre_render_script = last if last in names else department_preset(ConfigCache.get(), self.department, items)


class M_PIPELINE_OT_farm_kill_monitor(bpy.types.Operator):
    """Stop the current farm monitor"""

    bl_idname = "m_pipeline.farm_kill_monitor"
    bl_label = "Kill"
    bl_description = "Stop the current farm monitor so someone else can take over"

    lock_user: bpy.props.StringProperty()
    lock_machine: bpy.props.StringProperty()
    is_own: bpy.props.BoolProperty(default=False)

    def invoke(self, context, event):
        lock_path = ConfigCache.get_path("monitor_file")
        if not lock_path.exists():
            self.report({"WARNING"}, "No active farm monitor found.")
            return {"CANCELLED"}
        try:
            with locked_json(lock_path, read_only=True, retries=0) as box:
                data = box["data"] or {}
                self.lock_user = data.get("user", "unknown")
                self.lock_machine = data.get("machine", "unknown")
                self.is_own = data.get("pid") == os.getpid()
        except Exception:
            self.lock_user = "unknown"
            self.lock_machine = "unknown"
            self.is_own = False
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        if self.is_own:
            layout.label(text="Stop your own farm?", icon="QUESTION")
        else:
            layout.label(
                text=f"Kill {self.lock_user}'s farm on {self.lock_machine}?",
                icon="ERROR",
            )
        layout.separator(factor=0.5)
        layout.label(text="Pending renders will not be cancelled.", icon="INFO")
        layout.label(text="Already-running processes will finish.", icon="BLANK1")

    def execute(self, context):
        request_monitor_kill(get_user(context))
        self.report(
            {"INFO"}, "Kill request sent -- the monitor will stop on its next tick."
        )
        return {"FINISHED"}


class M_PIPELINE_OT_farm_launch_monitor(bpy.types.Operator):
    """Launch the farm and become its monitor"""

    bl_idname = "m_pipeline.farm_launch_monitor"
    bl_label = "Launch"
    bl_description = "Launch the farm and become its monitor"

    force: bpy.props.BoolProperty(default=False)
    stale_user: bpy.props.StringProperty()
    stale_since: bpy.props.StringProperty()
    skip_ffmpeg_check: bpy.props.BoolProperty(default=False)

    def invoke(self, context, event):
        if not self.skip_ffmpeg_check and not resolve_ffmpeg():
            set_pending_action(
                PipelineAction(
                    title="FFmpeg not found",
                    message=(
                        "FFmpeg isn't installed, or not on this machine's PATH.\n"
                        "Every job this monitor dispatches will fail its "
                        "checks_images and compilation stages.\n"
                        "If it IS installed, a sandboxed launch (Steam, "
                        "Flatpak...) can hide it -- set an explicit path "
                        "in Preferences > FFmpeg path."
                    ),
                    severity="warning",
                    choices=[
                        (
                            "Continue anyway",
                            self._continue_without_ffmpeg,
                            "Launch the monitor without FFmpeg -- checks_images and compilation will fail.",
                        ),
                    ],
                )
            )
            # Deferred one timer tick -- see NOTES.md, "Popup-chaining".
            bpy.app.timers.register(
                lambda: bpy.ops.m_pipeline.action_popup("INVOKE_DEFAULT"),
                first_interval=0.05,
            )
            return {"FINISHED"}

        lock_path = ConfigCache.get_path("monitor_file")

        if lock_path.exists():
            try:
                with locked_json(lock_path, read_only=True, retries=0) as box:
                    data = box["data"] or {}
                    # Heartbeat: mtime or in-file update_tick (see monitor_tick()).
                    last_tick = (
                        monitor_last_tick(lock_path, data) or EARLIEST
                    )
                    is_stale = monitor_age_status(last_tick) != "running"

                    if not is_stale:
                        self.report(
                            {"ERROR"},
                            f"Monitor already running by {data['user']} on {data['machine']}.",
                        )
                        return {"CANCELLED"}

                    self.force = True
                    self.stale_user = data.get("user", "unknown")
                    self.stale_since = last_tick.strftime("%H:%M:%S")
                    return context.window_manager.invoke_props_dialog(self, width=320)

            except Exception as e:
                self.report({"ERROR"}, f"Failed to read monitor lock: {e}")
                return {"CANCELLED"}

        return self.execute(context)

    def _continue_without_ffmpeg(self):
        """Re-invoke via a fresh bpy.ops call, deferred one timer tick -- see
        NOTES.md, "Popup-chaining". skip_ffmpeg_check=True: already
        confirmed, don't re-ask."""
        bpy.app.timers.register(
            lambda: bpy.ops.m_pipeline.farm_launch_monitor(
                "INVOKE_DEFAULT", skip_ffmpeg_check=True
            ),
            first_interval=0.05,
        )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Stale lock detected!", icon="ERROR")
        layout.separator(factor=0.5)
        layout.label(
            text=f"Last seen: {self.stale_user} at {self.stale_since}",
            icon="TIME",
        )
        layout.label(text="The previous monitor may have crashed.", icon="INFO")
        layout.separator()
        layout.label(text="Take over the monitor role?", icon="QUESTION")

    def execute(self, context):
        project_root = get_active_project_root()
        try:
            launch_monitor(project_root, get_user(context), force=self.force)
        except PipelineError as e:
            log(e.level, "farm_launch_monitor", e.message)
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        # The sidebar reads the farm status from a cache refreshed every
        # 10 s -- refresh it now so the header doesn't show "not running"
        # right after a launch. (Kill is asynchronous: nothing to refresh
        # until the monitor's own next tick.)
        refresh_monitor_status()
        self.report({"INFO"}, "Farm monitor launched.")
        return {"FINISHED"}


class PIPELINE_PG_farm_list_item(bpy.types.PropertyGroup):
    """One entry in the multi-file render submission list (scene.pipeline_farm_list)."""

    filepath: bpy.props.StringProperty(name="Path", default="")


class PIPELINE_PG_render_subshot_item(bpy.types.PropertyGroup):
    """One shot in the block being submitted for render -- a checklist row
    so the artist can submit just the shot(s) that need it."""

    shot_number: bpy.props.IntProperty(name="")
    include: bpy.props.BoolProperty(name="", default=True)


class PIPELINE_PG_preview_sequence_item(bpy.types.PropertyGroup):
    """One sequence of the Render dialog's Preview checklist."""

    name: bpy.props.StringProperty()
    include: bpy.props.BoolProperty(name="", default=False)


class M_PIPELINE_OT_farm_request_render(bpy.types.Operator):
    """Submit a render job (or a batch, via the list) to the farm queue."""

    bl_idname = "m_pipeline.farm_request_render"
    bl_label = "Render"
    bl_description = "Submit this file (or the pending list) to the render farm queue."

    # SKIP_SAVE: otherwise Blender remembers the last value across
    # invocations (its redo-panel memory), so the project panel's/top bar's
    # plain "Render" button -- which never sets filepath itself, meaning to
    # show the list/picker -- would inherit whatever file "Render this
    # file"/file_panel.py's own "Render" last submitted.
    filepath: bpy.props.StringProperty(
        name="filepath", default="", options={"SKIP_SAVE"}
    )
    # The "Render this file" shortcut: a keymap item can't hold the open
    # file's path, invoke() reads it.
    current_file: bpy.props.BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    # From the file panel's Render: the file open here may be rendered on
    # this machine (Where). Never from elsewhere: it renders the open file.
    here_ok: bpy.props.BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    where: bpy.props.EnumProperty(
        name="Where",
        items=[
            ("farm", "Farm", "Into the farm's queue: every machine it has, its priorities"),
            (
                "local",
                "Local · playblast",
                "On this machine, now, outside the farm's queue: the same render "
                "(its preset, video, history, to check), no host needed. A farm "
                "render on this machine gives way after its frame",
            ),
            (
                "viewport",
                "Local · viewport",
                "On this machine, now: each frame drawn by the file's largest 3D "
                "view through the camera -- its overlays as they are (rigs, "
                "bones...). A Blender window opens for it, this one stays free",
            ),
        ],
        default="farm",
        options={"SKIP_SAVE"},
    )

    file_type: bpy.props.EnumProperty(
        items=[
            ("asset", "Asset / Library", ""),
            ("shot", "Shot", ""),
            (
                "preview",
                "Preview",
                "Sequence previews: each shot's latest video, end to end",
            ),
        ],
        default="shot",
    )

    # Asset cascade: prefix → folder
    asset_prefix: bpy.props.EnumProperty(items=prefix_items)
    asset_folder: bpy.props.EnumProperty(items=asset_folder_items)

    # Shot cascade: sequence → shot
    sequence: bpy.props.EnumProperty(items=sequence_items)
    shot: bpy.props.EnumProperty(items=shot_items)

    # Version selection
    version_mode: bpy.props.EnumProperty(
        items=[
            ("stable", "Last stable", "Most recent -stable version"),
            ("last", "Last", "Most recent version"),
            ("custom", "Custom", "Pick a specific version"),
        ],
        default="stable",
    )
    custom_version: bpy.props.EnumProperty(items=version_items)

    settings: bpy.props.BoolProperty(name="Settings", default=False)
    project_root: bpy.props.StringProperty(name="project_root", default="")

    # SKIP_SAVE: every submit starts back at 10 -- Blender would otherwise
    # keep the last one, and a rush priority sticks to the next shots.
    priority: bpy.props.IntProperty(
        name="Priority",
        default=10,
        description="Higher goes first (10 by default); same priority: oldest first",
        options={"SKIP_SAVE"},
    )
    render_mode: bpy.props.EnumProperty(
        items=[
            (
                "all",
                "All machines",
                "Every free machine takes chunks of frames; more can join any time",
            ),
            ("single", "Single", "One machine at a time renders the whole range"),
        ],
        name="Render Mode",
        default="all",
    )
    increment: bpy.props.BoolProperty(
        name="Increment",
        description="Always use a new output folder (force_all)",
        default=True,
    )
    assigned_machines: bpy.props.EnumProperty(
        items=_get_workers_items,
        name="Target Machine",
        options={"ENUM_FLAG"},
        default=0,
    )

    frame_start: bpy.props.IntProperty(name="Frame_start", default=0)
    frame_end: bpy.props.IntProperty(name="Frame_end", default=0)

    _override_mode = [
        ("n", "Don't override", "Keep actual frame range."),
        ("a", "Absolute", "Override with absolute frame number."),
        ("s", "Relative to start", "Override with start relative frame number."),
        ("e", "Relative to end", "Override with end relative frame number."),
    ]
    rel_frame_start: bpy.props.EnumProperty(
        items=_override_mode,
        name="Frame override",
        default="n",
    )  # type: ignore

    rel_frame_end: bpy.props.EnumProperty(
        items=_override_mode,
        name="Frame override",
        default="n",
    )  # type: ignore

    sound: bpy.props.BoolProperty(
        name="Sound",
        description="The scene's own sound (sequencer sound strips, speakers) "
        "in the video, over the rendered range. Off: a video without sound",
        default=True,
    )  # type: ignore

    department: bpy.props.EnumProperty(
        items=_get_departments,
        name="Department",
        description="The department this render is for: its to check, its last render. "
        "Picking one sets its preset",
        update=_department_changed,
        options={"SKIP_SAVE"},
    )  # type: ignore

    pre_render_script: bpy.props.EnumProperty(
        items=_get_pre_render_scripts,
        name="Pre render script",
        default=0,
    )  # type: ignore

    def invoke(self, context, event):
        global _machines_items_cache
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        if self.current_file and not self.filepath:
            if not bpy.data.filepath:
                self.report({"ERROR"}, "Save this file first.")
                return {"CANCELLED"}
            self.filepath = bpy.data.filepath
        self.project_root = str(get_active_project_root())
        scan_descriptions(get_active_project_root())  # menu tooltips
        # Every submit starts from this file's last render's department (its
        # preset with it: _department_changed()), else the project's preset --
        # never the dialog's last one.
        dept = last_render(self.filepath).get("department") or ""
        self.department = dept if dept and dept in _file_departments(self.filepath) else _NO_DEPT
        _department_changed(self, context)  # its update may not run from invoke()
        if self.filepath:
            self._populate_subshots(context)
            if event.ctrl:
                return self.single(context)

            else:
                return context.window_manager.invoke_props_dialog(
                    self, width=300, confirm_text="Submit"
                )
        else:
            self._populate_sequences(context)
            return context.window_manager.invoke_props_dialog(
                self, width=300, confirm_text="Submit all"
            )

    def _panel_setting(self, context, col, is_block=False):
        """The submit settings: priority, mode, increment, frame override,
        assigned machines, pre-render script."""
        draw_box_tip(
            col,
            context,
            "All machines: every free worker takes chunks of frames, and more "
            "can join at any time. Single: one machine renders the whole range. "
            "Highest priority goes first. Increment: a new render folder rather "
            "than replacing the last one. No assigned machine: any worker. "
            "Sound: the scene's own, in the video. "
            "Pre-render script: a preset from config/presets applied first.",
            width_px=300,
        )
        here = self._here_ok()
        if here:
            col.row().prop(self, "where", expand=True)
            if self.where != "farm" and bpy.data.is_dirty:
                note = col.row()
                note.active = False
                note.label(text="Unsaved changes: saved first (no new version).", icon="FILE_TICK")
            col.separator()
        farm = not here or self.where == "farm"
        row = col.row(align=False)
        if farm:
            row.prop(self, "priority")
            row.prop(self, "render_mode", text="")
        row.prop(self, "increment")

        col.separator()
        if is_block:
            info = col.row()
            info.active = False
            info.label(
                text="Override applies within each selected shot's own range.",
                icon="INFO",
            )
        row = col.row(align=False)
        row1 = row.split(factor=0.6, align=True)
        row1.prop(self, "rel_frame_start", text="")
        row1.prop(self, "frame_start", text="")

        row2 = row.split(factor=0.6, align=True)
        row2.prop(self, "rel_frame_end", text="")
        row2.prop(self, "frame_end", text="")

        col.separator()
        col.prop(self, "sound")
        if farm:
            col.prop_menu_enum(
                self, "assigned_machines", text="Assigned machines (empty: auto)"
            )
        col.separator()
        # Department, then its preset (a dropdown, not prop_menu_enum(): shows the one picked).
        col.prop(self, "department", text="")
        col.prop(self, "pre_render_script", text="")

    def _draw_subshots(self, layout, subshots):
        """A block's checklist of shots to render."""
        naming = ConfigCache.get().get("naming", {})
        prefix = json_get(naming, "shot.prefix", "sh")
        digits = json_get(naming, "shot.digits", 3)

        box = layout.box().column(align=True)
        box.label(
            text="Shots in this block -- pick which to render:", icon="CAMERA_DATA"
        )
        for item in subshots:
            label = f"{prefix}{item.shot_number:0{digits}d}"
            box.row(align=True).prop(item, "include", text=label)
        layout.separator()

    def draw(self, context):
        layout = self.layout

        if self.filepath:
            subshots = context.window_manager.render_subshots
            is_block = len(subshots) > 1
            if is_block:
                self._draw_subshots(layout, subshots)
            self._panel_setting(context, layout.column(), is_block=is_block)

        else:
            ### file selection
            select = layout.column(align=True)
            row = select.row()
            row.prop(self, "file_type", expand=False, text="")

            select.separator()
            if self.file_type == "preview":
                draw_box_tip(
                    layout,
                    context,
                    "A preview compiles a disposable playback mp4 from the "
                    "shots already rendered, not a final render. Tick the "
                    "sequences to compile.",
                    width_px=300,
                )
                self._draw_sequences(layout, context.window_manager.preview_sequences)
                layout.prop(self, "priority")
                return

            if self.file_type == "asset":
                row = select.split(align=True, factor=0.33)
                row.prop(self, "asset_prefix", text="")
                row.prop(self, "asset_folder", text="")
            elif self.file_type == "shot":
                row = select.split(align=True, factor=0.33)
                row.prop(self, "sequence", text="")
                row.prop(self, "shot", text="")

            select.separator()

            select.row().prop(self, "version_mode", expand=True)
            if self.version_mode == "custom":
                select.separator(factor=0.5)
                select.prop(self, "custom_version", text="")

            ### file selection result
            layout.separator()
            col = layout.column()
            name = col.split(factor=0.7)
            resolved = self._resolve(context)
            if resolved:
                name.label(text=resolved.name, icon="FILE_BLEND")
                name.operator("m_pipeline.farm_add_to_list", icon="ADD").filepath = str(
                    resolved
                )
            else:
                name.label(text="No matching file found.", icon="ERROR")

            ### list -- shown even empty, so it's clear where "Add" goes
            layout.separator(factor=2)
            box = layout.box().column(align=True)
            box.label(text="Render list:")
            box.separator(type="LINE", factor=0.5)
            box.separator()
            if not context.scene.pipeline_farm_list:
                empty = box.row()
                empty.active = False
                empty.label(text="Empty -- add files with the button above.", icon="INFO")
            else:
                f_list = box.column(align=True)
                f_list.scale_y = 0.75
                for f in context.scene.pipeline_farm_list:
                    f_row = f_list.row()
                    f_row.label(text=Path(f.filepath).stem)
                    f_row.operator(
                        "m_pipeline.farm_list_delete",
                        icon="TRASH",
                        text="",
                        emboss=False,
                    ).filepath = f.filepath
                box.separator()
                box.operator(
                    "m_pipeline.farm_list_delete", icon="TRASH", text="Clear list"
                ).filepath = ""

            ### settings
            layout.separator(factor=2)
            setts = layout.column(align=False)
            setts.prop(
                self,
                "settings",
                icon="DOWNARROW_HLT" if self.settings else "RIGHTARROW",
            )
            if self.settings:
                setts.separator()
                col = setts.column(align=False)

                self._panel_setting(context, col)

    def execute(self, context):

        if self.filepath:
            return self.single(context)
        if self.file_type == "preview":
            return self._submit_previews(context)

        user = get_user(context)
        start, end = self._override_strings()
        count = len(context.scene.pipeline_farm_list)
        try:
            for item in context.scene.pipeline_farm_list:
                self._submit_for_filepath(item.filepath, user, start, end)
        except PipelineError as e:
            # list is left as-is on failure: a mid-batch error shouldn't lose
            # the files that weren't submitted yet
            log(e.level, "farm_request_render", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        context.scene.pipeline_farm_list.clear()
        self.report({"INFO"}, f"{count} render job(s) submitted.")
        return {"FINISHED"}

    def _override_strings(self) -> tuple[str, str]:
        """The frame override as job_request() takes it: "n" (none) or the mode
        letter and the frame ("s10", "e-5")."""
        start = (
            "n"
            if self.rel_frame_start == "n"
            else f"{self.rel_frame_start}{self.frame_start!s}"
        )
        end = (
            "n"
            if self.rel_frame_end == "n"
            else f"{self.rel_frame_end}{self.frame_end!s}"
        )
        return start, end

    def _submit_for_filepath(
        self,
        filepath: str,
        user: str,
        start: str,
        end: str,
        only: set[int] | None = None,
    ) -> None:
        """Submit one render job for filepath. `only` (from the checklist)
        rides along as this job's only_shots. Where (the file open here):
        on this machine, outside the queue (farm/local.py)."""
        here = self._here_ok() and self.where != "farm"
        if here:
            # First: no job left waiting for a machine that can't take it
            # (another Blender of it is its worker). Kept for nothing, it's
            # released on the farm loop's next turn.
            reserve_this_machine()
        job_request(
            filepath,
            user=user,
            priority=self.priority,
            render_mode=self.render_mode,
            assigned_machines=list(self.assigned_machines),
            increment=self.increment,
            # "" for none, as stored in job files (and job ids) before.
            prerender_script=(
                "" if self.pre_render_script == _NO_SCRIPT else self.pre_render_script
            ),
            overrided_frame_range=(start, end),
            only_shots=sorted(only) if only else None,
            sound=self.sound,
            # Picked in the dialog; "" none. A file of another kind (the list,
            # mixed): what its preset's name gives.
            department=(
                ""
                if self.department == _NO_DEPT
                else self.department
                if self.department in _file_departments(filepath)
                else None
            ),
            local=get_machine_id() if here else "",
            viewport=here and self.where == "viewport",
        )

    def _here_ok(self) -> bool:
        """Where offered: the file panel's Render, of the file open here."""
        return bool(self.here_ok and self.filepath and bpy.data.filepath) and os.path.normcase(
            os.path.abspath(self.filepath)
        ) == os.path.normcase(os.path.abspath(bpy.data.filepath))

    def _save_first(self) -> bool:
        """Rendered here: the file as it is now -- saved first when it has
        unsaved changes (a plain save, no new version). False, reported: open
        read-only, it can't be."""
        if not bpy.data.is_dirty:
            return True
        if get_opened_as_read_only() == bpy.data.filepath:
            self.report({"ERROR"}, "This file is open read-only: save your changes as a new version first.")
            return False
        bpy.ops.wm.save_mainfile()
        return True

    def _populate_subshots(self, context) -> None:
        """Refill window_manager.render_subshots from self.filepath's own
        name, all checked by default. Empty for a non-shot or mono-shot file."""
        subshots = context.window_manager.render_subshots
        subshots.clear()
        if not self.filepath:
            return
        parsed = parse_filename(Path(self.filepath).name)
        if not parsed or not parsed.get("shot"):
            return
        shots = shots_in_segment(parsed["shot"])
        if len(shots) <= 1:
            return
        for n in shots:
            item = subshots.add()
            item.shot_number = n
            item.include = True

    def _populate_sequences(self, context) -> None:
        """Refill window_manager.preview_sequences with the project's
        sequences, none checked."""
        sequences = context.window_manager.preview_sequences
        sequences.clear()
        shots_dir = Path(self.project_root) / "shots"
        try:
            names = sorted(e.name for e in os.scandir(shots_dir) if e.is_dir())
        except OSError:
            names = []
        for name in names:
            sequences.add().name = name

    def _draw_sequences(self, layout, sequences) -> None:
        """The Preview checklist: which sequences to compile end to end."""
        box = layout.box().column(align=True)
        box.label(text="Sequences to preview:", icon="SEQUENCE")
        if not sequences:
            empty = box.row()
            empty.active = False
            empty.label(text="No sequence in this project.", icon="INFO")
        for item in sequences:
            box.row(align=True).prop(item, "include", text=item.name)
        info = layout.row()
        info.active = False
        info.label(text="Each shot's latest video, end to end.", icon="INFO")

    def _submit_previews(self, context):
        """One preview compile request per checked sequence."""
        chosen = [s.name for s in context.window_manager.preview_sequences if s.include]
        if not chosen:
            self.report({"ERROR"}, "No sequence selected.")
            return {"CANCELLED"}
        user = get_user(context)
        sent, empty, dropped = [], [], []
        try:
            for name in chosen:
                sources = request_sequence_preview(name, user, self.priority, dropped)
                (sent if sources else empty).append(name)
        except PipelineError as e:
            return report_error(self, "farm_request_render", e)
        if not sent:
            self.report({"WARNING"}, "Nothing rendered yet in the selected sequence(s).")
            return {"CANCELLED"}
        message = f"Preview requested: {', '.join(sent)}."
        if empty:
            message += f" Nothing rendered yet in {', '.join(empty)}."
        left_out = dropped_message(dropped)
        if left_out:
            message += f" {left_out}"
        self.report({"WARNING" if empty or left_out else "INFO"}, message)
        return {"FINISHED"}

    def single(self, context):
        """Submit self.filepath alone (Ctrl+click, or the dialog of one file):
        only the shots ticked for a block."""
        user = get_user(context)
        start, end = self._override_strings()
        subshots = context.window_manager.render_subshots

        only = None
        if subshots:
            only = {s.shot_number for s in subshots if s.include}
            if not only:
                self.report({"ERROR"}, "No shot selected to render.")
                return {"CANCELLED"}

        here = self._here_ok() and self.where != "farm"
        if here and not self._save_first():
            return {"CANCELLED"}
        try:
            self._submit_for_filepath(self.filepath, user, start, end, only)
        except PipelineError as e:
            return report_error(self, "farm_request_render", e)
        context.scene.pipeline_farm_list.clear()
        if here:
            self.report({"INFO"}, f"Rendering here: {Path(self.filepath).name} (Farm in browser follows it).")
        else:
            self.report({"INFO"}, f"Render job submitted: {Path(self.filepath).name}")
        return {"FINISHED"}

    def _resolve(self, context) -> Path | None:
        """Return the Path of the file matching current selections, or None.
        Called from draw() on every redraw -- see resolve_version_file()."""
        folder = get_folder(self, context)
        return resolve_version_file(folder, self.version_mode, self.custom_version)


class M_PIPELINE_OT_farm_add_to_list(bpy.types.Operator):
    """Add a resolved file to the pending multi-file render submission list."""

    bl_idname = "m_pipeline.farm_add_to_list"
    bl_label = "Add to list"

    filepath: bpy.props.StringProperty(name="Path", default="")

    def execute(self, context):
        if self.filepath not in [i.filepath for i in context.scene.pipeline_farm_list]:
            item = context.scene.pipeline_farm_list.add()  # PropertyGroup collection
            item.filepath = str(self.filepath)
            return {"FINISHED"}
        else:
            return {"CANCELLED"}


class M_PIPELINE_OT_farm_list_delete(bpy.types.Operator):
    """Remove one entry from the render submission list, or clear it (filepath="")."""

    bl_idname = "m_pipeline.farm_list_delete"
    bl_label = ""

    filepath: bpy.props.StringProperty(name="filepath", default="")

    def execute(self, context):
        list = context.scene.pipeline_farm_list

        if self.filepath == "":
            list.clear()
            return {"FINISHED"}

        f_list = [f.filepath for f in list]

        if self.filepath in f_list:
            list.remove(f_list.index(self.filepath))
            return {"FINISHED"}
        else:
            return {"CANCELLED"}


class M_PIPELINE_OT_farm_add_self_worker(bpy.types.Operator):
    """Add this computer to the farm machine pool."""

    bl_idname = "m_pipeline.farm_add_self_worker"
    bl_label = "Add this machine to the farm as worker."
    bl_description = "Register this computer as a farm worker for the active project."

    def execute(self, context):
        if launch_worker():
            self.report({"INFO"}, "This machine is now a farm worker.")
            return {"FINISHED"}
        self.report(
            {"WARNING"}, "Another Blender instance on this machine is already a worker."
        )
        return {"CANCELLED"}


class M_PIPELINE_OT_farm_kill_self_worker(bpy.types.Operator):
    """Remove this computer's worker role from the farm."""

    bl_idname = "m_pipeline.farm_kill_self_worker"
    bl_label = "Kill this worker."
    bl_description = "Remove this computer's worker registration."

    def invoke(self, context, event):
        if not worker_rendering():
            return self.execute(context)
        # Rendering right now: the artist decides what happens to it.
        set_pending_action(
            PipelineAction(
                title="Stop this worker",
                message=(
                    "This machine is rendering a job right now.\n\n"
                    "After this frame: the frame it's on is written, then the "
                    "worker stops -- the job carries on with its other machines "
                    "(or is sent out again for the frames left).\n"
                    "Stop now: the render is interrupted, its frame in progress "
                    "is lost and freed for another machine."
                ),
                severity="warning",
                choices=[
                    (
                        "After this frame",
                        lambda: stop_worker(kill_render=False),
                        "Write the frame in progress, then stop the worker.",
                    ),
                    (
                        "Stop now",
                        lambda: stop_worker(kill_render=True),
                        "Interrupt the render now and stop the worker.",
                    ),
                ],
            )
        )
        return bpy.ops.m_pipeline.action_popup("INVOKE_DEFAULT")

    def execute(self, context):
        if worker_rendering():
            stop_worker(kill_render=True)  # scripted call: no popup to ask
            self.report({"INFO"}, "Render stopped, worker stopped.")
            return {"FINISHED"}
        if kill_worker():
            self.report({"INFO"}, "This machine is no longer a farm worker.")
            return {"FINISHED"}
        self.report(
            {"WARNING"}, "This worker entry belongs to another machine/process."
        )
        return {"CANCELLED"}


class M_PIPELINE_OT_farm_cancel_job(bpy.types.Operator):
    """Cancel a job's in-progress render, on every machine currently working
    on it (Jobs tab) or on just one (Workers tab, via target_uuid)."""

    bl_idname = "m_pipeline.farm_cancel_job"
    bl_label = "Cancel"
    bl_description = "Cancel this job's render."

    job_id: bpy.props.StringProperty()
    target_uuid: bpy.props.StringProperty(default="")

    def execute(self, context):
        if self.target_uuid:
            machines = [self.target_uuid]
        else:
            job_path = ConfigCache.get_path("farm_actives") / f"{self.job_id}.json"
            try:
                with locked_json(job_path, read_only=True) as box:
                    data = box["data"] or {}
            except PipelineError as e:
                return report_error(self, "farm_cancel_job", e)
            machines = data.get("used_machines", [])

        # No machine on it (its chunks waiting for one) still cancels the
        # job: cancel_pending_renders() fails it at once.
        user = get_user(context)
        # A machine that hasn't picked up its render yet has nothing to
        # kill: its request is withdrawn instead (else it renders later).
        running = cancel_pending_renders(
            self.job_id, machines, whole_job=not self.target_uuid
        )
        for uuid in running:
            job_cancel_request(job_id=self.job_id, target_uuid=uuid, user=user)
        self.report({"INFO"}, f"Cancel requested ({len(machines)} machine(s)).")
        return {"FINISHED"}


class M_PIPELINE_OT_farm_archive_job(bpy.types.Operator):
    """Move a finished/failed job (and its render logs) out of the active queue."""

    bl_idname = "m_pipeline.farm_archive_job"
    bl_label = "Archive"
    bl_description = "Move this job's file and logs to queue/archives/."

    job_id: bpy.props.StringProperty()

    def execute(self, context):
        job_path = ConfigCache.get_path("farm_actives") / f"{self.job_id}.json"
        try:
            archive(job_path)
        except OSError as e:
            log("ERROR", "farm_archive_job", str(e))
            self.report({"ERROR"}, f"Could not archive job: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Job archived.")
        return {"FINISHED"}


class M_PIPELINE_OT_farm_remove_job(bpy.types.Operator):
    """Take a job out of the queue before anything renders (Farm
    monitoring's right-click)."""

    bl_idname = "m_pipeline.farm_remove_job"
    bl_label = "Remove from queue"
    bl_description = "Take this job out of the queue: nothing of it rendered yet."

    job_id: bpy.props.StringProperty()
    pending: bpy.props.BoolProperty(options={"HIDDEN"})

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            removed = remove_waiting_job(self.job_id, self.pending)
        except (OSError, PipelineError) as e:
            self.report({"ERROR"}, f"Could not remove the job: {e}")
            return {"CANCELLED"}
        if not removed:
            self.report({"WARNING"}, "It started meanwhile: cancel it instead.")
            return {"CANCELLED"}
        log("INFO", "farm", f"Job {self.job_id} removed from the queue by {get_user(context)}.")
        return {"FINISHED"}


class M_PIPELINE_OT_farm_archive_jobs(bpy.types.Operator):
    """Archive every finished, or every failed, job of Farm monitoring."""

    bl_idname = "m_pipeline.farm_archive_jobs"
    bl_label = "Archive all"

    state: bpy.props.EnumProperty(
        items=[("finished", "Finished", ""), ("failed", "Failed", "")]
    )

    @classmethod
    def description(cls, context, properties):
        return f"Archive every {properties.state} job (moved to queue/archives/)."

    def execute(self, context):
        actives = ConfigCache.get_path("farm_actives")
        cache = get_monitor_cache()
        archived = set()
        for job in cache["jobs"]:
            if job["stage"] == "pending" or job_state(job["stage"]) != self.state:
                continue
            try:
                archive(actives / f"{job['job_id']}.json")
                archived.add(job["job_id"])
            except FileNotFoundError:
                # Archived meanwhile (its 24 h auto-archive, another
                # machine's click): the list was older than the queue.
                archived.add(job["job_id"])
            except OSError as e:
                log("ERROR", "farm_archive_jobs", f"{job['job_id']}: {e}")
        # Off the list now, not at the next refresh.
        cache["jobs"] = [j for j in cache["jobs"] if j["job_id"] not in archived]
        self.report({"INFO"}, f"{len(archived)} job(s) archived.")
        return {"FINISHED"}


class M_PIPELINE_OT_farm_retry_job(bpy.types.Operator):
    """Run a failed job again from the stage that failed."""

    bl_idname = "m_pipeline.farm_retry_job"
    bl_label = "Retry"
    bl_description = (
        "Run this job again from the stage that failed: same output folder, "
        "frames and preset (no new version). A render keeps the frames "
        "already rendered."
    )

    job_id: bpy.props.StringProperty()

    def execute(self, context):
        return _redo_job(
            self,
            failed_stage,
            lambda data: retry_job(data, get_active_project_root()),
            "This job didn't fail: nothing to retry.",
            "retry",
            lambda target: f"Job sent back to {target}.",
        )


class M_PIPELINE_OT_farm_recompile_job(bpy.types.Operator):
    """Compile a finished job's video again from the frames already on disk."""

    bl_idname = "m_pipeline.farm_recompile_job"
    bl_label = "Recompile"
    bl_description = (
        "Compile this job's video again from the frames already rendered: "
        "no render, no worker -- just ffmpeg on the monitor's machine. The "
        "render goes back to To check once done."
    )

    job_id: bpy.props.StringProperty()

    def execute(self, context):
        return _redo_job(
            self,
            recompilable,
            recompile_job,
            "Only a finished render can be recompiled.",
            "recompile",
            lambda _: "Compilation requested again.",
        )


def _redo_job(op, can, redo, refused: str, verb: str, done) -> set:
    """Retry / Recompile op.job_id: back from the archives first if it was
    archived by hand (can() it?), redo(data) under its lock -- written when
    it says something. refused: what nothing to do reads; done(result) the
    report."""
    job_path = ConfigCache.get_path("farm_actives") / f"{op.job_id}.json"
    archived = ConfigCache.get_path("farm_archives") / job_path.name
    try:
        if not job_path.exists() and archived.exists():
            if not can(read_json_quiet(archived) or {}):
                op.report({"WARNING"}, refused)
                return {"CANCELLED"}
            archived.rename(job_path)  # archived by hand: back in the queue
        with locked_json(job_path) as box:
            data = box["data"] or {}
            local = data.get("local")
            if local and local != get_machine_id():
                # Render here: only its machine moves it on.
                op.report({"WARNING"}, f"Rendered on {data.get('machine') or local[:8]} (Local): {verb} it from there.")
                return {"CANCELLED"}
            if local:
                reserve_this_machine()
            result = redo(data)
            if result:
                box["action"] = "to_write"
    except Exception as e:
        log("ERROR", f"farm_{verb}_job", str(e))
        op.report({"ERROR"}, f"Could not {verb} the job: {e}")
        return {"CANCELLED"}
    if not result:
        op.report({"WARNING"}, refused)
        return {"CANCELLED"}
    if monitoring_detail("job") == op.job_id:
        load_job_details(op.job_id)
    op.report({"INFO"}, done(result))
    return {"FINISHED"}


