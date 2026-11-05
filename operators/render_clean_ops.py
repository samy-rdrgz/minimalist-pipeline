"""Clean old renders (lib/render_clean.py): the options, the scan on a
thread, what it would free asked first, the clean on a thread."""

import bpy

from ..lib import (
    ConfigCache,
    SnapshotJob,
    get_active_project_root,
    get_user,
    json_get,
    log,
    sequence_items,
)
from ..lib.render_clean import apply_render_clean, human_bytes, plan_render_clean

# The scan's result waiting for its confirm dialog (one timer tick later:
# see NOTES.md, "Popup-chaining").
_pending: dict = {}
_GROUPS_SHOWN = 12


def _in_background(fn, args, on_done) -> None:
    """Run fn(*args) on a thread (SnapshotJob), polled by a timer, then
    on_done(result) -- no modal handler: the confirm dialog runs from a
    timer, with no window to hang one on (its clean never ran)."""
    job = SnapshotJob(fn, *args)

    def poll():
        if not job.done:
            return 0.3
        if job.error:
            log("ERROR", "render_clean", f"Clean old renders failed: {job.error}")
            _popup("Clean old renders failed", f"{job.error}\n\nSee the pipeline log.", "ERROR")
            return None
        on_done(job.result)
        return None

    bpy.app.timers.register(poll, first_interval=0.3)


def _popup(title: str, message: str, icon: str = "INFO") -> None:
    try:
        bpy.ops.m_pipeline.text_popup("INVOKE_DEFAULT", title=title, message=message, icon=icon)
    except RuntimeError:
        pass  # no window to show it in: the log has it


class M_PIPELINE_OT_clean_renders(bpy.types.Operator):
    """Lighten the renders folder: keep each shot's and asset's last renders,
    delete the older ones -- or only their frames, their videos kept."""

    bl_idname = "m_pipeline.clean_renders"
    bl_label = "Clean old renders"
    bl_options = {"INTERNAL"}

    keep: bpy.props.IntProperty(
        name="Renders kept",
        description="How many of its latest renders each shot and asset keeps whole",
        default=2,
        min=1,
        soft_max=10,
    )
    mode: bpy.props.EnumProperty(
        name="Older renders",
        items=[
            ("IMAGES", "Keep their videos", "Delete only their frames: every version stays watchable, a fraction of the size"),
            ("DELETE", "Delete them", "Delete their whole folder, video included"),
        ],
        default="IMAGES",
    )
    scope: bpy.props.EnumProperty(
        name="In",
        items=[
            ("BOTH", "Shots and assets", ""),
            ("SHOTS", "Shots", ""),
            ("ASSETS", "Assets", ""),
        ],
        default="BOTH",
    )
    sequence: bpy.props.EnumProperty(name="Sequence", items=sequence_items)

    def invoke(self, context, event):
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(
            self, width=420, confirm_text="Look"
        )

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "keep")
        col.prop(self, "mode")
        col.prop(self, "scope")
        if self.scope != "ASSETS":
            col.prop(self, "sequence")
        tip = col.column(align=True)
        tip.active = False
        tip.scale_y = 0.8
        tip.label(text="Their last render, a render a note or 'to check' names,")
        tip.label(text="one the farm is writing: always kept. Nothing done before you confirm.")

    def execute(self, context):
        root = get_active_project_root()
        kinds = {"BOTH": ("shot", "asset"), "SHOTS": ("shot",), "ASSETS": ("asset",)}[self.scope]
        sequence = "" if self.scope == "ASSETS" or self.sequence in ("all", "NONE") else self.sequence
        keep = self.keep
        self.report({"INFO"}, "Looking at the renders...")

        def looked(plan):
            if not plan["candidates"]:
                _popup("Clean old renders", "Nothing to clean: every render is among the ones kept.")
                return
            _pending.clear()
            _pending.update(plan=plan, keep=keep)
            bpy.ops.m_pipeline.clean_renders_confirm("INVOKE_DEFAULT")

        _in_background(
            plan_render_clean,
            (
                root,
                self.keep,
                self.mode == "IMAGES",
                kinds,
                sequence,
                json_get(ConfigCache.get(), "naming.version.prefix", "v"),
                ConfigCache.get_path("farm_actives"),
            ),
            looked,
        )
        return {"FINISHED"}


class M_PIPELINE_OT_clean_renders_confirm(bpy.types.Operator):
    """What a clean would free, asked before doing it."""

    bl_idname = "m_pipeline.clean_renders_confirm"
    bl_label = "Clean old renders"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        if not _pending:
            return {"CANCELLED"}
        plan = _pending["plan"]
        what = "Delete their frames" if plan["images_only"] else "Delete them"
        return context.window_manager.invoke_props_dialog(
            self, width=460, confirm_text=f"{what} ({human_bytes(plan['bytes'])})"
        )

    def draw(self, context):
        plan = _pending["plan"]
        col = self.layout.column(align=True)
        n = len(plan["candidates"])
        if plan["images_only"]:
            col.label(text=f"{n} older render(s): their frames deleted, their videos kept.", icon="IMAGE_DATA")
        else:
            row = col.row()
            row.alert = True
            row.label(text=f"{n} older render(s) deleted, videos included.", icon="TRASH")
        col.label(text=f"{human_bytes(plan['bytes'])} freed -- the {_pending['keep']} latest of each kept whole ({plan['kept']} render(s)).", icon="BLANK1")
        previous = sum(1 for c in plan["candidates"] if c.get("previous"))
        if previous:
            col.label(
                text=f"{previous} of them from a previous file of the same shot (rendered before it was made).",
                icon="BLANK1",
            )
        col.separator()
        groups = list(plan["groups"].items())
        box = col.box().column(align=True)
        box.scale_y = 0.8
        for group, (folders, size) in groups[:_GROUPS_SHOWN]:
            row = box.row()
            row.label(text=group)
            right = row.row()
            right.alignment = "RIGHT"
            right.label(text=f"{folders} render(s), {human_bytes(size)}")
        if len(groups) > _GROUPS_SHOWN:
            rest = groups[_GROUPS_SHOWN:]
            box.label(
                text=f"... and {len(rest)} more: {sum(f for _, (f, _s) in rest)} render(s), "
                f"{human_bytes(sum(s for _, (_f, s) in rest))}"
            )

    def execute(self, context):
        plan = _pending.get("plan")
        if not plan:
            return {"CANCELLED"}
        _pending.clear()
        user = get_user(context)
        kind = "lightened (frames deleted)" if plan["images_only"] else "deleted"
        log("INFO", "render_clean", f"Cleaning {len(plan['candidates'])} older render(s) ({kind}), by {user}...")
        self.report({"INFO"}, "Cleaning old renders...")

        def cleaned(result):
            message = f"{result['done']} older render(s) {kind}, {human_bytes(result['bytes'])} freed."
            log("SUCCESS", "render_clean", f"{message} By {user}.")
            for path, why in result["errors"]:
                log("WARNING", "render_clean", f"Not cleaned: {path}: {why}")
            if result["errors"]:
                lines = [f"{path}: {why}" for path, why in result["errors"][:12]]
                _popup("Clean old renders", "\n".join([message, f"{len(result['errors'])} not cleaned:", *lines]), "ERROR")
            else:
                _popup("Clean old renders", message)

        _in_background(apply_render_clean, (plan,), cleaned)
        return {"FINISHED"}
