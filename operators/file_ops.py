"""Files management operators: increment, mark stable."""

from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    PipelineError,
    TrackingStatusCache,
    create_stablemeta,
    create_wipmeta,
    file_department_items,
    get_departments_required,
    get_last_stable,
    get_last_version_number,
    get_session_worked_departments,
    json_get,
    log,
    parse_filename,
    save_as,
    wipmeta_add_work,
)

# ---------------------------------------------------------------------------
# Increment Version
# ---------------------------------------------------------------------------


def _tag_items(self, context):
    """Build enum from config tags list + 'none' option."""
    try:
        config = ConfigCache.get()
        tags = config.get("tags", ["stable"])
        items = [("NONE", "(no tag)", "Save without tag")]
        items += [(t, t, "") for t in tags]
        return items
    except Exception:
        return [("NONE", "(no tag)", ""), ("stable", "stable", "")]


class M_PIPELINE_OT_increment_version(bpy.types.Operator):
    """Save as next version, optionally with a tag."""

    bl_idname = "m_pipeline.increment_version"
    bl_label = "Increment version"
    bl_description = "Save current file as next version."

    tag: bpy.props.EnumProperty(
        name="Tag", items=_tag_items, description="Tag to apply to this version."
    )
    worked_departments: bpy.props.EnumProperty(
        items=file_department_items,
        options={"ENUM_FLAG"},
        name="Departments worked this session :",
    )
    stabled_departments: bpy.props.EnumProperty(
        items=file_department_items,
        options={"ENUM_FLAG"},
        name="Departments validated :",
    )

    def invoke(self, context, event):
        filepath = Path(bpy.data.filepath)
        requireds = get_departments_required(filepath)
        # Default to whatever's already toggled in the asset/shot panel this
        # session, instead of asking again from scratch -- the panel toggles
        # write straight to .wipmeta, so this is just reading current state.
        self.worked_departments = set(get_session_worked_departments(filepath))

        old_stable = get_last_stable(Path(bpy.data.filepath).parent)[
            "departments_validated"
        ]
        if old_stable:
            old_stable = [d for d in old_stable if old_stable[d]]

            worked = TrackingStatusCache.get(Path(bpy.data.filepath).parent).get(
                "worked_departments", {}
            )
            checked = set()
            for d in requireds:
                if d in old_stable and d not in worked:
                    checked.add(d)
            self.stabled_departments = checked

        return context.window_manager.invoke_props_dialog(self, width=350)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "tag")

        layout.label(text="Select department(s) worked durring this session.")
        row = layout.row(align=True)
        row.prop(self, "worked_departments", expand=True)
        if self.tag == "stable":
            layout.label(text="Select department(s) finished.")
            row = layout.row(align=True)
            row.prop(self, "stabled_departments", expand=True)

        parsed = parse_filename(Path(bpy.data.filepath).name)
        if parsed:
            config = ConfigCache.get()
            v_digits = json_get(config, "naming.version.digits", 3)
            v_prefix = json_get(config, "naming.version.prefix", "v")
            next_v = get_last_version_number() + 1
            name, _ = Path(bpy.data.filepath).name.rsplit("_v", 1)
            if self.tag != "NONE":
                preview = f"{name}_{v_prefix}{next_v:0{v_digits}d}-{self.tag}.blend"
            else:
                preview = f"{name}_{v_prefix}{next_v:0{v_digits}d}.blend"

            layout.separator()
            col = layout.column()
            col.active = False
            col.scale_y = 0.5
            col.label(text=f"File: {preview}", icon="FILE")

    def execute(self, context):
        try:
            tag = self.tag if self.tag != "NONE" else None
            current = Path(bpy.data.filepath)
            result = save_as(tag=tag)

            if result:
                self.report({"INFO"}, f"Saved: {Path(result).name}")
                if "-stable.blend" not in current.name:
                    wipmeta_add_work(current, list(self.worked_departments))
                if tag != "stable":
                    create_wipmeta(
                        filepath=Path(result),
                        original_filepath=current,
                        creation_mode="manual_incrementation",
                    )
                else:
                    create_stablemeta(
                        filepath=Path(result),
                        original_filepath=current,
                        departments=list(self.stabled_departments),
                        conflict_warnings="",
                    )
                return {"FINISHED"}
            return {"CANCELLED"}
        except PipelineError as e:
            log(e.level, "increment", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
