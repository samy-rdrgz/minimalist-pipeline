"""Farm management panel in the 3D View sidebar."""

import datetime
from pathlib import Path

import bpy

from ..farm import (
    RETRYABLE_STAGES,
    failed_stage,
    get_job_details,
    get_job_details_logs,
    get_job_details_path,
    get_monitor_cache,
    job_state,
    machine_for_frame,
    recompilable,
    this_instance_is_worker,
)
from ..lib import (
    addon_pref,
    draw_box_tip,
    draw_pager,
    get_active_project_root,
    get_user,
    monitoring_detail,
    paginate,
    rows_that_fit,
)

FIRST_COLUMN = 0.4
# What Farm monitoring's window holds besides the Jobs rows (filters, list
# header, footer, margins), in widget units -- see rows_that_fit().
_JOBS_RESERVED_UNITS = 7.5
# Same for the Workers view: one row of filters, no footer.
_WORKERS_RESERVED_UNITS = 5.0


class M_PIPELINE_PT_farm_panel(bpy.types.Panel):
    """Farm monitoring."""

    bl_label = ""
    bl_idname = "M_PIPELINE_PT_farm_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pipeline"

    bl_options = {"HEADER_LAYOUT_EXPAND", "DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return addon_pref(context) is not None and get_active_project_root()

    def draw_header(self, context):
        layout = self.layout.row(align=True)
        layout.separator(factor=0.4)
        # A button opening Farm monitoring, its text left-aligned like a label.
        status_row = layout.row(align=True)
        status_row.alignment = "LEFT"

        # From the status cache (refreshed by _status_tick() every 10 s),
        # never monitor.lock.exists() here: a disk call per redraw is a
        # network round-trip on a share, even with this panel collapsed.
        is_monitor = get_monitor_cache().get("status") not in ("not running", "unknown")

        if not is_monitor:
            status_row.operator(
                "m_pipeline.farm_monitor",
                text="Farm : not running",
                icon="GHOST_DISABLED",
                emboss=False,
            )
            layout.operator(
                "m_pipeline.farm_launch_monitor",
                text="",
                icon="TRIA_RIGHT",
                emboss=False,
            )

        else:
            cache = get_monitor_cache()
            status = cache["status"]
            icons = {
                "running": "CHECKMARK",
                "stale": "FREEZE",
                "dead": "GHOST_DISABLED",
            }

            labels = {
                "running": "Farm : Running",
                "stale": "Farm : Stale",
                "dead": "Farm : Dead",
                "unknown": "Farm : ...",
            }
            status_row.operator(
                "m_pipeline.farm_monitor",
                text=labels.get(status, "Farm : ..."),
                icon=icons.get(status, "GHOST_DISABLED"),
                emboss=False,
            )
            if status != "running":
                layout.operator(
                    "m_pipeline.farm_launch_monitor",
                    text="",
                    icon="TRIA_RIGHT",
                    emboss=False,
                )
        layout.separator(factor=1.5)

    def draw(self, context):
        layout = self.layout.column(align=True)

        draw_box_tip(
            layout,
            context,
            "Monitor runs the render queue (one per project). Worker "
            "means this machine renders jobs. Both coordinate through "
            "files in the project (no server, no network setup).",
        )

        layout.operator("m_pipeline.farm_monitor", text="Farm monitor", icon="WORKSPACE")
        layout.separator()

        # Status cache, not monitor.lock.exists() -- see draw_header().
        is_monitor = get_monitor_cache().get("status") not in ("not running", "unknown")

        if is_monitor:
            cache = get_monitor_cache()
            status = cache["status"]

            if status in ("running", "stale"):
                layout.operator(
                    "m_pipeline.farm_kill_monitor", text="Kill farm", icon="X"
                )
            if status not in ("running", "stale"):
                layout.operator(
                    "m_pipeline.farm_launch_monitor",
                    text="Launch farm",
                    icon="TRIA_RIGHT",
                )

            last_seen = (
                cache["last_tick"].strftime("%H:%M:%S") if cache["last_tick"] else "?"
            )

            labels = {
                "running": f"Running {cache['lock_user']} @ {cache['lock_machine']}",
                "stale": f"Stale: {cache['lock_user']} (last seen {last_seen})",
                "dead": f"Dead: {cache['lock_user']} (last seen {last_seen})",
                "unknown": "...",
            }
            info = layout.row()
            info.active = False
            info.label(text=labels.get(status, "..."), icon="DOT")
        else:
            layout.operator(
                "m_pipeline.farm_launch_monitor", text="Launch farm", icon="TRIA_RIGHT"
            )
        if this_instance_is_worker():
            layout.operator(
                "m_pipeline.farm_kill_self_worker", text="Stop this worker", icon="X"
            )
        else:
            layout.operator(
                "m_pipeline.farm_add_self_worker",
                text="Add this machine as worker",
                icon="ADD",
            )


def job_icon(stage: str) -> str:
    """A job stage's icon -- Farm monitoring's list, and Project monitoring's
    Farm column."""
    if stage == "pending":
        return "SORTTIME"
    if stage == "queued":
        return "DECORATE_ANIMATE"
    if job_state(stage) == "finished":
        return "KEYTYPE_JITTER_VEC"
    if stage.endswith("_finished"):
        return "HANDLETYPE_FREE_VEC"
    if stage.endswith("failed"):
        return "KEYTYPE_EXTREME_VEC"
    return "KEYTYPE_BREAKDOWN_VEC"


def _job_time(iso: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None


def _duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def machine_label(uuid: str, recorded: str = "") -> str:
    """A machine as people know it: its worker's user and id ("Alice
    (a1b2c3d4)") -- a machine is only ever named by its id, no hostname
    read. Else the name recorded with the render, else the id. Memory
    only (the monitor cache's workers): draw()-safe."""
    worker = (get_monitor_cache().get("workers") or {}).get(uuid) or {}
    if worker.get("user"):
        return f"{worker['user']} ({worker.get('machine') or uuid[:8]})"
    return worker.get("machine") or recorded or uuid[:8]


def draw_frame_lookup(layout, renders: list) -> None:
    """ "Frame [n] -> the machine that wrote it", for renders: (label, its
    frame_machines, its machine_seconds) each -- a block's shots, one field
    for all (their ranges don't overlap). Out of every range: the ranges.
    Memory only: draw()-safe."""
    renders = [r for r in renders if r[1] and r[1].get("frames")]
    if not renders:
        return
    wm = bpy.context.window_manager
    layout.prop(wm, "farm_frame_lookup", text="Frame")
    # The answer on its own row: next to the field, in an aligned row, it
    # only got what the field left -- the machine's name cut to "WOR...02".
    answer = layout.row()
    answer.alignment = "LEFT"
    for label, record, seconds in renders:
        found = machine_for_frame(record, wm.farm_frame_lookup)
        if found:
            uuid, name = found
            if uuid:
                name = machine_label(uuid, name)
            pace = (seconds or {}).get(uuid)
            text = f"{label}rendered by {name}"
            answer.label(text=text + (f"  ({_duration(pace)}/frame)" if pace else ""))
            return
    answer.label(
        text=", ".join(
            f"{label}{r['start']} - {r['start'] + len(r['frames']) - 1}"
            for label, r, _ in renders
        )
    )


def _job_matches(self, job: dict, user: str) -> bool:
    if self.state != "all" and job_state(job["stage"]) != self.state:
        return False
    if self.only_mine and job.get("user") != user:
        return False
    search = self.search.strip().lower()
    if search:
        name = f"{Path(job['filepath']).name} {job.get('shot_override', '')}"
        if search not in name.lower():
            return False
    return True


def draw_farm_jobs(self, context, layout):
    """Farm monitoring's "Jobs" view: every active job, its stage and
    progress -- filtered by self (WindowManager.pipeline_farm_monitoring),
    paged like draw_monitor_table()."""
    cache = get_monitor_cache()

    title = layout.split(factor=FIRST_COLUMN)
    title.active = False
    title.row().label(text="Jobs", icon="BLANK1")
    title.row().label(text="Status")
    layout.separator(factor=1)

    user = get_user()
    matches = [j for j in cache["jobs"] if _job_matches(self, j, user)]
    # Newest submit first: the order the reader thread lists files in is
    # arbitrary, it would shuffle jobs between refreshes.
    matches.sort(key=lambda j: j.get("submitted_at") or "", reverse=True)

    total = len(matches)
    per_page = rows_that_fit(context, _JOBS_RESERVED_UNITS)
    filters = (self.state, self.only_mine, self.search.strip().lower())
    shown, page, pages = paginate("farm", matches, per_page, filters)
    for j in shown + [None] * (per_page - len(shown)):
        row = layout.column()
        # Line *after* the row, never before it inside an aligned column:
        # that glues it to the text -- same spacing as draw_monitor_table().
        layout.separator(factor=0.5, type="LINE")
        if j is None:  # a page's padding
            row.label(text="", icon="BLANK1")
            continue
        row = row.split(factor=FIRST_COLUMN)
        name = Path(j["filepath"]).name
        stage = j["stage"]
        # A split block's jobs share its filepath: shot_override marks
        # each child, split_finished the parent.
        if j.get("shot_override"):
            name = f"{name}  [{j['shot_override']}]"
        elif stage == "split_finished":
            name = f"{name}  [split]"

        elapsed = j["elapsed_seconds"]
        elapsed_str = _duration(elapsed)

        icon = job_icon(stage)

        if stage == "pending" and j.get("blocked_by_stage"):
            text = (
                f"waiting for this shot's job in progress "
                f"({j['blocked_by_stage']}) - {elapsed_str}"
            )
        elif stage == "pending":
            text = f"waiting for monitor - {elapsed_str}"
        elif job_state(stage) in ("finished", "failed"):
            # When it ended, not elapsed: stage_at never moves again.
            at = _job_time(j["stage_at"])
            text = f"{stage} - {at:%d/%m %H:%M}" if at else stage

        elif j["frames_total"] > 0:
            pct = j["frames_done"] / j["frames_total"]
            # Frames left over the pace of the machines on it now
            # (_time_left(), farm/loop.py) -- else, nothing timed yet,
            # elapsed / pct as the estimated total.
            left = j.get("time_left")
            if left is None and pct > 0:
                left = elapsed / pct - elapsed
            if left is not None:
                remaining_str = f"≃ {_duration(left)} remaining"
            else:
                remaining_str = "estimating..."
            text = (
                f"{stage} - {j['frames_done']}/{j['frames_total']} ({pct:.0%})"
                f" - {elapsed_str} ({remaining_str})"
            )

        else:
            text = f"{stage} - {elapsed_str}"

        if j.get("skipped_shots"):
            text += f" -- missing: {', '.join(j['skipped_shots'])}"
        if j.get("absorbed_shots"):
            text += f" -- absorbed: {', '.join(j['absorbed_shots'])}"

        name_row = row.row()
        name_row.alignment = "LEFT"
        if stage == "pending" and j.get("blocked_by_stage"):
            # Same job id as the job holding it back: open that one.
            name_row.operator(
                "m_pipeline.farm_job_details", text=name, icon=icon, emboss=False
            ).job_id = j["job_id"]
        elif stage == "pending":
            name_row.label(text=name, icon=icon)  # no job file yet
        else:
            name_row.operator(
                "m_pipeline.farm_job_details", text=name, icon=icon, emboss=False
            ).job_id = j["job_id"]
        status = row.row()
        status.label(text=text)
        if j.get("output_dir"):
            op = status.operator(
                "wm.open_folder", text="", icon="FILE_FOLDER", emboss=False
            )
            op.filepath = j["output_dir"]
            op.custom_tooltip = "Open this job's render folder"
        if stage == "render_start":
            status.operator(
                "m_pipeline.farm_cancel_job", text="", icon="X", emboss=False
            ).job_id = j["job_id"]
        elif job_state(stage) in ("finished", "failed"):
            if stage in RETRYABLE_STAGES:
                status.operator(
                    "m_pipeline.farm_retry_job",
                    text="",
                    icon="LOOP_BACK",
                    emboss=False,
                ).job_id = j["job_id"]
            elif stage == "finished" and j.get("output_dir"):
                status.operator(
                    "m_pipeline.farm_recompile_job",
                    text="",
                    icon="FILE_MOVIE",
                    emboss=False,
                ).job_id = j["job_id"]
            status.operator(
                "m_pipeline.farm_archive_job",
                text="",
                icon="CHECKMARK",
                emboss=False,
            ).job_id = j["job_id"]

    footer = layout.row()
    footer.active = False
    if total == 0:
        footer.label(
            text="No job with this filter" if cache["jobs"] else "No job",
            icon="BLANK1",
        )
    else:
        footer.label(text=f"{total} job(s)", icon="BLANK1")
    # Every job of that state, not just this filter's.
    bulk = footer.row(align=True)
    bulk.alignment = "RIGHT"
    for state in ("finished", "failed"):
        count = sum(
            1
            for j in cache["jobs"]
            if j["stage"] != "pending" and job_state(j["stage"]) == state
        )
        if count:
            bulk.operator(
                "m_pipeline.farm_archive_jobs",
                text=f"Archive {state} ({count})",
                icon="CHECKMARK",
            ).state = state
    draw_pager(footer, self, page, pages)


def _job_name(job: dict) -> str:
    """A job's name as the Jobs view lists it: its file, plus the shot of a
    split block's child."""
    name = Path(job.get("filepath", "")).name
    if job.get("shot_override"):
        name = f"{name}  [{job['shot_override']}]"
    return name


def _draw_job_link(layout, job_id: str, text: str) -> None:
    """text, clicked to open job_id's details -- like a name in the Jobs
    view. A plain label without a job id."""
    row = layout.row()
    row.alignment = "LEFT"
    if job_id:
        op = row.operator("m_pipeline.farm_job_details", text=text, emboss=False)
        op.job_id = job_id
    else:
        row.label(text=text)


def draw_farm_workers(context, layout):
    """M_PIPELINE_OT_farm_monitor's "Workers" view: every known machine, idle
    or what it's currently rendering -- padded with blank rows to the
    window's height, like the Jobs view (no pages: a farm has few machines,
    past the window the region scrolls)."""
    title_list = layout.split(factor=FIRST_COLUMN)
    title_list.active = False
    btn = title_list.row()
    btn.alignment = "LEFT"
    btn.label(text="Machine", icon="BLANK1")
    if this_instance_is_worker():
        btn.operator(
            "m_pipeline.farm_kill_self_worker", text="Kill this worker", icon="X"
        )
    else:
        btn.operator(
            "m_pipeline.farm_add_self_worker", text="Add this machine", icon="ADD"
        )

    title_list.row().label(text="Jobs")
    layout.separator(factor=1)

    monitor_cache = get_monitor_cache()
    # From the snapshot the refresh timer builds (_apply_farm_snapshot()), never
    # scan_workers() here: draw() reruns on every hover of the popup, and
    # each worker file read is a network round-trip on a share.
    workers = monitor_cache.get("workers") or {}

    machines = list(workers.values())
    # job_id -> its Jobs view entry, for the names below. Never a pending
    # one: a re-submit waiting in incoming/ shares its active job's id.
    jobs_by_id = {
        job["job_id"]: job
        for job in monitor_cache.get("jobs") or []
        if job.get("stage") != "pending"
    }

    row = layout.column()
    layout.separator(factor=0.5, type="LINE")
    # uuid -> job_id, to let a busy worker's row cancel just its own share.
    # Empty when the monitor is stopped: a worker file can still say busy.
    uuid_to_job = {}
    if monitor_cache.get("status") == "not running":
        row.label(
            text="Farm not running",
            icon="QUIT",
        )
    else:
        monitor_label = (
            f"Farm host: {monitor_cache['lock_machine']}"
            if monitor_cache.get("lock_machine")
            else "Farm host"
        )
        monitor_jobs = monitor_cache.get("jobs") or []
        # Only the process the host is running right now, same definition
        # as _finish_job_processes() (farm/queue.py) -- not render_start:
        # that's the workers' part, listed under each machine below.
        running_jobs = [
            job
            for job in monitor_jobs
            if job.get("stage", "").endswith("_start")
            and job.get("stage") != "render_start"
        ]

        status = monitor_cache.get("status")
        split = row.split(factor=FIRST_COLUMN)
        if status in ("stale", "dead"):
            # Its jobs' stages are frozen where it left them: never list
            # them as running. Same icons as the sidebar's header.
            split.row().label(
                text=monitor_label,
                icon="FREEZE" if status == "stale" else "GHOST_DISABLED",
            )
            last = monitor_cache.get("last_tick")
            seen = f" (last seen {last:%d/%m %H:%M:%S})" if last else ""
            split.row().label(text=status + seen)
        else:
            split.row().label(
                text=monitor_label,
                icon="KEYTYPE_BREAKDOWN_VEC" if running_jobs else "KEYTYPE_JITTER_VEC",
            )
            jobs_col = split.column(align=True)
            if running_jobs:
                for job in running_jobs:
                    _draw_job_link(
                        jobs_col, job["job_id"], f"{job['stage']}: {_job_name(job)}"
                    )
            else:
                jobs_col.row().label(text="idle")

        uuid_to_job = {
            uuid: job["job_id"]
            for job in monitor_jobs
            for uuid in job.get("machines", [])
        }

    # The farm host's row comes first.
    rows = rows_that_fit(context, _WORKERS_RESERVED_UNITS) - 1
    machines = machines + ["empty"] * (rows - len(machines))
    for m in machines:
        row = layout.column()
        layout.separator(factor=0.5, type="LINE")

        if m == "empty":
            row.label(text="", icon="BLANK1")
            continue

        split = row.split(factor=FIRST_COLUMN)

        info = split.row()
        # Read from disk: never trust a key to be there.
        busy = m.get("status") not in ("idle", "not running", "stopped", None)
        info.label(
            text=m.get("user", "unknown"),
            icon="KEYTYPE_BREAKDOWN_VEC" if busy else "KEYTYPE_JITTER_VEC",
        )
        info.label(text=m.get("machine", "unknown"))

        jobs = split.row()
        if m.get("status") == "stopped":
            jobs.label(text="stopped")
            continue
        if busy:
            current_id = m.get("current_job_id") or ""
            job = jobs_by_id.get(current_id)
            # Not in the snapshot (archived meanwhile): the .blend the worker
            # file names -- current_job is its request's full path.
            name = _job_name(job) if job else Path(m.get("current_file") or "").name
            text = f"render: {name or current_id}"
            pace = ((job or {}).get("machine_seconds") or {}).get(m.get("uuid"))
            if pace:
                text += f"  ({_duration(pace)}/frame)"
            if m.get("stopping"):
                text += "  (stops after this frame)"
            _draw_job_link(jobs, current_id, text)
            job_id = uuid_to_job.get(m.get("uuid"))
            if job_id:
                op = jobs.operator(
                    "m_pipeline.farm_cancel_job", text="", icon="X", emboss=False
                )
                op.job_id = job_id
                op.target_uuid = m.get("uuid", "")
        else:
            jobs.label(text="idle")
        if not m.get("stopping"):
            op = jobs.operator(
                "m_pipeline.farm_stop_worker", text="", icon="PAUSE", emboss=False
            )
            op.target_uuid = m.get("uuid", "")
            op.machine = m.get("machine", "")
            op.busy = busy
    layout.separator()  # the last row's line off the box's bottom edge


def draw_farm_job_details(layout, context):
    """M_PIPELINE_OT_farm_monitor's detail view of one job: its file as read
    by M_PIPELINE_OT_farm_job_details on click (get_job_details()) -- never
    read from here. Every key with .get(): the file is hand-editable and
    older jobs lack the newer fields."""
    job_id = monitoring_detail("job")
    data = get_job_details()

    header = layout.row()
    back = header.row()
    back.alignment = "LEFT"
    back.operator("m_pipeline.farm_job_details", text="", icon="BACK", emboss=False)
    name = Path(data.get("filepath", "")).name or job_id
    if data.get("shot_override"):
        name = f"{name}  [{data['shot_override']}]"
    header.label(text=name, icon="RENDER_ANIMATION")
    actions = header.row(align=True)
    actions.alignment = "RIGHT"
    if failed_stage(data):
        actions.operator(
            "m_pipeline.farm_retry_job", text="Retry", icon="LOOP_BACK"
        ).job_id = job_id
        actions.separator(factor=2)  # apart from reload: both read as "redo"
    elif recompilable(data):
        actions.operator(
            "m_pipeline.farm_recompile_job", text="Recompile", icon="FILE_MOVIE"
        ).job_id = job_id
        actions.separator(factor=2)
    op = actions.operator(
        "m_pipeline.farm_job_details", text="", icon="FILE_REFRESH", emboss=False
    )
    op.job_id = job_id
    op.reload = True
    job_file = get_job_details_path()
    if job_file:
        op = actions.operator(
            "wm.open_folder", text="", icon="FILE_TEXT", emboss=False
        )
        op.filepath = str(job_file)
        op.custom_tooltip = (
            f"Open this job's file ({job_file.parent.name}/{job_file.name})"
        )
    actions.operator(
        "m_pipeline.pipeline_logs", text="", icon="TEXT", emboss=False
    ).search = job_id

    if not data:
        layout.label(text="Job file not found.", icon="ERROR")
        return

    # Names recorded with the job: a machine whose worker is gone.
    recorded = dict(data.get("machine_names") or {})
    recorded.update(
        {u: n for u, n in (data.get("frame_machines") or {}).get("machines", {}).values()}
    )

    def machine_names(uuids) -> str:
        return ", ".join(machine_label(u, recorded.get(u, "")) for u in uuids or []) or "-"

    def field(col, label: str, value, icon: str = "NONE"):
        split = col.split(factor=FIRST_COLUMN)
        left = split.row()
        left.active = False
        left.label(text=label)
        split.label(text=str(value), icon=icon)

    layout.separator(factor=0.5, type="LINE")
    col = layout.column(align=True)
    field(col, "Job", job_id)
    field(col, "Submitted by", data.get("user", "-"))
    field(col, "Render mode", data.get("render_mode", "-"))
    field(col, "Preset", data.get("prerender_script") or "none")

    frames = data.get("resolved_frame_range")
    if frames and len(frames) == 2:
        count = frames[1] - frames[0] + 1
        field(col, "Frames", f"{frames[0]} - {frames[1]} ({count})")
    else:
        field(col, "Frames", "not resolved yet")
    field(col, "Format", data.get("output_extension", "-"))
    field(col, "fps", data.get("fps", "-"))

    output = data.get("output_path")
    split = col.split(factor=FIRST_COLUMN)
    left = split.row()
    left.active = False
    left.label(text="Output")
    out = split.row()
    out.label(text=output or "-")
    root = get_active_project_root()
    if output and root:
        path = Path(output)
        op = out.operator("wm.open_folder", text="", icon="FILE_FOLDER", emboss=False)
        op.filepath = str((path if path.is_absolute() else Path(root) / path).parent)
        op.custom_tooltip = "Open this job's render folder"

    field(
        col,
        "Assigned to",
        machine_names(data["assigned_machines"]) if data.get("assigned_machines") else "auto",
    )
    field(col, "Machines", machine_names(data.get("used_machines")))
    if data.get("rendered_by"):
        field(col, "Rendered by", machine_names(data["rendered_by"]))
    # Live from the monitor cache while it renders, else the job file's.
    live = next(
        (j for j in get_monitor_cache().get("jobs") or [] if j.get("job_id") == job_id),
        {},
    )
    average = live.get("seconds_per_frame") or data.get("seconds_per_frame")
    if average:
        field(col, "Per frame", f"{_duration(average)} on average")
    per_machine = live.get("machine_seconds") or data.get("machine_seconds") or {}
    record = data.get("frame_machines") or {}
    counts = {}
    for letter in record.get("frames", ""):
        uuid = (record.get("machines", {}).get(letter) or [""])[0]
        if uuid:
            counts[uuid] = counts.get(uuid, 0) + 1
    if per_machine or counts:
        names = {u: n for u, n in record.get("machines", {}).values()}

        def machine_line(u):
            parts = [f"{counts[u]} frames"] if u in counts else []
            if u in per_machine:
                parts.append(f"{_duration(per_machine[u])}/frame")
            return f"{machine_label(u, names.get(u))} ({', '.join(parts)})"

        field(
            col,
            "Per machine",
            ", ".join(machine_line(u) for u in sorted(set(per_machine) | set(counts))),
        )
    if record:
        split = col.split(factor=FIRST_COLUMN)
        left = split.row()
        left.active = False
        left.label(text="Who rendered")
        draw_frame_lookup(split, [("", record, per_machine)])
    if data.get("failed_machines"):
        field(col, "Failed on", machine_names(data["failed_machines"]))
    if data.get("frames_corrupted"):
        field(col, "Corrupted frames", data["frames_corrupted"], icon="ERROR")
    if data.get("frames_rerendered"):
        # Corrupted or written by two machines, then rendered again.
        frames = data["frames_rerendered"]
        more = f" (+{len(frames) - 8})" if len(frames) > 8 else ""
        field(
            col,
            "Rendered again",
            ", ".join(str(f) for f in frames[:8]) + more,
            icon="FILE_REFRESH",
        )

    if data.get("split_into"):
        field(col, "Split into", ", ".join(data["split_into"]))
    if data.get("skipped_shots"):
        field(col, "Missing shots", ", ".join(data["skipped_shots"]), icon="ERROR")
    if data.get("absorbed_shots"):
        field(col, "Absorbed shots", ", ".join(data["absorbed_shots"]))

    logs = get_job_details_logs()
    if logs:
        split = col.split(factor=FIRST_COLUMN)
        left = split.row()
        left.active = False
        left.label(text="Logs")
        buttons = split.row(align=True)
        buttons.alignment = "LEFT"
        prefix = f"request_{job_id}_"
        for log_file in logs:
            # request_<job_id>.log is this machine's stages, the others a
            # worker's render (request_<job_id>_<uuid>.log).
            stem = log_file.stem
            uuid = stem[len(prefix) :] if stem.startswith(prefix) else ""
            op = buttons.operator(
                "wm.open_folder",
                text=machine_names([uuid]) if uuid else "farm host",
                icon="TEXT",
            )
            op.filepath = str(log_file)
            op.custom_tooltip = f"Open {log_file.name}"

    layout.separator(factor=0.5, type="LINE")
    col = layout.column(align=True)
    title = col.row()
    title.active = False
    title.label(text="Stages")
    previous = None
    for entry in data.get("stage_history") or []:
        at = _job_time(entry.get("at"))
        stage = entry.get("stage", "?")
        if entry.get("resumed"):
            stage += f" ({entry['resumed']})"
        delta = (
            f"+{_duration((at - previous).total_seconds())}" if at and previous else ""
        )
        split = col.split(factor=FIRST_COLUMN)
        left = split.row()
        left.active = False
        left.label(text=f"{at:%d/%m %H:%M:%S}  {delta}" if at else "?")
        split.label(text=stage)
        previous = at or previous
