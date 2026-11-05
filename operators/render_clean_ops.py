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


class _ThreadedModal:
    """Run fn on a thread (SnapshotJob), then on_done(context, result)."""

    def _start(self, context, fn, *args):
        self._job = SnapshotJob(fn, *args)
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type != "TIMER" or not self._job.done:
            return {"PASS_THROUGH"}
        context.window_manager.event_timer_remove(self._timer)
        if self._job.error:
            log("ERROR", "render_clean", f"Clean old renders failed: {self._job.error}")
            self.report({"ERROR"}, "Clean old renders failed (see log).")
            return {"CANCELLED"}
        return self.on_done(context, self._job.result)


class M_PIPELINE_OT_clean_renders(_ThreadedModal, bpy.types.Operator):
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
        self._options = (self.keep, self.mode)
        self.report({"INFO"}, "Looking at the renders...")
        return self._start(
            context,
            plan_render_clean,
            root,
            self.keep,
            self.mode == "IMAGES",
            kinds,
            sequence,
            json_get(ConfigCache.get(), "naming.version.prefix", "v"),
            ConfigCache.get_path("farm_actives"),
        )

    def on_done(self, context, plan):
        if not plan["candidates"]:
            self.report({"INFO"}, "Nothing to clean: every render is among the ones kept.")
            return {"FINISHED"}
        _pending.clear()
        _pending.update(plan=plan, keep=self._options[0])
        bpy.app.timers.register(
            lambda: bpy.ops.m_pipeline.clean_renders_confirm("INVOKE_DEFAULT") and None,
            first_interval=0.05,
        )
        return {"FINISHED"}


class M_PIPELINE_OT_clean_renders_confirm(_ThreadedModal, bpy.types.Operator):
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
        self._plan = plan
        self.report({"INFO"}, "Cleaning old renders...")
        return self._start(context, apply_render_clean, plan)

    def on_done(self, context, result):
        _pending.clear()
        kind = "lightened (frames deleted)" if self._plan["images_only"] else "deleted"
        message = f"{result['done']} older render(s) {kind}, {human_bytes(result['bytes'])} freed."
        log("SUCCESS", "render_clean", f"{message} By {get_user(context)}.")
        for path, why in result["errors"]:
            log("WARNING", "render_clean", f"Not cleaned: {path}: {why}")
        if result["errors"]:
            self.report({"WARNING"}, f"{message} {len(result['errors'])} could not be (see log).")
        else:
            self.report({"INFO"}, message)
        return {"FINISHED"}
