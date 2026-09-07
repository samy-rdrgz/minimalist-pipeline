"""Farm management panel in the 3D View sidebar."""

import datetime
import json
from pathlib import Path

import bpy

from ..farm import get_monitor_cache, scan_workers
from ..lib import ConfigCache, addon_pref, draw_box_tip, get_active_project_root

FIRST_COLUMN = 0.4


class M_PIPELINE_PT_farm_panel(bpy.types.Panel):
    """Farm monitoring."""

    bl_label = ""
    bl_idname = "M_PIPELINE_PT_farm_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pipeline"

    bl_options = {"HEADER_LAYOUT_EXPAND", "DEFAULT_CLOSED"}

    def _get_jobs(self, jobs_dir: Path) -> list[dict]:
        jobs = []
        for i in jobs_dir.glob("job_*.json"):
            filepath = jobs_dir / i.name
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                jobs.append(data)
            except Exception:
                pass
        return jobs

    @classmethod
    def poll(cls, context):
        return addon_pref(context) is not None and get_active_project_root()

    def draw_header(self, context):
        layout = self.layout.row(align=True)
        layout.separator(factor=0.4)

        monitor = ConfigCache.get_path("monitor_file")
        is_monitor = monitor.exists()

        if not is_monitor:
            layout.label(text="Farm : not running", icon="GHOST_DISABLED")
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
            layout.label(
                text=labels.get(status, "Farm : ..."),
                icon=icons.get(status, "GHOST_DISABLED"),
            )
            if status != "running":
                layout.operator(
                    "m_pipeline.farm_launch_monitor",
                    text="",
                    icon="TRIA_RIGHT",
                    emboss=False,
                )
        layout.operator(
            "m_pipeline.farm_monitor", text="", icon="SEQ_STRIP_MODIFIER", emboss=False
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

        monitor = ConfigCache.get_path("monitor_file")

        is_monitor = monitor.exists()

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
        layout.operator(
            "m_pipeline.farm_monitor", text="Farm monitor", icon="SEQ_STRIP_MODIFIER"
        )


def draw_farm_jobs(layout):
    """M_PIPELINE_OT_farm_monitor's "Jobs" view: every active job, its stage
    and progress."""
    cache = get_monitor_cache()

    title = layout.split(factor=FIRST_COLUMN)
    title.active = False
    title.row().label(text="Jobs", icon="BLANK1")
    title.row().label(text="Status")

    # Job list
    jobs = (
        cache["jobs"]
        if len(cache["jobs"]) >= 5
        else cache["jobs"] + ["empty" for _ in range(5 - len(cache["jobs"]))]
    )
    for j in jobs:
        row = layout.column(align=True)
        row.separator(factor=0.1, type="LINE")
        if j == "empty":
            row.label(text="", icon="BLANK1")
            continue
        else:
            row = row.split(factor=FIRST_COLUMN)
            name = Path(j["filepath"]).name
            stage = j["stage"]
            # A multishot block split into one job per shot (see
            # _split_into_shot_jobs() in farm/setup.py) shares that same
            # filepath across every job -- shot_override ("sh045") tells
            # a split-off child apart from its siblings; split_finished
            # (only ever reached by the parent, never a child) tells the
            # parent apart from an ordinary, unsplit job.
            if j.get("shot_override"):
                name = f"{name}  [{j['shot_override']}]"
            elif stage == "split_finished":
                name = f"{name}  [split]"

            elapsed = j["elapsed_seconds"]
            text = ""
            icon = ""
            elapsed_str = f"{int(elapsed // 60)}m{int(elapsed % 60):02d}s"

            if stage == "pending":
                icon = "SORTTIME"
            elif stage == "queued":
                icon = "DECORATE_ANIMATE"
            elif stage == "finished" or stage == "split_finished":
                icon = "KEYTYPE_JITTER_VEC"
            elif stage.endswith("_finished"):
                icon = "HANDLETYPE_FREE_VEC"
            elif stage.endswith("failed"):
                icon = "KEYTYPE_EXTREME_VEC"
            else:
                icon = "KEYTYPE_BREAKDOWN_VEC"

            if stage == "pending":
                text = f"waiting for monitor - {elapsed_str}"
            elif (
                stage == "finished"
                or stage == "split_finished"
                or stage.endswith("failed")
            ):
                # These are terminal once archived (see _build_job_entry():
                # an archived job reports its own penultimate stage, not
                # "archived", so this is the branch that actually shows --
                # a fixed completion time, not elapsed, which would
                # otherwise tick up forever against a stage_at that never
                # moves again.
                text = f"{stage} - {str(datetime.datetime.fromisoformat(j['stage_at'])).replace('-', '·')}"

            elif j["frames_total"] > 0:
                pct = j["frames_done"] / j["frames_total"]
                remaining = elapsed / pct
                remaining_str = (
                    f"≃ {int(remaining // 60)}m{int(remaining % 60):02d}s remaining"
                )
                text = f"{stage} - {j['frames_done']}/{j['frames_total']} ({pct:.0%}) - {elapsed_str} ({remaining_str})"

            else:
                text = f"{stage} - {elapsed_str}"

            if j.get("skipped_shots"):
                text += f" -- missing: {', '.join(j['skipped_shots'])}"
            if j.get("absorbed_shots"):
                text += f" -- absorbed: {', '.join(j['absorbed_shots'])}"

            row.label(text=name, icon=icon)
            status = row.row()
            status.label(text=text)
            if stage == "render_start":
                status.operator(
                    "m_pipeline.farm_cancel_job", text="", icon="X", emboss=False
                ).job_id = j["job_id"]
            elif (
                stage == "finished"
                or stage == "split_finished"
                or stage.endswith("failed")
            ):
                status.operator(
                    "m_pipeline.farm_archive_job",
                    text="",
                    icon="CHECKMARK",
                    emboss=False,
                ).job_id = j["job_id"]


def draw_farm_workers(layout):
    """M_PIPELINE_OT_farm_monitor's "Workers" view: every known machine, idle
    or what it's currently rendering."""
    title_list = layout.split(factor=FIRST_COLUMN)
    title_list.active = False
    btn = title_list.row()
    btn.alignment = "LEFT"
    btn.label(text="Machine", icon="BLANK1")
    if bpy.context.scene.is_worker:
        btn.operator(
            "m_pipeline.farm_kill_self_worker", text="Kill this worker", icon="X"
        )
    else:
        btn.operator(
            "m_pipeline.farm_add_self_worker", text="Add this machine", icon="ADD"
        )

    title_list.row().label(text="Jobs")

    workers = scan_workers()

    machines = [j for i, j in workers.items()]

    monitor_cache = get_monitor_cache()
    layout.separator(factor=0.1, type="LINE")
    row = layout.column(align=True)
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
        monitor_jobs = monitor_cache["jobs"]

        split = row.split(factor=FIRST_COLUMN)
        split.row().label(
            text=monitor_label,
            icon="KEYTYPE_BREAKDOWN_VEC" if monitor_jobs else "KEYTYPE_JITTER_VEC",
        )
        jobs_col = split.column(align=True)
        if monitor_jobs:
            for job in monitor_jobs:
                jobs_col.row().label(text=f"{job['stage']}: {job['job_id']}")
        else:
            jobs_col.row().label(text="idle")

        uuid_to_job = {
            uuid: job["job_id"] for job in monitor_jobs for uuid in job["machines"]
        }

    # uuid -> job_id, to let a busy worker's row cancel just its own share

    machines = machines + ["empty" for _ in range(4 - len(machines))]
    for m in machines:
        row = layout.column(align=True)
        row.separator(factor=0.1, type="LINE")

        if m == "empty":
            row.label(text="", icon="BLANK1")
            continue

        split = row.split(factor=FIRST_COLUMN)

        info = split.row()
        busy = m["status"] != "idle" and m["status"] != "not running"
        info.label(
            text=m.get("user", "unknown"),
            icon="KEYTYPE_BREAKDOWN_VEC" if busy else "KEYTYPE_JITTER_VEC",
        )
        info.label(text=m.get("machine", "unknown"))

        jobs = split.row()
        if busy:
            jobs.label(text=f"render: {m['current_job']}")
            job_id = uuid_to_job.get(m.get("uuid"))
            if job_id:
                op = jobs.operator(
                    "m_pipeline.farm_cancel_job", text="", icon="X", emboss=False
                )
                op.job_id = job_id
                op.target_uuid = m.get("uuid", "")
        else:
            jobs.label(text="idle")
