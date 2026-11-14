"""Migrate old data (lib/migration.py): the project's files read on a
thread, what would change asked first, then written -- each one backed up
under backup/migration-<date>/ at the project's root."""

import bpy

from ..lib import (
    ConfigCache,
    get_active_project_root,
    get_user,
    json_get,
    locked_json,
    log,
    run_in_background,
)
from ..lib.config import get_config_filepath
from ..lib.migration import (
    BACKUP_DIRNAME,
    apply_migration,
    migration_done,
    migration_record,
    plan_migration,
)
from ..lib.tracking import ProjectScan, TrackingStatusCache

# The plan waiting for its confirm dialog (see NOTES.md, "Popup-chaining").
_pending: dict = {}

# What a change is called in the dialog, in its order.
_CHANGES = (
    ("entry departments", "notes and tasks: their departments as a list"),
    ("stable: departments started", "stables: the departments started so far"),
    ("stable: validations carried", "stables: the validations they carried"),
    ("links one per file", "versions: their links, one per file"),
    ("render: folder found", "renders before 1.0.11: their folder, found by time"),
    ("render: source file", "renders: the .blend they came from"),
    ("render: shot", "renders: their shot"),
    ("render: frame range", "renders: their frame range"),
)


def _popup(title: str, message: str, icon: str = "INFO") -> None:
    try:
        bpy.ops.m_pipeline.text_popup("INVOKE_DEFAULT", title=title, message=message, icon=icon)
    except RuntimeError:
        pass  # no window to show it in: the log has it


def _record(root, user: str, files: int) -> None:
    """Note in the project's config that its data was migrated."""
    with locked_json(get_config_filepath(root)) as box:
        data = box["data"] or {}
        data.setdefault("data_migrations", {}).update(migration_record(user, files))
        box["action"] = "to_write"
    ConfigCache.invalidate()


class M_PIPELINE_OT_migrate_data(bpy.types.Operator):
    """Bring the project's data from older addon versions to this one's."""

    bl_idname = "m_pipeline.migrate_data"
    bl_label = "Migrate old data"
    bl_description = (
        "Complete the data older addon versions wrote (stables, notes, render "
        "history) as this version writes it -- once per project, every machine "
        "updated first. Asks before writing; every file changed is backed up "
        f"under {BACKUP_DIRNAME}/"
    )
    bl_options = {"INTERNAL"}

    def execute(self, context):
        root = get_active_project_root()
        if not root:
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        self.report({"INFO"}, "Reading the project's data...")

        def read(plan):
            _pending.clear()
            _pending.update(plan=plan, root=root)
            bpy.ops.m_pipeline.migrate_data_confirm("INVOKE_DEFAULT")

        def failed(error):
            log("ERROR", "migration", f"Migrate old data failed: {error}")
            _popup("Migrate old data failed", f"{error}\n\nSee the pipeline log.", "ERROR")

        v_prefix = json_get(ConfigCache.get(), "naming.version.prefix", "v")
        run_in_background(plan_migration, (root, v_prefix), read, failed)
        return {"FINISHED"}


class M_PIPELINE_OT_migrate_data_confirm(bpy.types.Operator):
    """What the migration would change, asked before writing it."""

    bl_idname = "m_pipeline.migrate_data_confirm"
    bl_label = "Migrate old data"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        if not _pending:
            return {"CANCELLED"}
        n = len(_pending["plan"]["files"])
        text = f"Migrate {n} file(s)" if n else "Note it as migrated"
        return context.window_manager.invoke_props_dialog(self, width=460, confirm_text=text)

    def draw(self, context):
        plan = _pending["plan"]
        col = self.layout.column(align=True)
        if not plan["files"]:
            col.label(text=f"{plan['owners']} asset(s) and shot(s) read: nothing to change.", icon="CHECKMARK")
            return
        col.label(
            text=f"{len(plan['files'])} file(s) to complete, over {plan['owners']} asset(s) and shot(s):",
            icon="FILE_REFRESH",
        )
        box = col.box().column(align=True)
        box.scale_y = 0.8
        for key, label in _CHANGES:
            if plan["counts"].get(key):
                row = box.row()
                row.label(text=label)
                right = row.row()
                right.alignment = "RIGHT"
                right.label(text=str(plan["counts"][key]))
        col.separator()
        tip = col.column(align=True)
        tip.active = False
        tip.scale_y = 0.8
        tip.label(text="Every machine on this version first. Each file is backed up")
        tip.label(text=f"under {BACKUP_DIRNAME}/migration-<date>/: delete that folder once checked.")

    def execute(self, context):
        plan, root = _pending.get("plan"), _pending.get("root")
        if not plan:
            return {"CANCELLED"}
        _pending.clear()
        user = get_user(context)
        result = apply_migration(root, plan)
        for path, why in result["errors"]:
            log("WARNING", "migration", f"Not migrated: {path}: {why}")
        for f in plan["files"]:
            log("INFO", "migration", f"{f['path']}: {', '.join(f['changes'])}")
        message = f"{result['written']} file(s) migrated."
        if result["written"]:
            message += f" Backups: {result['backup']}"
        if result["errors"]:
            lines = [f"{p}: {why}" for p, why in result["errors"][:12]]
            _popup("Migrate old data", "\n".join([message, f"{len(result['errors'])} not migrated:", *lines]), "ERROR")
            log("WARNING", "migration", f"{message} {len(result['errors'])} not migrated, by {user}.")
            return {"FINISHED"}  # not noted as done: run it again
        _record(root, user, result["written"])
        log("SUCCESS", "migration", f"{message} By {user}.")
        TrackingStatusCache._cache.clear()
        ProjectScan.start(root)
        _popup("Migrate old data", message)
        return {"FINISHED"}


def project_needs_migration() -> bool:
    """The active project's data not migrated yet (draw(): never raises)."""
    try:
        return bool(get_active_project_root()) and not migration_done(ConfigCache.get())
    except Exception:
        return False
