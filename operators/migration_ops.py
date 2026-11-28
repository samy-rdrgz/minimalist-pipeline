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
from ..lib.monitoring.tracking import ProjectScan, TrackingStatusCache
from ..lib.operators import popup

# The plan waiting for its confirm dialog (see NOTES.md, "Popup-chaining").
_pending: dict = {}
# The department menu's items, kept: Blender holds on to the strings an
# items callback returned (see operators/farm_ops.py _stable_enum_items()).
_KEEP = "__keep__"
_department_items: list = []


def _departments_of(root) -> list[str]:
    config = ConfigCache.get() or {}
    return list(dict.fromkeys(
        str(d).strip().lower()
        for d in [*json_get(config, "shots_departments", []), *json_get(config, "assets_departments", [])]
        if str(d).strip()
    ))


def _department_enum(self, context):
    items = [(_KEEP, "Keep as is", "Leave its name: its renders keep no department")]
    items += [(d, d.capitalize(), f"Rename it for {d}: its renders are {d}'s") for d in _departments_of(None)]
    if _department_items != items:
        _department_items[:] = items
    return _department_items


def renamed_for(name: str, department: str) -> str:
    """A preset's name for a department: the department in place of its
    first word ("final_hd" -> "lighting_hd"), before it with none ("hd" ->
    "lighting_hd")."""
    for sep in ("_", "-"):
        if sep in name:
            return f"{department}{sep}{name.split(sep, 1)[1]}"
    return f"{department}_{name}"


class PIPELINE_PG_preset_rename(bpy.types.PropertyGroup):
    """A preset whose name gives no department, in Migrate old data: the
    department to rename it for, or kept."""

    department: bpy.props.EnumProperty(name="", items=_department_enum)

# What a change is called in the dialog, in its order.
_CHANGES = (
    ("entry departments", "notes and tasks: their departments as a list"),
    ("entry ids made unique", "notes and tasks: an id found twice made unique"),
    ("stable: departments started", "stables: the departments started so far"),
    ("stable: validations carried", "stables: the validations they carried"),
    ("links one per file", "versions: their links, one per file"),
    ("render: folder found", "renders before 1.0.11: their folder, found by time"),
    ("render: source file", "renders: the .blend they came from"),
    ("render: shot", "renders: their shot"),
    ("render: frame range", "renders: their frame range"),
    ("presets: into their folders", "presets: into render_shots/, render_assets/ and creation/"),
    ("render presets: .json to .py", "render presets: .json rewritten as .py"),
    ("render presets: one per department", "render presets: one for each department with none"),
    ("sessions with their date, named sessions", "versions: their sessions dated, named sessions"),
    ("progress: days rebuilt", "progress over time: the days before the log, rebuilt"),
    ("activity: rebuilt", "activity over time (files worked, hours): rebuilt"),
)


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
            popup("Migrate old data failed", f"{error}\n\nSee the pipeline log.", "ERROR")

        v_prefix = json_get(ConfigCache.get(), "naming.version.prefix", "v")
        run_in_background(plan_migration, (root, v_prefix), read, failed, task=("migration", root.name))
        return {"FINISHED"}


class M_PIPELINE_OT_migrate_data_confirm(bpy.types.Operator):
    """What the migration would change, asked before writing it."""

    bl_idname = "m_pipeline.migrate_data_confirm"
    bl_label = "Migrate old data"
    bl_options = {"INTERNAL"}

    renames: bpy.props.CollectionProperty(type=PIPELINE_PG_preset_rename)
    old_renders: bpy.props.BoolProperty(
        name="Their past renders too",
        description="The renders these presets made, with no department, get the new name's: right only if each always served that department",
        default=False,
    )

    def invoke(self, context, event):
        if not _pending:
            return {"CANCELLED"}
        plan = _pending["plan"]
        self.renames.clear()
        for name in plan.get("loose_presets") or []:
            self.renames.add().name = name
        n = len(plan["files"]) + sum(len(v) for v in (plan.get("presets") or {}).values())
        text = f"Migrate {n} file(s)" if n or plan.get("loose_presets") else "Note it as migrated"
        return context.window_manager.invoke_props_dialog(self, width=460, confirm_text=text)

    def draw(self, context):
        plan = _pending["plan"]
        col = self.layout.column(align=True)
        if self.renames:
            # A name is the user's to choose: proposed, kept by default.
            box = col.box().column(align=True)
            box.label(text="Render presets whose name gives no department (their renders have none):", icon="ERROR")
            for item in self.renames:
                row = box.split(factor=0.4, align=True)
                row.label(text=item.name)
                right = row.row(align=True)
                right.prop(item, "department")
                if item.department != _KEEP:
                    right.label(text=f"→ {renamed_for(item.name, item.department)}")
            if any(i.department != _KEEP for i in self.renames):
                box.prop(self, "old_renders")
            col.separator()
        if not plan["files"] and not any((plan.get("presets") or {}).values()) and not self.renames and not plan.get("progress"):
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
        if result.get("progress_days"):
            message += f" Progress over time: {result['progress_days']} day(s) rebuilt."
        if result["written"]:
            message += f" Backups: {result['backup']}"
        if result["errors"]:
            lines = [f"{p}: {why}" for p, why in result["errors"][:12]]
            popup("Migrate old data", "\n".join([message, f"{len(result['errors'])} not migrated:", *lines]), "ERROR")
            log("WARNING", "migration", f"{message} {len(result['errors'])} not migrated, by {user}.")
            return {"FINISHED"}  # not noted as done: run it again
        message += self._renames(root)
        _record(root, user, result["written"])
        log("SUCCESS", "migration", f"{message} By {user}.")
        TrackingStatusCache._cache.clear()
        ProjectScan.start(root)
        popup("Migrate old data", message)
        return {"FINISHED"}


    def _renames(self, root) -> str:
        """The presets given a department, each as Rename preset does it:
        " N preset(s) renamed." -- and any refused, said."""
        from ..lib.errors import PipelineError
        from ..lib.presets import rename_preset

        done, refused = [], []
        departments = _departments_of(root)
        for item in self.renames:
            if item.department == _KEEP:
                continue
            new = renamed_for(item.name, item.department)
            try:
                rename_preset(root, item.name, new, departments, old_renders=self.old_renders)
                done.append(f"{item.name} -> {new}")
                log("INFO", "migration", f"Render preset {item.name} renamed {new}.")
            except PipelineError as e:
                refused.append(f"{item.name}: {e.message}")
                log("WARNING", "migration", f"Render preset {item.name} not renamed: {e.message}")
        text = f" {len(done)} render preset(s) renamed." if done else ""
        if refused:
            text += " Not renamed: " + "; ".join(refused) + " (Edit project > Rename preset)."
        return text


def project_needs_migration() -> bool:
    """The active project's data not migrated yet (draw(): never raises)."""
    try:
        return bool(get_active_project_root()) and not migration_done(ConfigCache.get())
    except Exception:
        return False
