"""Farm operators: launch/kill the monitor, submit render requests, self as worker, farm monitor UI."""

import datetime
import os
from pathlib import Path

import bpy

from ..farm import (
    archive,
    failed_stage,
    get_monitor_cache,
    job_cancel_request,
    job_request,
    job_state,
    kill_worker,
    launch_monitor,
    launch_worker,
    load_job_details,
    monitor_age_status,
    monitor_last_tick,
    recompilable,
    recompile_job,
    refresh_monitor_status,
    register_popup_region,
    register_refresh_timer,
    request_monitor_kill,
    request_worker_stop,
    retry_job,
    scan_workers,
    stop_worker,
    unregister_refresh_timer,
    worker_rendering,
)
from ..lib import (
    ConfigCache,
    PipelineAction,
    PipelineError,
    asset_folder_items,
    cached_scandir,
    get_active_project_root,
    get_folder,
    get_machine_id,
    get_user,
    json_get,
    locked_json,
    log,
    parse_filename,
    prefix_items,
    read_json_quiet,
    resolve_ffmpeg,
    resolve_version_file,
    sequence_items,
    set_pending_action,
    shot_items,
    shots_in_segment,
    version_items,
)
from ..panels import (
    draw_farm_job_details,
    draw_farm_jobs,
    draw_farm_workers,
    popup_width,
)

_workers_items_cache: list[tuple[str, str, str]] = []
_pre_render_scripts: list[tuple[str, str, str]] = []


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

        _workers_items_cache[:] = items
        return _workers_items_cache

    except Exception as e:
        log("WARNING", "farm", f"Could not list machines: {e}")
        _workers_items_cache[:] = [("NONE", "No worker found", "")]
        return _workers_items_cache


def _get_pre_render_scripts(self, context):
    """Enum items for the pre-render script picker: every .py/.json preset
    directly under config/presets/ (matches apply_custom_preset()'s lookup),
    excluding asset_file_preset.py and the ffmpeg_presets/ subfolder."""
    global _pre_render_scripts
    items = [("", "None", "Don't execute script before render.")]
    try:
        presets_dir = ConfigCache.get_path("presets")
        names = set()
        # cached_scandir(): this enum is re-evaluated on every redraw of the
        # Render dialog; DirEntry.is_file() needs no extra stat.
        for f in cached_scandir(presets_dir):
            suffix = Path(f.name).suffix
            if (
                f.is_file()
                and suffix in (".py", ".json")
                and f.name != "asset_file_preset.py"
            ):
                names.add(Path(f.name).stem)
        for name in sorted(names):
            items.append((name, name, f"Apply preset '{name}' before render."))
    except Exception as e:
        log("WARNING", "farm", f"Could not list pre-render presets: {e}")
    _pre_render_scripts = items
    return _pre_render_scripts


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
                        ("Cancel", None, "Don't launch the monitor."),
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
                        monitor_last_tick(lock_path, data) or datetime.datetime.min
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

    file_type: bpy.props.EnumProperty(
        items=[("asset", "Asset / Library", ""), ("shot", "Shot", "")],
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

    priority: bpy.props.IntProperty(name="Priority", default=10)
    render_mode: bpy.props.EnumProperty(
        items=[
            ("auto", "Auto", "Placeholder first, fallback to single on collision"),
            ("single", "Single", "One machine, whole shot"),
            ("placeholder", "Placeholder", "All free machines, self-arbitrated"),
        ],
        name="Render Mode",
        default="auto",
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
        self.project_root = str(get_active_project_root())
        if self.filepath:
            self._populate_subshots(context)
            if event.ctrl:
                return self.single(context)

            else:
                return context.window_manager.invoke_props_dialog(
                    self, width=300, confirm_text="Submit"
                )
        else:
            return context.window_manager.invoke_props_dialog(
                self, width=300, confirm_text="Submit all"
            )

    def _panel_setting(self, context, col, is_block=False):
        row = col.row(align=False)
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
        col.prop_menu_enum(
            self, "assigned_machines", text="Assigned machines (Empty : auto)"
        )
        col.separator()
        col.prop_menu_enum(self, "pre_render_script", text="Pre_render script")

    def _draw_subshots(self, layout, subshots):
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

            ### list
            if len(context.scene.pipeline_farm_list) > 0:
                layout.separator(factor=2)
                box = layout.box().column(align=True)
                box.label(text="Render list :")
                box.separator(type="LINE", factor=0.5)
                box.separator()
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
        rides along as this job's only_shots."""
        job_request(
            filepath,
            user=user,
            priority=self.priority,
            render_mode=self.render_mode,
            assigned_machines=list(self.assigned_machines),
            increment=self.increment,
            prerender_script=self.pre_render_script,
            overrided_frame_range=(start, end),
            only_shots=sorted(only) if only else None,
        )

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

    def single(self, context):
        user = get_user(context)
        start, end = self._override_strings()
        subshots = context.window_manager.render_subshots

        only = None
        if subshots:
            only = {s.shot_number for s in subshots if s.include}
            if not only:
                self.report({"ERROR"}, "No shot selected to render.")
                return {"CANCELLED"}

        try:
            self._submit_for_filepath(self.filepath, user, start, end, only)
        except PipelineError as e:
            log(e.level, "farm_request_render", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        context.scene.pipeline_farm_list.clear()
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
                    "Stop the render too: it's interrupted now, the job carries "
                    "on with its other machines (or is sent out again for the "
                    "frames left).\n"
                    "Let it finish: no new render is picked up, the worker "
                    "stops once this one is done."
                ),
                severity="warning",
                choices=[
                    (
                        "Stop the render too",
                        lambda: stop_worker(kill_render=True),
                        "Interrupt the render now and stop the worker.",
                    ),
                    (
                        "Let it finish",
                        lambda: stop_worker(kill_render=False),
                        "Finish the current render, then stop the worker.",
                    ),
                    ("Cancel", None, "Keep the worker running."),
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


class M_PIPELINE_OT_farm_stop_worker(bpy.types.Operator):
    """Stop any machine's worker from the Workers tab."""

    bl_idname = "m_pipeline.farm_stop_worker"
    bl_label = "Stop worker"
    bl_description = (
        "Stop this machine's worker. If it's rendering, choose whether its "
        "render is interrupted or finishes first."
    )

    target_uuid: bpy.props.StringProperty()
    machine: bpy.props.StringProperty()
    busy: bpy.props.BoolProperty()
    kill_render: bpy.props.BoolProperty(
        description="Scripted call only: interrupt its render in progress"
    )

    def invoke(self, context, event):
        if self.target_uuid == get_machine_id():
            return bpy.ops.m_pipeline.farm_kill_self_worker("INVOKE_DEFAULT")
        if not self.busy:
            return self.execute(context)
        user = get_user(context)
        uuid, name = self.target_uuid, self.machine or self.target_uuid[:8]
        set_pending_action(
            PipelineAction(
                title=f"Stop worker {name}",
                message=(
                    f"{name} is rendering a job right now.\n\n"
                    "Stop the render too: it's interrupted now, the job carries "
                    "on with its other machines (or is sent out again for the "
                    "frames left).\n"
                    "Let it finish: no new render is picked up, the worker "
                    "stops once this one is done.\n\n"
                    "Takes effect on its next tick (about 10 s)."
                ),
                severity="warning",
                choices=[
                    (
                        "Stop the render too",
                        lambda: request_worker_stop(uuid, True, user),
                        "Interrupt its render now and stop the worker.",
                    ),
                    (
                        "Let it finish",
                        lambda: request_worker_stop(uuid, False, user),
                        "Finish its current render, then stop the worker.",
                    ),
                    ("Cancel", None, "Keep the worker running."),
                ],
            )
        )
        return bpy.ops.m_pipeline.action_popup("INVOKE_DEFAULT")

    def execute(self, context):
        if not self.target_uuid:
            return {"CANCELLED"}
        request_worker_stop(self.target_uuid, self.kill_render, get_user(context))
        self.report(
            {"INFO"},
            f"Stop requested for {self.machine or self.target_uuid[:8]} (next tick).",
        )
        return {"FINISHED"}


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
                log(e.level, "farm_cancel_job", e.message)
                self.report({e.level}, e.message)
                return {"CANCELLED"}
            machines = data.get("used_machines", [])

        if not machines:
            self.report({"WARNING"}, "No machine currently assigned to this job.")
            return {"CANCELLED"}

        user = get_user(context)
        for uuid in machines:
            job_cancel_request(job_id=self.job_id, target_uuid=uuid, user=user)
        self.report({"INFO"}, f"Cancel request sent ({len(machines)} machine(s)).")
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


class M_PIPELINE_OT_farm_archive_jobs(bpy.types.Operator):
    """Archive every finished, or every failed, job of the Farm popup."""

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
        actives = ConfigCache.get_path("farm_actives")
        job_path = actives / f"{self.job_id}.json"
        archived = ConfigCache.get_path("farm_archives") / job_path.name
        try:
            if not job_path.exists() and archived.exists():
                if not failed_stage(read_json_quiet(archived) or {}):
                    self.report({"WARNING"}, "This job didn't fail: nothing to retry.")
                    return {"CANCELLED"}
                archived.rename(job_path)  # archived by hand: back in the queue
            with locked_json(job_path) as box:
                data = box["data"] or {}
                target = retry_job(data, get_active_project_root())
                if target:
                    box["action"] = "to_write"
        except Exception as e:
            log("ERROR", "farm_retry_job", str(e))
            self.report({"ERROR"}, f"Could not retry the job: {e}")
            return {"CANCELLED"}
        if not target:
            self.report({"WARNING"}, "This job didn't fail: nothing to retry.")
            return {"CANCELLED"}
        if context.window_manager.farm_job_selected == self.job_id:
            load_job_details(self.job_id)
        self.report({"INFO"}, f"Job sent back to {target}.")
        return {"FINISHED"}


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
        actives = ConfigCache.get_path("farm_actives")
        job_path = actives / f"{self.job_id}.json"
        archived = ConfigCache.get_path("farm_archives") / job_path.name
        done = False
        try:
            if not job_path.exists() and archived.exists():
                if not recompilable(read_json_quiet(archived) or {}):
                    self.report({"WARNING"}, "Only a finished render can be recompiled.")
                    return {"CANCELLED"}
                archived.rename(job_path)  # archived by hand: back in the queue
            with locked_json(job_path) as box:
                data = box["data"] or {}
                done = recompile_job(data)
                if done:
                    box["action"] = "to_write"
        except Exception as e:
            log("ERROR", "farm_recompile_job", str(e))
            self.report({"ERROR"}, f"Could not recompile the job: {e}")
            return {"CANCELLED"}
        if not done:
            self.report({"WARNING"}, "Only a finished render can be recompiled.")
            return {"CANCELLED"}
        if context.window_manager.farm_job_selected == self.job_id:
            load_job_details(self.job_id)
        self.report({"INFO"}, "Compilation requested again.")
        return {"FINISHED"}


class M_PIPELINE_OT_farm_job_details(bpy.types.Operator):
    """Farm monitoring popup: switch to one job's detail view, or back to
    the list. Reads the job file here, once per click -- never in draw()."""

    bl_idname = "m_pipeline.farm_job_details"
    bl_label = ""
    bl_description = "Show this job's details."

    job_id: bpy.props.StringProperty()
    reload: bpy.props.BoolProperty(options={"SKIP_SAVE"})

    def execute(self, context):
        wm = context.window_manager
        if wm.farm_job_selected == self.job_id and not self.reload:
            wm.farm_job_selected = ""  # back to the list
            return {"FINISHED"}
        if load_job_details(self.job_id) is None:
            wm.farm_job_selected = ""
            self.report({"WARNING"}, "Job file not found (deleted?).")
            return {"CANCELLED"}
        wm.farm_job_selected = self.job_id
        return {"FINISHED"}


def _back_to_first_page(self, context):
    self.page = 1


class M_PIPELINE_OT_farm_monitor(bpy.types.Operator):
    """Popup dashboard: active jobs and worker machines, filterable."""

    bl_idname = "m_pipeline.farm_monitor"
    bl_label = ""
    bl_description = "Show a popup view of farm."

    view: bpy.props.EnumProperty(
        items=[("jobs", "Jobs", ""), ("workers", "Workers", "")],
        default="jobs",
    )

    # Jobs view filters. A filter change goes back to page 1.
    state: bpy.props.EnumProperty(
        items=[
            ("all", "All", "Every job"),
            ("running", "Running", "Pending, queued or in progress"),
            ("finished", "Finished", "Finished jobs"),
            ("failed", "Failed", "Failed jobs"),
        ],
        default="all",
        update=_back_to_first_page,
    )
    only_mine: bpy.props.BoolProperty(
        name="",
        default=False,
        description="Only the jobs I submitted",
        update=_back_to_first_page,
    )
    search: bpy.props.StringProperty(
        name="",
        description="Filter by file name or shot",
        options={"SKIP_SAVE"},
        update=_back_to_first_page,
    )
    # SKIP_SAVE: reopen on page 1, see M_PIPELINE_OT_tracking_monitor.page.
    page: bpy.props.IntProperty(default=1, min=1, options={"SKIP_SAVE"})
    PAGE_SIZE = 8

    def invoke(self, context, event):
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}

        context.window_manager.farm_job_selected = ""  # always open on the list
        register_refresh_timer()

        return context.window_manager.invoke_props_dialog(
            self, width=popup_width(context)
        )

    def execute(self, context):
        unregister_refresh_timer()
        return {"FINISHED"}

    def cancel(self, context):
        unregister_refresh_timer()

    def draw(self, context):
        # context.region_popup (Blender 4.2+) only exists while this popup is
        # actually being drawn -- registering it here (not in invoke()) lets
        # _refresh_tick force this exact popup's redraw on every timer tick.
        register_popup_region(getattr(context, "region_popup", None))

        layout = self.layout
        if context.window_manager.farm_job_selected:
            draw_farm_job_details(layout.box(), context)
            return

        filter_box = layout.box()
        filters = filter_box.split(factor=0.5)
        filters.label(text="Filters", icon="FILTER")
        filters_btn = filters.row()
        filters_btn.prop(self, "view", expand=True)
        if self.view == "jobs":
            job_filters = filter_box.split(factor=0.5)
            job_filters.prop(self, "search", text="", icon="VIEWZOOM")
            job_btn = job_filters.row()
            job_btn.prop(self, "state", expand=True)
            job_btn.prop(self, "only_mine", text="Mine", icon="USER")

        box = layout.box()
        if self.view == "jobs":
            draw_farm_jobs(self, box)
        else:
            draw_farm_workers(box)
