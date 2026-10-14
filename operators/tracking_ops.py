"""Tracking operators: CRUD on note/todo/rtk entries, prod snapshot export and review import, monitoring popups."""

import hashlib
from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    PipelineError,
    ProjectScan,
    SnapshotJob,
    TrackingStatusCache,
    build_snapshot,
    clear_render_to_check,
    create_entry,
    delete_entry,
    department_filter_items,
    edit_entry,
    entry_version_items,
    get_active_project_root,
    get_addon_version,
    get_current_departments,
    get_departments_required,
    get_last_stable,
    get_description,
    get_session_worked_departments,
    get_user,
    import_review_xlsx,
    json_get,
    log,
    now,
    prefix_items,
    read_json_quiet,
    read_snapshot_data,
    review_description_changes,
    resolve_ffmpeg,
    sequence_items,
    set_department_validated,
    set_description,
    shot_tag_items,
    snapshot_filename,
    text_field,
    thumbnail_size,
    to_absolute,
    toggle_entry_task,
    tracked_department_items,
    tracking_json_path,
    wipmeta_add_work,
    write_snapshot,
)
from ..farm import archive
from ..panels import (
    draw_file_details,
    draw_monitor_table,
    load_file_renders,
    load_file_thumbnail,
    popup_width,
)

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
        tracking_file = tracking_json_path(target)
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
        if len(shot_tag_items(self, context)) > 2:
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
            text_field(row, entry, "text", initial_visible_lines=1)
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
            text_field(row, entry, "text", initial_visible_lines=1)
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
                # Stored department may no longer be among this project's
                # configured departments (renamed/removed since, or stale
                # data) -- fall back to "NONE" rather than crashing invoke().
                try:
                    self.department = e.get("department") or "NONE"
                except TypeError:
                    self.department = "NONE"
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
        TITLE_WIDTH = 0.35
        layout = self.layout.column(align=True)

        col = layout.column()
        col.active = False
        col.scale_y = 0.6
        col.label(text=f"id : {self.id}", icon="INFO")
        layout.separator()

        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Text", icon="TEXT")
        text_field(row, self, "text", initial_visible_lines=1)

        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Type", icon="TRIA_RIGHT")
        row.prop(self, "type", text="")

        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Department", icon="COLOR")
        row.prop(self, "department", text="")

        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Version", icon="LINKED")
        row.prop(self, "referenced_version", text="")

        if len(shot_tag_items(self, context)) > 2:
            row = layout.split(factor=TITLE_WIDTH, align=True)
            row.label(text="Shot", icon="CAMERA_DATA")
            row.prop(self, "shot_tag", text="")

        layout.separator(type="LINE", factor=3)

        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Frame", icon="KEYFRAME")
        row = row.row(align=True)
        txt = "Tag frame" if not self.is_frame_start else ""
        row.prop(self, "is_frame_start", text=txt)
        if self.is_frame_start:
            row.prop(self, "frame_start", text="")
            txt = "Add end frame" if not self.is_frame_end else ""
            row.separator()
            row.prop(self, "is_frame_end", text=txt)
            if self.is_frame_end:
                row.prop(self, "frame_end", text="")

        row = layout.split(factor=TITLE_WIDTH, align=True)
        row.label(text="Reference", icon="BLANK1")
        row.prop(self, "frame_reference", text="")

        layout.separator(factor=2)
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


class M_PIPELINE_OT_import_review(bpy.types.Operator):
    """Import the notes from a filled-in snapshot review spreadsheet."""

    bl_idname = "m_pipeline.import_review"
    bl_label = "Import review"
    bl_description = (
        "Create notes from a review spreadsheet sent back by production "
        "(the .xlsx downloaded from a snapshot). Lines already imported are "
        "skipped"
    )

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.xlsx", options={"HIDDEN"})

    def invoke(self, context, event):
        if not get_active_project_root():
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        path = Path(bpy.path.abspath(self.filepath))
        if not path.is_file() or path.suffix.lower() != ".xlsx":
            self.report({"ERROR"}, "No valid .xlsx file selected.")
            return {"CANCELLED"}
        try:
            result = import_review_xlsx(path)
        except PipelineError as e:
            log(e.level, "review_import", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        for label, reason in result["skipped"]:
            log("WARNING", "review_import", f"{path.name}: {label} -- {reason}")
        log(
            "INFO",
            "review_import",
            f"{path.name}: {result['imported']} imported, "
            f"{result['duplicates']} already there, {len(result['skipped'])} skipped",
        )
        try:
            _description_changes[:] = review_description_changes(path)
        except PipelineError as e:
            log(e.level, "review_import", e.message)
            _description_changes.clear()
        if not (any(result.values()) or _description_changes):
            # Nothing at all: most likely the blank template, not the
            # filled-in one sent back.
            _show_import_summary(
                f"Nothing to import in {path.name}: no note and no description "
                "change.\nIs it the filled-in file sent back?",
                "QUESTION",
            )
            return {"FINISHED"}
        lines = [f"{result['imported']} note(s) imported"]
        if result["duplicates"]:
            lines.append(f"{result['duplicates']} already imported before, skipped")
        if result["skipped"]:
            lines.append(f"{len(result['skipped'])} not imported:")
            lines += [f"   {label} -- {reason}" for label, reason in result["skipped"][:8]]
            if len(result["skipped"]) > 8:
                lines.append(f"   ... and {len(result['skipped']) - 8} more (see log)")
        message = "\n".join(lines)
        icon = "ERROR" if result["skipped"] else "CHECKMARK"
        # Deferred one tick: chaining a popup from execute() -- see NOTES.md,
        # "Popup-chaining".
        if _description_changes:
            bpy.app.timers.register(
                lambda: bpy.ops.m_pipeline.review_descriptions(
                    "INVOKE_DEFAULT", summary=message, icon=icon
                )
                and None,
                first_interval=0.05,
            )
        else:
            _show_import_summary(message, icon)
        return {"FINISHED"}


def _show_import_summary(message: str, icon: str) -> None:
    """The review import's result popup, one tick later (popup-chaining)."""
    bpy.app.timers.register(
        lambda: bpy.ops.m_pipeline.text_popup(
            "INVOKE_DEFAULT", title="Review import", message=message, icon=icon
        )
        and None,
        first_interval=0.05,
    )


# Descriptions a review import would change, waiting for the confirm
# dialog (M_PIPELINE_OT_review_descriptions): all applied, or none.
_description_changes: list[dict] = []
# Lines the confirm dialog lists; the rest is counted, applied all the same.
_DESCRIPTIONS_SHOWN = 20


class M_PIPELINE_OT_review_descriptions(bpy.types.Operator):
    """Confirm the description changes of an imported review: all or none."""

    bl_idname = "m_pipeline.review_descriptions"
    bl_label = ""
    bl_options = {"INTERNAL"}

    summary: bpy.props.StringProperty()  # the notes import's result
    icon: bpy.props.StringProperty(default="CHECKMARK")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self,
            width=700,
            title="Review import: descriptions changed",
            confirm_text=f"Apply {len(_description_changes)} description(s)",
        )

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="The review changes these descriptions. Apply them all?")
        col.label(text="(To leave one out, fix it in the spreadsheet and re-import.)")
        col.separator()
        for change in _description_changes[:_DESCRIPTIONS_SHOWN]:
            col.label(text=change["name"], icon="GREASEPENCIL")
            was = col.row()
            was.active = False
            was.label(text=f"     was: {change['old'][:140] or '(empty)'}")
            col.label(text=f"     now: {change['new'][:140]}")
        rest = len(_description_changes) - _DESCRIPTIONS_SHOWN
        if rest > 0:
            col.label(text=f"... and {rest} more", icon="BLANK1")

    def execute(self, context):
        applied, failed = 0, []
        for change in _description_changes:
            try:
                set_description(Path(change["filepath"]), change["new"])
                TrackingStatusCache.get(change["filepath"], force_reload=True)
                applied += 1
            except PipelineError as e:
                failed.append(change["name"])
                log(e.level, "review_import", f"{change['name']}: {e.message}")
        log("INFO", "review_import", f"{applied} description(s) updated")
        _description_changes.clear()
        summary = f"{self.summary}\n{applied} description(s) updated"
        if failed:
            summary += f"\nNot updated (see log): {', '.join(failed)}"
        _show_import_summary(summary, "ERROR" if failed else self.icon)
        return {"FINISHED"}

    def cancel(self, context):
        _description_changes.clear()
        _show_import_summary(f"{self.summary}\nDescriptions left unchanged", self.icon)


class M_PIPELINE_OT_export_snapshot(bpy.types.Operator):
    """Write a self-contained HTML snapshot of the project's state."""

    bl_idname = "m_pipeline.export_snapshot"
    bl_label = "Export snapshot"
    bl_description = (
        "Write one HTML file showing every asset/shot's status and open notes, "
        "readable offline without Blender, with a review spreadsheet inside "
        "to send back"
    )

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.html", options={"HIDDEN"})
    include_thumbnails: bpy.props.BoolProperty(
        name="Thumbnails",
        default=True,
        description=(
            "Show a thumbnail per asset/shot, from its latest render. Missing "
            "or outdated ones are made first, in the background"
        ),
    )

    _job = None
    _warnings: list = []
    _timer = None
    _root = None
    _writing = False

    def invoke(self, context, event):
        root = get_active_project_root()
        if not root:
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        meta = {"project": json_get(ConfigCache.get(), "project_name") or root.name}
        # The project's snapshots/ folder, fresh dated name -- the browser
        # can still go elsewhere.
        folder = ConfigCache.get_path("snapshots")
        try:
            folder.mkdir(exist_ok=True)
        except OSError:
            folder = Path(root)
        self.filepath = str(
            folder / snapshot_filename({"meta": {**meta, "scan_started_at": now()}})
        )
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        self._root = get_active_project_root()
        if not self._root:
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        if not self.filepath.lower().endswith(".html"):
            self.filepath += ".html"
        # Disk reads, then render+write, each on a thread: a full walk takes
        # seconds on a share, and the target folder can be on it too.
        v_prefix = json_get(ConfigCache.get(), "naming.version.prefix", "v")
        thumbnails = None
        if self.include_thumbnails:
            thumbnails = {
                "size": thumbnail_size(ConfigCache.get()),
                "blender": bpy.app.binary_path,
                "ffmpeg": resolve_ffmpeg(),
            }
        self._job = SnapshotJob(read_snapshot_data, self._root, thumbnails, v_prefix)
        self._writing = False
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        self.report({"INFO"}, "Scanning project for the snapshot...")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type != "TIMER" or not self._job.done:
            return {"PASS_THROUGH"}
        if self._job.error:
            context.window_manager.event_timer_remove(self._timer)
            log("ERROR", "snapshot", f"Snapshot failed: {self._job.error}")
            self.report({"ERROR"}, "Snapshot failed (see log).")
            return {"CANCELLED"}
        if not self._writing:
            config = ConfigCache.get()
            meta = {
                "project": json_get(config, "project_name") or self._root.name,
                "scan_started_at": self._job.started_at,
                "exported_by": get_user(context),
                "addon_version": get_addon_version(),
            }
            try:
                snapshot = build_snapshot(self._job.result, config, meta)
            except Exception as e:
                context.window_manager.event_timer_remove(self._timer)
                log("ERROR", "snapshot", f"Snapshot failed: {e}")
                self.report({"ERROR"}, "Snapshot failed (see log).")
                return {"CANCELLED"}
            self._warnings = snapshot["meta"]["thumbnail_warnings"]
            self._job = SnapshotJob(write_snapshot, snapshot, Path(self.filepath))
            self._writing = True
            return {"PASS_THROUGH"}
        context.window_manager.event_timer_remove(self._timer)
        log("INFO", "snapshot", f"Snapshot written to {self.filepath}")
        for w in self._warnings:
            log("WARNING", "snapshot", f"Thumbnail not made: {w}")
        if self._warnings:
            # A multilayer EXR needs ffmpeg: another machine that has it
            # can fill the gaps with a new export.
            self.report(
                {"WARNING"},
                f"Snapshot written: {Path(self.filepath).name} -- "
                f"{len(self._warnings)} thumbnail(s) could not be made (see log)",
            )
        else:
            self.report({"INFO"}, f"Snapshot written: {Path(self.filepath).name}")
        return {"FINISHED"}


class M_PIPELINE_OT_tracking_refresh(bpy.types.Operator):
    """Re-scan the whole project for Project monitoring."""

    bl_idname = "m_pipeline.tracking_refresh"
    bl_label = "Refresh"
    bl_description = (
        "Re-scan the project's tracking data. The monitoring view otherwise "
        "shows what was found when it opened -- a full scan costs seconds "
        "on a network share, too much for every redraw."
    )

    def execute(self, context):
        project_root = get_active_project_root()
        if project_root:
            # Background scan, never blocks -- the table fills in as it goes.
            ProjectScan.start(project_root)
        return {"FINISHED"}


def _back_to_first_page(self, context):
    self.page = 1


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
    # Set by invoke() from the window (panels.popup_width()).
    popup_width: bpy.props.IntProperty(options={"SKIP_SAVE", "HIDDEN"})

    entries_hide_done: bpy.props.BoolProperty(name="", default=True)
    entries_department_filter: bpy.props.EnumProperty(items=department_filter_items)
    entries_min_version: bpy.props.IntProperty(name="", default=0, min=0)
    only_to_check: bpy.props.BoolProperty(
        name="",
        default=False,
        description="Only the files with a farm render waiting to be checked",
    )
    # SKIP_SAVE: a search left over from last time would silently hide files.
    search: bpy.props.StringProperty(
        name="",
        description="Filter by file name or description",
        options={"SKIP_SAVE"},
        update=_back_to_first_page,
    )

    def draw(self, context):
        layout = self.layout
        if context.window_manager.file_details_selected:
            draw_file_details(self, context, layout)

        else:
            filters = layout.box().split(factor=0.3)
            filters.label(text="Filters", icon="FILTER")
            filters_btn = filters.row()
            filters_btn.prop(self, "file_type", expand=True)

            if self.file_type == "asset":
                filters_btn.prop(self, "asset_prefix", text="")
                columns = json_get(ConfigCache.get(), "assets_departments", [])

            elif self.file_type == "shot":
                filters_btn.prop(self, "sequence", text="")
                columns = json_get(ConfigCache.get(), "shots_departments", [])

            filters_btn.prop(self, "search", text="", icon="VIEWZOOM")
            # Icon only: the property's description is the tooltip.
            filters_btn.prop(self, "only_to_check", text="", icon="HIDE_OFF")

            layout.separator(factor=0.5)

            draw_monitor_table(self, context, layout, columns)

    def invoke(self, context, event):
        project_root = get_active_project_root()

        if project_root:
            # Opens at once on what's already known; ProjectScan refreshes the
            # whole project in the background (see its docstring) -- a
            # blocking scan froze Blender for minutes on a network share.
            ProjectScan.start(project_root)
            self.project_root = str(project_root)

            # Kept: draw_file_details() wraps its text on it.
            self.popup_width = popup_width(context)
            return context.window_manager.invoke_props_dialog(
                self, width=self.popup_width
            )

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
        text_field(layout, self, "description", initial_visible_lines=1)

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


class PIPELINE_PG_department_check_item(bpy.types.PropertyGroup):
    """One department "Checked" offers to validate along with the render --
    a checklist row, like the Render dialog's shots (a dynamic ENUM_FLAG
    draws as an empty box in a dialog)."""

    department: bpy.props.StringProperty()
    validate: bpy.props.BoolProperty(name="", default=False)


class M_PIPELINE_OT_render_checked(bpy.types.Operator):
    """Mark a farm render as checked: it leaves the "To check" column. Asks
    first which of the file's departments to validate along with it."""

    bl_idname = "m_pipeline.render_checked"
    bl_label = ""

    filepath: bpy.props.StringProperty()
    shot: bpy.props.StringProperty()
    all_shots: bpy.props.BoolProperty(options={"SKIP_SAVE"})
    custom_tooltip: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        if properties.custom_tooltip:
            return properties.custom_tooltip
        return "Mark this render as checked."

    def invoke(self, context, event):
        # The checklist: the required departments not validated yet.
        checklist = context.window_manager.render_checked_departments
        checklist.clear()
        folder = Path(self.filepath)
        try:
            required = get_departments_required(folder) or []
        except PipelineError:
            required = []
        current = get_current_departments(folder)
        todo = [d for d in required if not current.get(d)]
        # Validating needs a stable version (set_department_validated()).
        if not todo or "file" not in get_last_stable(folder):
            return self.execute(context)
        for department in todo:
            item = checklist.add()
            item.department = department
            item.validate = department == "render"
        return context.window_manager.invoke_props_dialog(
            self, width=300, title="Render checked", confirm_text="Mark checked"
        )

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text="Validate as well:")
        for item in context.window_manager.render_checked_departments:
            col.prop(item, "validate", text=item.department.upper())

    def execute(self, context):
        try:
            job_ids = clear_render_to_check(
                self.filepath, None if self.all_shots else self.shot
            )
        except PipelineError as e:
            log(e.level, "render_checked", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        checklist = context.window_manager.render_checked_departments
        for department in [i.department for i in checklist if i.validate]:
            try:
                set_department_validated(Path(self.filepath), department, True)
            except PipelineError as e:
                log(e.level, "render_checked", e.message)
                self.report({e.level}, e.message)
        # The table only reads the cache: refresh this one folder now.
        TrackingStatusCache.get(self.filepath, force_reload=True)
        for job_id in job_ids:
            _archive_checked_job(job_id)
        checklist.clear()  # filled again by the next invoke()
        return {"FINISHED"}


_VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi")


class M_PIPELINE_OT_open_render_video(bpy.types.Operator):
    """Play a farm render's compiled video with the system's player."""

    bl_idname = "m_pipeline.open_render_video"
    bl_label = ""

    render: bpy.props.StringProperty()  # its folder, project-relative
    video: bpy.props.StringProperty()  # the job's compiled_output_path
    custom_tooltip: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        return properties.custom_tooltip or "Play this render's video."

    def execute(self, context):
        try:
            video = self._find()
        except (PipelineError, OSError) as e:
            self.report({"ERROR"}, f"Could not look for the video: {e}")
            return {"CANCELLED"}
        if not video:
            self.report({"WARNING"}, "No video found for this render.")
            return {"CANCELLED"}
        return bpy.ops.wm.open_folder(filepath=str(video))

    def _find(self) -> Path | None:
        video = to_absolute(self.video) if self.video else None
        if video and video.is_file():
            return video
        if not self.render:
            return None
        # Flagged before the video was recorded: the newest one in the
        # render's folder.
        folder = to_absolute(self.render)
        if not folder.is_dir():
            return None
        videos = [f for f in folder.iterdir() if f.suffix.lower() in _VIDEO_EXTS]
        return max(videos, key=lambda f: f.stat().st_mtime, default=None)


def _archive_checked_job(job_id: str) -> None:
    """A checked render's job leaves the Farm popup's list too -- if it's
    still in active/ and done. Never raises: the check itself went through."""
    job_path = ConfigCache.get_path("farm_actives") / f"{job_id}.json"
    data = read_json_quiet(job_path)
    if not data:
        return  # already archived by hand, or never there
    stages = [s.get("stage") for s in data.get("stage_history") or []]
    if "finished" not in stages:
        return
    try:
        archive(job_path)
    except OSError as e:
        log("WARNING", "render_checked", f"Could not archive {job_id}: {e}")


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
            load_file_thumbnail(self.filepath)
            load_file_renders(self.filepath)
        return {"FINISHED"}
