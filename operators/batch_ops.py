"""Batch operator: create multiple assets/shots from a CSV, each row built in
its own disposable headless Blender process (see lib/batch.py). Runs as a
background modal (PASS_THROUGH on every event) so the artist can keep working
while it processes the queue."""

from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    PipelineError,
    asset_batch_exists,
    get_active_project_root,
    launch_batch_create_entry,
    log,
    parse_asset_batch_csv,
    parse_shot_batch_csv,
    read_batch_result,
    sanitize_name,
    shot_batch_exists,
)


class M_PIPELINE_OT_batch_create(bpy.types.Operator):
    """Batch-create assets or shots from a CSV file, skipping any that
    already exist."""

    bl_idname = "m_pipeline.batch_create"
    bl_label = "Batch create from CSV"
    bl_description = (
        "Create multiple assets or shots from a CSV file, skipping existing ones."
    )

    kind: bpy.props.EnumProperty(
        items=[("asset", "Assets", ""), ("shot", "Shots", "")],
        name="Kind",
        default="asset",
    )
    csv_path: bpy.props.StringProperty(
        name="CSV file",
        subtype="FILE_PATH",
        description="Select your .csv file.",
        default="",
    )

    _timer = None
    _queue = None
    _process = None
    _request_path = None
    _current_label = ""
    _created = 0
    _failed = 0
    _skipped = 0
    _project_root = None

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "kind", expand=True)
        layout.prop(self, "csv_path")
        layout.separator()
        col = layout.column(align=True)
        col.active = False
        col.scale_y = 0.7
        if self.kind == "asset":
            col.label(text="Columns: prefix, name (required),", icon="INFO")
            col.label(text="departments, description (both optional).")
        else:
            col.label(text="Columns: sequence, shot (required),", icon="INFO")
            col.label(text="frame_start / frame_end / frame_duration,")
            col.label(text="departments, description (all optional).")
        col.label(text="departments: comma-separated, unknown names are")
        col.label(text="skipped (logged) -- omit for the project's defaults.")
        col.label(text="Rows matching an existing asset/shot are skipped.")

    def invoke(self, context, event):
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(
            self, width=420, confirm_text="Start batch"
        )

    def execute(self, context):
        project_root = get_active_project_root()

        if not self.csv_path:
            self.report({"ERROR"}, "No CSV file selected.")
            return {"CANCELLED"}

        csv_file = Path(bpy.path.abspath(self.csv_path))
        try:
            rows = (
                parse_asset_batch_csv(csv_file)
                if self.kind == "asset"
                else parse_shot_batch_csv(csv_file)
            )
        except PipelineError as e:
            log(e.level, "batch_create", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}

        config = ConfigCache.get()
        naming = config.get("naming", {})
        queue = []
        skipped = 0
        seen = set()  # labels already queued this run -- asset_batch_exists()/
        # shot_batch_exists() only see the filesystem, so two rows for the
        # same asset/shot within the same CSV would otherwise both pass
        # (neither exists on disk yet at parse time) and silently produce
        # two versions instead of the second being skipped as a duplicate.
        for row in rows:
            try:
                if self.kind == "asset":
                    prefix = row.get("prefix", "").strip()
                    name = sanitize_name(row.get("name", ""))
                    if not prefix or name == "unnamed":
                        raise ValueError("prefix/name missing")
                    label = f"{prefix}_{name}"
                    if label in seen:
                        raise ValueError("duplicate row in this CSV")
                    if asset_batch_exists(project_root, prefix, name, config):
                        skipped += 1
                        continue
                else:
                    sequence = row.get("sequence", "").strip()
                    shot = row.get("shot", "").strip()
                    if not sequence or not shot:
                        raise ValueError("sequence/shot missing")
                    sq = f"{naming['sequence']['prefix']}{int(sequence):0{naming['sequence']['digits']}d}"
                    sh = f"{naming['shot']['prefix']}{int(shot):0{naming['shot']['digits']}d}"
                    label = f"{sq}_{sh}"
                    if label in seen:
                        raise ValueError("duplicate row in this CSV")
                    if shot_batch_exists(project_root, sq, sh):
                        skipped += 1
                        continue
                seen.add(label)
                queue.append((row, label))
            except Exception as e:
                log("WARNING", "batch_create", f"Row {row} skipped: {e}")
                skipped += 1

        if not queue:
            self.report(
                {"INFO"}, f"Nothing to create ({skipped} already existing or invalid)."
            )
            return {"FINISHED"}

        self._queue = queue
        self._skipped = skipped
        self._created = 0
        self._failed = 0
        self._process = None
        self._request_path = None
        self._project_root = project_root

        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        log("INFO", "batch_create", f"Batch started: {len(queue)} file(s) to create.")
        self.report({"INFO"}, f"Batch started: {len(queue)} file(s) to create.")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if self._process is not None:
            if self._process.poll() is None:
                return {"PASS_THROUGH"}  # still running

            result = read_batch_result(self._request_path)
            self._request_path.unlink(missing_ok=True)
            if result.get("status") == "ok":
                self._created += 1
            else:
                self._failed += 1
                log(
                    "WARNING",
                    "batch_create",
                    f"{self._current_label} failed: {result.get('message', 'unknown error')}",
                )
            self._process = None

        if not self._queue:
            self._finish(context)
            return {"FINISHED"}

        row, label = self._queue.pop(0)
        self._current_label = label
        try:
            self._process, self._request_path = launch_batch_create_entry(
                project_root=self._project_root, kind=self.kind, row=row
            )
        except PipelineError as e:
            log(e.level, "batch_create", f"{label}: {e.message}")
            self._failed += 1
            self._process = None

        return {"PASS_THROUGH"}

    def _finish(self, context, cancelled=False):
        context.window_manager.event_timer_remove(self._timer)
        self._timer = None

        if cancelled and self._process is not None:
            try:
                self._process.terminate()
            except Exception:
                pass
            if self._request_path:
                self._request_path.unlink(missing_ok=True)
            self._skipped += len(self._queue or [])

        status = "cancelled" if cancelled else "finished"
        msg = (
            f"Batch {status}: {self._created} created, {self._failed} failed, "
            f"{self._skipped} skipped."
        )
        log("WARNING" if self._failed else "SUCCESS", "batch_create", msg)
        self.report({"WARNING"} if self._failed else {"INFO"}, msg)
