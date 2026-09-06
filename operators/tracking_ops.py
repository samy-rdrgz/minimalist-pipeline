"""Tracking operators: CRUD on note/todo/rtk entries, CSV import, monitoring popups."""

import hashlib
from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    PipelineError,
    TrackingStatusCache,
    create_entry,
    delete_entry,
    department_filter_items,
    edit_entry,
    entry_version_items,
    get_active_project_root,
    get_current_departments,
    get_departments_required,
    get_description,
    get_session_worked_departments,
    get_user,
    json_get,
    log,
    now,
    prefix_items,
    sequence_items,
    set_department_validated,
    set_description,
    shot_tag_items,
    to_absolute,
    toggle_entry_task,
    tracked_department_items,
    upload_csv,
    wipmeta_add_work,
)
from ..panels import draw_file_details, draw_monitor_table

_file_department_items_cache: list = []


def _file_department_items(self, context) -> list[tuple]:
    # Cached, and returned as-is when unchanged: a dynamic EnumProperty
    # callback must keep its returned strings alive across calls (Blender
    # docs) or the current selection gets corrupted on the next redraw --
    # same reasoning as _stable_items() in lib/browser.py.
    deps = [d for d in context.window_manager.file_selected_departments.split(",") if d]
    items = [("NONE", "No department", "")] + [
        (d.lower(), d.capitalize(), "") for d in deps
    ]
    if _file_department_items_cache and _file_department_items_cache[0] == items:
        return _file_department_items_cache[1]
    _file_department_items_cache[:] = [items, items]
    return items


class PipelineEntryItem(bpy.types.PropertyGroup):
    """An entry."""

    text: bpy.props.StringProperty(name="")
    department: bpy.props.EnumProperty(items=_file_department_items)
    is_frame_start: bpy.props.BoolProperty(name="")
    frame_start: bpy.props.IntProperty(name="")
    is_frame_end: bpy.props.BoolProperty(name="")
    frame_end: bpy.props.IntProperty(name="")


class M_PIPELINE_OT_add_entry_line(bpy.types.Operator):
    """Append one text line to the note/todo being composed."""

    bl_idname = "m_pipeline.add_entry_line"
    bl_label = "New line"

    department: bpy.props.StringProperty(name="")

    def execute(self, context):
        entries = context.window_manager.pipeline_entry_buffer
        new_item = entries.add()
        if self.department:
            new_item.department = self.department
        return {"FINISHED"}


class M_PIPELINE_OT_remove_entry_line(bpy.types.Operator):
    """Remove one text line from the note/todo being composed, by index."""

    bl_idname = "m_pipeline.remove_entry_line"
    bl_label = "Remove line"

    index: bpy.props.IntProperty(name="")

    def execute(self, context):
        entries = context.window_manager.pipeline_entry_buffer
        entries.remove(self.index)
        return {"FINISHED"}


class M_PIPELINE_OT_create_entry(bpy.types.Operator):
    """Create a note/todo/rtk entry on a file's tracking.json."""

    bl_idname = "m_pipeline.create_entry"
    bl_label = "New entry"
    bl_description = "Add a note, todo, or RTK entry to this file's tracking."

    type: bpy.props.EnumProperty(
        items=[("note", "Note", ""), ("todo", "Todo", ""), ("rtk", "RTK", "")],
        options={"SKIP_SAVE"},
    )
    filepath: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    response: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})
    frame_reference: bpy.props.EnumProperty(
        items=[
            ("abs", "Absolute", ""),
            ("0", "Start at 0", ""),
            ("1", "Start at 1", ""),
        ],
        default="abs",
        options={"SKIP_SAVE"},
    )
    referenced_version: bpy.props.EnumProperty(
        items=entry_version_items, options={"SKIP_SAVE"}
    )
    shot_tag: bpy.props.EnumProperty(
        name="Shot",
        description="Which shot in this block the entry is about, if any.",
        items=shot_tag_items,
        options={"SKIP_SAVE"},
    )

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = bpy.data.filepath
        if not self.filepath:
            self.report({"ERROR"}, "No file to attach this entry to (save it first).")
            return {"CANCELLED"}

        target = Path(self.filepath)
        tracking_file = (
            (target.parent if target.is_file() else target)
            / ".pipeline"
            / "tracking.json"
        )
        if not tracking_file.exists():
            self.report(
                {"WARNING"},
                f"No tracking.json found next to {Path(self.filepath).name} "
                f"(looked in {tracking_file.parent}) -- departments/versions will be empty.",
            )

        required = get_departments_required(Path(self.filepath))
        context.window_manager.file_selected_departments = ",".join(required or [])
        file = (
            Path(self.filepath)
            if Path(self.filepath).is_dir()
            else Path(self.filepath).parent
        )
        file = (
            file.stem
            if not file.stem.startswith("sh")
            else (file.parent.stem + " " + file.stem)
        )
        return context.window_manager.invoke_props_dialog(
            self, width=480, title=f"New note or tasks for {file}:"
        )

    def draw(self, context):
        layout = self.layout

        entries = context.window_manager.pipeline_entry_buffer

        row = layout.box().split(align=True, factor=0.25)
        row.label(text="Entry type : ", icon="TRIA_RIGHT")
        row = row.row()
        row.prop(self, "type", expand=True)
        layout.prop(self, "shot_tag")
        layout.separator(factor=2)

        if self.type == "note":
            self._draw_notes(layout, entries)
        else:
            self._draw_tasks(layout, entries)

        layout.separator(factor=2)

    def _draw_notes(self, layout, entries):
        col = layout.column(align=True)

        if not entries:
            col.operator("m_pipeline.add_entry_line", text="Add text line", icon="ADD")
            return

        col_txt = col.column(align=True)
        col_txt.scale_y = 1.4
        for idx, entry in enumerate(entries):
            row = col_txt.row(align=True)
            row.textbox(entry, "text", initial_visible_lines=1)
            row.operator(
                "m_pipeline.remove_entry_line", text="", icon="REMOVE"
            ).index = idx

        row = col.row(align=True)
        row = row.split(factor=0.5, align=True)
        row_a = row.split(factor=0.5, align=True)
        row_b = row.split(factor=0.5, align=True)

        col1 = row_a.column(align=True)
        col2 = row_a.row(align=True)
        col3 = row_b.row(align=True)
        col4 = row_b.row(align=True)

        col1.prop(entries[0], "department", text="")
        col1.prop(self, "referenced_version", text="")

        txt = "Add frame tag" if not entries[0].is_frame_start else ""
        col2.prop(entries[0], "is_frame_start", text=txt)

        if entries[0].is_frame_start:
            col2.prop(entries[0], "frame_start", text="")

            txt = "add end frame" if not entries[0].is_frame_end else ""
            col3.prop(entries[0], "is_frame_end", text=txt)
            if entries[0].is_frame_end:
                col3.prop(entries[0], "frame_end", text="")

            col4.separator(factor=0.1)
            col4.prop(self, "frame_reference", text="")
            col4.separator(factor=1.5)
        else:
            col4.label()

        col4.operator("m_pipeline.add_entry_line", text="", icon="ADD")

    def _draw_tasks(self, layout, entries):
        col = layout.column(align=True)

        for idx, entry in enumerate(entries):
            row = col.row(align=True)
            row.scale_y = 1.4
            row.textbox(entry, "text", initial_visible_lines=1)
            row.operator(
                "m_pipeline.remove_entry_line", text="", icon="REMOVE"
            ).index = idx

            row = col.row(align=True)
            row = row.split(factor=0.5, align=True)
            row_a = row.split(factor=0.5, align=True)
            row_b = row.split(factor=0.5, align=True)

            col1 = row_a.column(align=True)
            col2 = row_a.row(align=True)
            col3 = row_b.row(align=True)
            col4 = row_b.row(align=True)

            col1.prop(entry, "department", text="")

            txt = "Add frame tag" if not entry.is_frame_start else ""
            col2.prop(entry, "is_frame_start", text=txt)

            if entry.is_frame_start:
                col2.prop(entry, "frame_start", text="")

                txt = "add end frame" if not entry.is_frame_end else ""
                col3.prop(entry, "is_frame_end", text=txt)
                if entry.is_frame_end:
                    col3.prop(entry, "frame_end", text="")

                col4.separator(factor=0.1)
                col4.prop(self, "frame_reference", text="")
                col4.label(icon="BLANK1")

            col.separator(factor=2)

        col.separator(factor=2)
        row = col.split(factor=0.5)
        row.prop(self, "referenced_version", text="")
        row = row.row()
        row.label()
        row.operator(
            "m_pipeline.add_entry_line", icon="ADD", text="New task"
        ).department = entries[-1].department if entries else ""

    def execute(self, context):
        if not self.filepath:
            self.filepath = bpy.data.filepath

        entries = context.window_manager.pipeline_entry_buffer
        if not entries:
            return {"CANCELLED"}

        entries_list = []

        if self.type == "note":
            texts = "\n".join([e.text for e in entries])
            f_start = entries[0].frame_start if entries[0].is_frame_start else None
            f_end = (
                entries[0].frame_end
                if entries[0].is_frame_start and entries[0].is_frame_end
                else None
            )
            entries_list.append((texts, entries[0].department, f_start, f_end))

        else:
            for entry in entries:
                f_start = entry.frame_start if entry.is_frame_start else None
                f_end = (
                    entry.frame_end
                    if entry.is_frame_start and entry.is_frame_end
                    else None
                )
                entries_list.append((entry.text, entry.department, f_start, f_end))

        try:
            nw = now()
            for text, department, f_start, f_end in entries_list:
                create_entry(
                    Path(self.filepath),
                    text=text,
                    department=department,
                    author=get_user(context),
                    type=self.type,
                    response=self.response,
                    frame_reference=self.frame_reference,
                    f_start=f_start,
                    f_end=f_end,
                    review_id=hashlib.sha1(nw.encode("utf-8")).hexdigest()[:5]
                    if len(entries_list) > 1
                    else None,
                    referenced_version=self.referenced_version,
                    shot=None if self.shot_tag == "NONE" else self.shot_tag,
                )

        except PipelineError as e:
            log(e.level, "create_entry", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        self.report({"INFO"}, "Entry created.")
        context.window_manager.pipeline_entry_buffer.clear()
        return {"FINISHED"}


class M_PIPELINE_OT_edit_entry(bpy.types.Operator):
    """Edit an existing tracking entry."""

    bl_idname = "m_pipeline.edit_entry"
    bl_label = "Edit"

    id: bpy.props.StringProperty(default="")
    type: bpy.props.EnumProperty(
        items=[("note", "Note", ""), ("todo", "Todo", ""), ("rtk", "RTK", "")]
    )
    text: bpy.props.StringProperty()
    department: bpy.props.EnumProperty(items=tracked_department_items)
    filepath: bpy.props.StringProperty(default="")
    frame_reference: bpy.props.EnumProperty(
        items=[
            ("abs", "Absolute", ""),
            ("0", "Start at 0", ""),
            ("1", "Start at 1", ""),
        ],
        default="abs",
    )
    is_frame_start: bpy.props.BoolProperty(name="")
    frame_start: bpy.props.IntProperty(name="")
    is_frame_end: bpy.props.BoolProperty(name="")
    frame_end: bpy.props.IntProperty(name="")
    referenced_version: bpy.props.EnumProperty(items=entry_version_items)
    shot_tag: bpy.props.EnumProperty(
        name="Shot",
        description="Which shot in this block the entry is about, if any.",
        items=shot_tag_items,
    )

    custom_tooltip: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        if properties.custom_tooltip:
            return properties.custom_tooltip
        return "Edit this entry's text, type, or department."

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = bpy.data.filepath
        data = TrackingStatusCache.get(self.filepath)
        for e in data.get("entries", []):
            if e["id"] == self.id:
                self.type = e["type"]
                self.text = e["text"]
                self.department = e.get("department") or "NONE"
                # Stored "shot" may predate this being an enum (free text
                # back then, not validated) -- only keep it if it's still a
                # valid choice for this exact file (same digit width, still
                # among its shots); anything else falls back to "NONE"
                # rather than silently selecting the wrong shot.
                try:
                    digits = json_get(ConfigCache.get(), "naming.shot.digits", 3)
                    self.shot_tag = f"{int(e['shot']):0{digits}d}"
                except (KeyError, TypeError, ValueError):
                    self.shot_tag = "NONE"
                self.frame_reference = e.get("frame_reference", "abs")
                self.is_frame_start = "frame_start" in e
                self.frame_start = e.get("frame_start", 0)
                self.is_frame_end = "frame_end" in e
                self.frame_end = e.get("frame_end", 0)
                if e.get("referenced_version"):
                    try:
                        self.referenced_version = str(
                            to_absolute(e["referenced_version"])
                        )
                    except TypeError:
                        # Stored version no longer among entry_version_items()
                        # (file renamed/deleted since) -- leave the default.
                        pass
                break
        else:
            self.report({"ERROR"}, f"Entry with id {self.id} not found.")
            return {"CANCELLED"}

        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"id : {self.id}")
        layout.textbox(self, "text", initial_visible_lines=1)
        row = layout.row()
        row.prop(self, "type")
        row.prop(self, "frame_reference")
        layout.prop(self, "department")
        layout.prop(self, "referenced_version")
        layout.prop(self, "shot_tag")

        row = layout.row()
        txt = "Tag frame" if not self.is_frame_start else ""
        row.prop(self, "is_frame_start", text=txt)
        if self.is_frame_start:
            row.prop(self, "frame_start", text="")
            txt = "Add end frame" if not self.is_frame_end else ""
            row.prop(self, "is_frame_end", text=txt)
            if self.is_frame_end:
                row.prop(self, "frame_end", text="")

        op = layout.operator(
            "m_pipeline.delete_entry", text=f"Delete this {self.type} ?", icon="TRASH"
        )
        op.id = self.id
        op.filepath = self.filepath

    def execute(self, context):
        if not self.filepath:
            self.filepath = bpy.data.filepath

        f_start = self.frame_start if self.is_frame_start else None
        f_end = self.frame_end if self.is_frame_start and self.is_frame_end else None

        try:
            edit_entry(
                Path(self.filepath),
                text=self.text,
                department=self.department,
                editor=get_user(context),
                type=self.type,
                id=self.id,
                frame_reference=self.frame_reference,
                f_start=f_start,
                f_end=f_end,
                referenced_version=self.referenced_version,
                shot=None if self.shot_tag == "NONE" else self.shot_tag,
            )
        except PipelineError as e:
            log(e.level, "edit_entry", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        self.report({"INFO"}, "Entry updated.")
        return {"FINISHED"}


class M_PIPELINE_OT_generic_entry_button(bpy.types.Operator):
    """One entry's clickable title: click to reply, Ctrl+click to edit."""

    bl_idname = "m_pipeline.generic_entry_button"
    bl_label = ""

    id: bpy.props.StringProperty()
    filepath: bpy.props.StringProperty()
    custom_tooltip: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        if properties.custom_tooltip:
            return (
                properties.custom_tooltip + "\n\n[ clic to Reply or Ctrl+clic to Edit ]"
            )
        return "[ clic to Reply or Ctrl+clic to Edit]"

    def invoke(self, context, event):
        if event.ctrl:
            return bpy.ops.m_pipeline.edit_entry(
                "INVOKE_DEFAULT", id=self.id, filepath=self.filepath
            )
        return bpy.ops.m_pipeline.create_entry(
            "INVOKE_DEFAULT", response=self.id, filepath=self.filepath
        )

    def execute(self, context):
        return {"FINISHED"}


class M_PIPELINE_OT_delete_entry(bpy.types.Operator):
    """Delete a tracking entry, after confirmation."""

    bl_idname = "m_pipeline.delete_entry"
    bl_label = "Delete"
    bl_description = "Delete this entry."

    id: bpy.props.StringProperty()
    filepath: bpy.props.StringProperty(default="")

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        if not self.filepath:
            self.filepath = bpy.data.filepath
        try:
            delete_entry(Path(self.filepath), self.id)
        except PipelineError as e:
            log(e.level, "delete_entry", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        self.report({"INFO"}, "Entry deleted.")
        return {"FINISHED"}


class M_PIPELINE_OT_toggle_entry_task(bpy.types.Operator):
    """Flip a todo/rtk entry between done and not done."""

    bl_idname = "m_pipeline.toggle_entry_task"
    bl_label = ""
    bl_description = "Mark this todo/RTK entry as done, or undo that."

    id: bpy.props.StringProperty()
    filepath: bpy.props.StringProperty(default="")

    def execute(self, context):
        if not self.filepath:
            self.filepath = bpy.data.filepath
        try:
            toggle_entry_task(Path(self.filepath), self.id, get_user(context))
        except PipelineError as e:
            log(e.level, "toggle_entry_task", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        return {"FINISHED"}


class M_PIPELINE_OT_upload_csv(bpy.types.Operator):
    """Bulk-create tracking entries from a .csv file."""

    bl_idname = "m_pipeline.upload_csv"
    bl_label = ""
    bl_description = "Bulk-create tracking entries from a .csv file."

    csv_path: bpy.props.StringProperty(
        name="CSV file",
        subtype="FILE_PATH",
        description="Select your .csv file.",
        default="//",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Select your CSV file:", icon="FILE_FOLDER")
        layout.prop(self, "csv_path", text="")
        layout.label(
            text="Must contain at least 'text' and 'filename' in the header.",
            icon="INFO",
        )
        layout.label(
            text="('author', 'department' and 'type' can be specified in other columns.)",
            icon="INFO",
        )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):
        path = Path(bpy.path.abspath(self.csv_path))

        if not path.exists() or path.is_dir() or path.suffix != ".csv":
            self.report({"ERROR"}, "No valid CSV file selected.")
            return {"CANCELLED"}
        try:
            imported, total = upload_csv(path, get_user(context))
        except PipelineError as e:
            log(e.level, "csv_import", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        if imported < total:
            self.report(
                {"WARNING"},
                f"Imported {imported}/{total} entries (see log for skipped rows).",
            )
        else:
            self.report(
                {"INFO"}, f"Imported {imported} entr{'y' if imported == 1 else 'ies'}."
            )
        return {"FINISHED"}


class M_PIPELINE_OT_tracking_monitor(bpy.types.Operator):
    """Popup dashboard: every tracked asset/shot with its department status, filterable."""

    bl_idname = "m_pipeline.tracking_monitor"
    bl_label = ""
    bl_description = (
        "Show a popup view of all files in the project with their tracking status."
    )
    project_root: bpy.props.StringProperty()

    file_type: bpy.props.EnumProperty(
        items=[("asset", "Asset / Library", ""), ("shot", "Shot", "")],
        default="asset",
    )

    asset_prefix: bpy.props.EnumProperty(items=prefix_items)

    sequence: bpy.props.EnumProperty(items=sequence_items)

    # SKIP_SAVE: always reopen the popup on page 1 rather than remembering
    # the last page, since the file list (and thus the page count) can have
    # changed since the popup was last closed.
    page: bpy.props.IntProperty(default=1, min=1, options={"SKIP_SAVE"})
    PAGE_SIZE = 8

    entries_hide_done: bpy.props.BoolProperty(name="", default=True)
    entries_department_filter: bpy.props.EnumProperty(items=department_filter_items)
    entries_min_version: bpy.props.IntProperty(name="", default=0, min=0)

    def draw(self, context):

        layout = self.layout
        if context.window_manager.file_details_selected:
            draw_file_details(self, context, layout)

        else:
            filters = layout.box().split(factor=0.5)
            filters.label(text="Filters", icon="FILTER")
            filters_btn = filters.row()
            filters_btn.prop(self, "file_type", expand=True)

            if self.file_type == "asset":
                filters_btn.prop(self, "asset_prefix", text="")
                columns = json_get(ConfigCache.get(), "assets_departments", [])

            elif self.file_type == "shot":
                filters_btn.prop(self, "sequence", text="")
                columns = json_get(ConfigCache.get(), "shots_departments", [])

            layout.separator(factor=0.5)

            draw_monitor_table(self, context, layout, columns)

    def invoke(self, context, event):
        project_root = get_active_project_root()

        if project_root:
            TrackingStatusCache.get_all(project_root, force_reload=True)
            self.project_root = str(project_root)

            return context.window_manager.invoke_props_dialog(self, width=800)

    def execute(self, context):
        return {"FINISHED"}


class M_PIPELINE_OT_edit_description(bpy.types.Operator):
    """Edit an asset/shot's free-text description."""

    bl_idname = "m_pipeline.edit_description"
    bl_label = "Edit description"
    bl_description = "Edit this asset/shot's description."

    filepath: bpy.props.StringProperty(default="")
    description: bpy.props.StringProperty()

    def invoke(self, context, event):
        self.description = get_description(
            Path(self.filepath if self.filepath else bpy.data.filepath)
        )
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        layout.textbox(self, "description", initial_visible_lines=1)

    def execute(self, context):
        try:
            set_description(
                Path(self.filepath if self.filepath else bpy.data.filepath),
                self.description,
            )
        except PipelineError as e:
            log(e.level, "edit_description", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        self.report({"INFO"}, "Description updated.")
        return {"FINISHED"}


class M_PIPELINE_OT_toggle_worked_department(bpy.types.Operator):
    """Toggle one department on/off in the current file's 'worked this
    session' list. Writes straight to .wipmeta on click -- no popup, no
    batching, safe to click any time during the session (including never,
    if nothing was worked on)."""

    bl_idname = "m_pipeline.toggle_worked_department"
    bl_label = "Toggle department worked"
    bl_description = "Mark/unmark this department as worked on during this session."
    bl_options = {"INTERNAL"}

    department: bpy.props.StringProperty()

    def execute(self, context):
        filepath = Path(bpy.data.filepath)
        current = set(get_session_worked_departments(filepath))
        current.symmetric_difference_update({self.department})
        try:
            wipmeta_add_work(filepath, sorted(current))
        except PipelineError as e:
            log(e.level, "toggle_worked_department", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        return {"FINISHED"}


class M_PIPELINE_OT_toggle_validated_department(bpy.types.Operator):
    """Toggle one department's validated status directly, without cutting a
    new -stable version -- for departments (like "render") that aren't tied
    to editing the file itself. filepath: explicit, since this is also used
    from the monitoring dashboard on files that aren't the one currently open."""

    bl_idname = "m_pipeline.toggle_validated_department"
    bl_label = "Toggle department validated"
    bl_description = (
        "Mark/unmark this department as validated (no new stable version needed)."
    )
    bl_options = {"INTERNAL"}

    department: bpy.props.StringProperty()
    filepath: bpy.props.StringProperty(default="")
    custom_tooltip: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        if properties.custom_tooltip:
            return properties.custom_tooltip
        return (
            "Mark/unmark this department as validated (no new stable version needed)."
        )

    def execute(self, context):
        filepath = Path(self.filepath if self.filepath else bpy.data.filepath)
        current = get_current_departments(filepath)
        try:
            set_department_validated(
                filepath, self.department, not current.get(self.department, False)
            )
        except PipelineError as e:
            log(e.level, "toggle_validated_department", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        return {"FINISHED"}


class M_PIPELINE_OT_department_status_info(bpy.types.Operator):
    """Read-only tooltip carrier for a department status cell that isn't
    meant to be editable at its call site (the monitor grid, the sidebar's
    required-departments list) -- see M_PIPELINE_OT_toggle_validated_department
    for the one that actually toggles. Always drawn with enabled=False;
    execute() is unreachable in normal use, kept as a harmless no-op."""

    bl_idname = "m_pipeline.department_status_info"
    bl_label = ""
    bl_options = {"INTERNAL"}

    custom_tooltip: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        return properties.custom_tooltip or "Department status."

    def execute(self, context):
        return {"CANCELLED"}


class M_PIPELINE_OT_tracking_file_details(bpy.types.Operator):
    """Popup: department status and notes/todos for one tracked file."""

    bl_idname = "m_pipeline.tracking_file_details"
    bl_label = ""

    filepath: bpy.props.StringProperty()
    custom_tooltip: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        if properties.custom_tooltip:
            return properties.custom_tooltip
        return "Show tracking details for a selected file."

    def execute(self, context):
        if context.window_manager.file_details_selected == self.filepath:
            context.window_manager.file_details_selected = ""
        else:
            context.window_manager.file_details_selected = self.filepath
        return {"FINISHED"}
