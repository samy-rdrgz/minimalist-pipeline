"""Tracking panel in the 3D View sidebar: current file's department status and notes/todos."""

from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    TrackingStatusCache,
    WorkTimeCache,
    department_status_tooltip,
    draw_box_tip,
    filter_review_boxes,
    find_linked_by,
    format_duration,
    get_active_project_root,
    get_current_departments,
    get_description,
    get_entries,
    get_entries_grouped,
    get_linked_libraries,
    json_get,
    region_char_budget,
    responsive_layout,
    shots_in_segment,
    text_to_lines,
    to_absolute,
    to_relative,
)

# Fudge factor: entries end up nested a few columns/rows deep (see
# _draw_entry), and Blender doesn't expose a sub-layout's resolved width.
ENTRIES_INDENT_FACTOR = 0.8

TYPE_ICON = {
    "sh": "OUTLINER_OB_CAMERA",
    "ch": "OUTLINER_OB_ARMATURE",
    "pr": "AUTO",
    "mat": "MATERIAL",
    "env": "WORLD",
    "gn": "NODETREE",
    "tech": "SCRIPT",
    "fx": "SHADERFX",
    "asset": "ASSET_MANAGER",
}


def draw_tracking_data(context, box, filepath, required, width: int | None = None):

    if required:
        box.separator(factor=1)
        data = TrackingStatusCache.get(filepath)
        validated = get_current_departments(Path(filepath))
        deps = responsive_layout(context, box.box(), 200)
        deps.label(text="Finished :", icon="COLOR")
        col = deps.column(align=True)
        col.scale_y = 0.7
        for d in required:
            row = col.row()
            row.active = d in validated
            # Read-only here (toggling lives in the file_details popup):
            # enabled=False blocks clicks, the tooltip still shows on hover.
            row.enabled = False
            row.alignment = "LEFT"
            row.operator(
                "m_pipeline.department_status_info",
                text=d,
                icon="CHECKMARK" if d in validated else "CHECKBOX_DEHLT",
                emboss=False,
            ).custom_tooltip = department_status_tooltip(data, d)
        box.separator(factor=2)

    draw_entries(box, filepath, width=width)


def draw_entries(box, filepath, filters=None, width: int | None = None):
    """filters: object owning entries_hide_done/entries_department_filter/
    entries_min_version. Defaults to the WindowManager (one shared, global
    filter state) for the sidebar panel -- pass the popup's own operator
    instance instead when draw_entries() is showing a file that may differ
    from bpy.data.filepath (e.g. M_PIPELINE_OT_tracking_file_details), so its
    filters (and department dropdown, via department_filter_items' self.filepath
    fallback) stay scoped to that file instead of leaking into/from the panel."""
    filters = filters or bpy.context.window_manager
    title = box.column(align=True)
    title_row = title.box().row(align=True)
    title_row.prop(
        bpy.context.window_manager,
        "entries_collapse",
        icon="RIGHTARROW"
        if not bpy.context.window_manager.entries_collapse
        else "DOWNARROW_HLT",
        text="Notes & tasks",
        emboss=False,
    )
    btns = title_row.row(align=True)
    btn = btns.operator("m_pipeline.create_entry", icon="ADD", text="", emboss=False)
    btn.filepath = filepath
    btns.operator("m_pipeline.upload_csv", icon="IMPORT", text="", emboss=False)

    if bpy.context.window_manager.entries_collapse:
        draw_box_tip(
            title,
            bpy.context,
            "Note = a free remark. Todo = something still to do. RTK "
            "(retake) = a correction requested in review. Check it off "
            "once it's addressed.",
        )
        raw_boxes = get_entries_grouped(filepath)
        if raw_boxes:
            filters_row = title.row(align=True)
            filters_row.scale_y = 0.8
            filters_row.active = False
            filters_row.box().label(icon="FILTER")
            filters_row.box().prop(
                filters,
                "entries_department_filter",
                text="",
                emboss=False,
                icon="TAG",
            )
            filters_row.box().prop(
                filters,
                "entries_min_version",
                text="Since version",
                emboss=False,
                icon="CON_TRANSFORM_CACHE",
            )
            filters_row.box().prop(
                filters,
                "entries_hide_done",
                text="Hide done",
                icon="VIS_SEL_10" if filters.entries_hide_done else "VIS_SEL_00",
                emboss=False,
            )
            box.separator()

        review_boxes = filter_review_boxes(
            raw_boxes,
            hide_done=filters.entries_hide_done,
            department=filters.entries_department_filter,
            min_version=filters.entries_min_version,
        )
        reviews_col = box.column(align=True)
        if not review_boxes:
            box.label(
                text="No notes or tasks."
                if not raw_boxes
                else "No notes or tasks match the filters.",
                icon="BLANK1",
            )
        reviews_col.scale_y = 0.8
        for review_box in review_boxes:
            reviews_col.separator(factor=1.5)
            container = reviews_col.box().column(align=True)

            for thread in review_box["threads"]:
                thread_col = container.column(align=True)
                _draw_thread(thread, thread_col, filepath, width)
        box.separator()


def _draw_thread(thread, note, filepath, width: int | None = None):
    _draw_entry(thread["root"], note, filepath, width)
    done = thread["root"].get("done", False)

    replies = thread["replies"]
    for idx, reply in enumerate(replies):
        row = note.row(align=True)
        row.separator(factor=4)
        col = row.column(align=True)
        col.active = not (
            (done and reply.get("done", True)) or reply.get("done", False)
        )

        if idx == 0:
            col.separator(factor=0.2)
        _draw_entry(reply, col, filepath, width)

        if idx + 1 == len(replies):
            col.separator(factor=0.2)


def _draw_entry(e, note, filepath, width: int | None = None):
    """Draw one entry's title/author/action row plus its text body."""
    row = note.row(align=True)
    body = row.row(align=True)

    if e.get("done") is not None:
        btn = body.operator(
            "m_pipeline.toggle_entry_task",
            text="",
            icon="CHECKMARK" if e["done"] else "CHECKBOX_DEHLT",
            emboss=False,
        )
        btn.id = e["id"]
        btn.filepath = filepath

    else:
        body.label(
            text="",
            icon="LAYER_USED",
        )

    layout_text = body.column(align=True)
    layout_text.alignment = "LEFT"
    layout_text.active = e.get("done") is not True

    text = e["text"].split("\n")
    for i, line in enumerate(text):
        if i == 0:
            layout_line = layout_text.row(align=True)
            text_row = layout_line.row(align=True)
            frames_row = layout_line.row(align=True)
            btns_row = layout_line.row(align=True)
            if e.get("shot"):
                prefix = json_get(ConfigCache.get(), "naming.shot.prefix", "sh")
                line = f"[{prefix}{e['shot']}] {line}"
        else:
            layout_text.separator(factor=0.75)
            text_row = layout_text.row(align=True)

        text_row.separator(factor=0.65)
        text_row.alert = e.get("done") is False and e["type"] == "rtk"

        text_to_lines(text_row, line, max_width=width, scale_y=0.75)

    if e.get("frame_start"):
        frames_row.alignment = "LEFT"
        frames_row.scale_x = 0.85 - (
            0.25 / max(len(str(e.get("frame_start"))), len(str(e.get("frame_end"))))
        )
        frames_row.active = False
        ref = e.get("frame_reference")
        referenced_version = e.get("referenced_version")
        # Independent optional field -- see NOTES.md, "Entries: two fields".
        active_file = bool(referenced_version) and (
            to_absolute(referenced_version).parent == Path(bpy.data.filepath).parent
        )
        frames_row.enabled = active_file

        if ref in ("0", "1") and not active_file:
            base = 1 if ref == "0" else 0
            label = "{}th f"
        else:
            base = (
                bpy.context.scene.frame_start - int(ref)
                if active_file and ref in ("0", "1")
                else 0
            )
            label = "f {}"

        f_start = e["frame_start"] + base
        f_end = e["frame_end"] + base if e.get("frame_end") is not None else None

        frames_row.operator(
            "m_pipeline.current_frame",
            text=label.format(f_start),
            emboss=not e.get("done", False),
        ).frame = f_start
        if e.get("frame_end"):
            frames_row.operator(
                "m_pipeline.current_frame",
                text=label.format(f_end),
                emboss=not e.get("done", False),
            ).frame = f_end
        frames_row.separator(factor=0.75)

    btn = btns_row.row(align=True)
    btn.alignment = "RIGHT"
    btns = btn.row(align=True)
    btns.scale_x = 0.85

    btn = btns.operator(
        "m_pipeline.generic_entry_button",
        text="",
        icon="GRIP_CORNER_BOTTOM_RIGHT",
        emboss=False,
    )
    btn.id = e["id"]
    btn.filepath = filepath
    btn.custom_tooltip = _get_entry_tooltip(e, filepath)


def _get_entry_by_id(entries, id):
    for e in entries:
        if e.get("id") == id:
            return e
    return []


def _get_entry_tooltip(e, filepath):
    file = e.get("referenced_version")
    file = Path(file).stem if file else "unknown version"

    text = f"By : {e.get('author', 'unknown')}\nAt : {e['created_at'].replace('T', ' ')}\nBased on : {file}"
    if e.get("edited_by"):
        text = f"{text}\n\nEdited by : {e['edited_by']}\nAt : {e['edited_at'].replace('T', ' ')}"
    if e.get("department"):
        text = f"{text}\nFor department : {e.get('department')}"
    text = f"{text}\nId : {e.get('id')}{f' (review_id : {e.get('review_id')})' if e.get('review_id') else ''}"

    if e.get("response"):
        parent = _get_entry_by_id(get_entries(filepath), e.get("response"))
        if parent:
            quote = (
                f"{parent['text'][:20]}..."
                if len(parent["text"]) > 20
                else parent["text"][:20]
            )
            text = f"{text}\n\nIn response to : {parent.get('author', '//')} :\n   ''{quote}''"

        else:
            text = f"{text}\n\nIn response to a note that cannot be found"
    if e.get("done") is True:
        # Not always stamped -- see NOTES.md, "Entries: two fields".
        done_at = e.get("done_at")
        done_at = done_at.replace("T", " ") if done_at else "//"
        text = f"{text}\n\nDone by : {e.get('done_by', '//')}\nAt : {done_at}"
    return text


def draw_file_details(self, context, layout):

    box = layout
    row = box.row(align=True)

    row_left = row.box().row(align=True)
    row_left.alignment = "LEFT"
    row_left.operator(
        "m_pipeline.tracking_file_details",
        text="",
        icon="BACK",
        emboss=False,
    )

    filepath = context.window_manager.file_details_selected

    data = TrackingStatusCache.get(filepath)
    description = get_description(Path(filepath))

    # file_details_selected is the tracked folder, not a versioned .blend --
    # see NOTES.md.
    shot_prefix = json_get(ConfigCache.get(), "naming.shot.prefix", "sh")
    shot_name = Path(filepath).name
    is_shot = shot_name.startswith(shot_prefix)
    icon = TYPE_ICON.get(
        "sh" if is_shot else shot_name.split("_", 1)[0],
        "ASSET_MANAGER",
    )
    txt = (
        f"{Path(filepath).parent.name.upper()} {shot_name.upper()}"
        if is_shot
        else shot_name.upper()
    ) + (f" - {description}" if description else "")
    row_left = row.box().row(align=True)
    row_left.alignment = "EXPAND"
    row_left.label(text=txt, icon=icon)

    row_right = row.box().row(align=False)
    row_right.alignment = "RIGHT"
    row_right.operator(
        "m_pipeline.edit_description",
        text="",
        icon="GREASEPENCIL",
        emboss=False,
    ).filepath = filepath

    row_right.operator(
        "m_pipeline.open_file_version",
        text="",
        icon="FILE_ALIAS",
        emboss=False,
    ).filepath = str(filepath)

    op = row_right.operator(
        "wm.open_folder", text="", icon="FILE_FOLDER", emboss=False
    )
    op.filepath = str(filepath)
    op.custom_tooltip = "Open this file's folder"

    op = row_right.operator(
        "wm.open_folder", text="", icon="RENDER_STILL", emboss=False
    )
    op.filepath = str(to_absolute("renders/" + to_relative(Path(filepath))))
    op.custom_tooltip = "Open this file's render folder"

    if is_shot:
        try:
            is_block = len(shots_in_segment(shot_name[len(shot_prefix) :])) > 1
        except ValueError:
            is_block = False
        if is_block:
            op = row_right.operator(
                "m_pipeline.compile_preview",
                text="",
                icon="RENDER_ANIMATION",
                emboss=False,
            )
            op.scope = "block"
            op.filepath = filepath
            op.custom_tooltip = (
                "Compile a disposable preview from just this block's own shots."
            )

        op = row_right.operator(
            "m_pipeline.compile_preview", text="", icon="SEQUENCE", emboss=False
        )
        op.scope = "sequence"
        op.filepath = filepath
        op.custom_tooltip = (
            "Compile a disposable preview from every rendered shot in this sequence."
        )

    total_seconds = WorkTimeCache.get(filepath)
    if total_seconds:
        # Total only -- never a per-person/department breakdown, see
        # design.md "Work duration is logged, never surfaced per person".
        time_row = layout.row()
        time_row.active = False
        time_row.label(
            text=f"Total work time: {format_duration(total_seconds)}", icon="TIME"
        )

    layout.separator(factor=1)
    tabl = layout.row(align=True)
    tabl.alignment = "LEFT"

    required = data.get("departments_required", [])
    if required:
        deps_row = tabl.column(align=True)
        deps_row.scale_y = 0.8
        validated = get_current_departments(Path(filepath))
        txt = deps_row.row(align=True)
        txt.separator(factor=0.5)
        txt.label(text="Departments required for this file :", icon="TAG")
        for d in required:
            btn = deps_row.row(align=True)
            btn.label(text="", icon="BLANK1")
            btn.active = d in validated
            btn.alignment = "LEFT"
            op = btn.operator(
                "m_pipeline.toggle_validated_department",
                text=d.upper(),
                icon="CHECKMARK" if d in validated else "REMOVE",
                emboss=False,
            )
            op.department = d
            op.filepath = filepath
            op.custom_tooltip = department_status_tooltip(data, d)
    else:
        deps_row = tabl.column()
        deps_row.scale_y = 0.5
        deps_row.label(text="No departments required for this file.")
        deps_row.label(
            text="(editable via /.pipeline/tracking.json > departments_required)"
        )

    tabl.separator(factor=4)

    linked = get_linked_libraries(Path(filepath))
    linked_by = find_linked_by(get_active_project_root(), Path(filepath))
    if linked or linked_by:
        links_col = tabl.column(align=True)
        links_col.scale_y = 0.7
        if linked:
            # Group by linked file (one entry per datablock otherwise) and
            # dedupe (file, type, name) -- see NOTES.md.
            seen = set()
            by_folder: dict[Path, list[dict]] = {}
            for entry in linked:
                if not entry.get("file"):
                    continue
                key = (entry["file"], entry.get("type"), entry.get("name"))
                if key in seen:
                    continue
                seen.add(key)
                by_folder.setdefault(to_absolute(entry["file"]).parent, []).append(
                    entry
                )

            links_col.label(text="Links to:", icon="LINKED")
            for lib_dir, entries in by_folder.items():
                row = links_col.row(align=True)
                row.alignment = "LEFT"
                row.separator(factor=1.5)
                op = row.operator(
                    "m_pipeline.tracking_file_details",
                    text=f"{lib_dir.name} ({len(entries)})"
                    if len(entries) > 1
                    else lib_dir.name,
                    icon="BLANK1",
                    emboss=False,
                )
                op.filepath = str(lib_dir)
                op.custom_tooltip = "\n".join(
                    f"{e.get('type', '')} '{e.get('name', '')}'" for e in entries
                )
        if linked_by:
            links_col.label(text="Linked by:", icon="LINKED")
            for folder in linked_by:
                row = links_col.row(align=True)
                row.alignment = "LEFT"
                row.separator(factor=1.5)
                op = row.operator(
                    "m_pipeline.tracking_file_details",
                    text=folder.name,
                    icon="BLANK1",
                    emboss=False,
                )
                op.filepath = str(folder)

    layout.separator(factor=2)

    # draw_file_details() is only ever called from M_PIPELINE_OT_tracking_monitor's
    # draw() (invoke_props_dialog(width=800)) -- context.region there isn't
    # that dialog's own region, so region_char_budget(context) would size
    # this off a panel-sized guess. Pass the dialog's own real width instead
    # -- see region_char_budget()'s docstring / POPUP_WIDTH_SCALE in
    # lib/core.py for why it still needs correcting.
    width = int(region_char_budget(context, width_px=800) * ENTRIES_INDENT_FACTOR)
    draw_entries(layout.column(align=True), filepath, filters=self, width=width)
    layout.separator(factor=2)


def draw_monitor_table(self, context, layout, columns):
    """Filtered, paginated file list for M_PIPELINE_OT_tracking_monitor's main
    view -- self is that operator instance (file_type/asset_prefix/sequence/
    page state lives on it, same convention as draw_file_details() above)."""
    data = TrackingStatusCache.get_all(Path(self.project_root))
    FIRST_COLUMN = 0.3
    types = {
        "asset": json_get(ConfigCache.get(), "structure.asset_prefixes")
        + json_get(ConfigCache.get(), "structure.library_prefixes"),
        "shot": json_get(ConfigCache.get(), "naming.sequence.prefix"),
    }

    matches = []
    for dir, file in data:
        if (
            self.file_type == "asset"
            and file.get("file_name") is not None
            and (
                (file["file_name"].split("_", 1)[0] in types["asset"])
                if self.asset_prefix == "all" and file["file_name"]
                else (file["file_name"].split("_", 1)[0] == self.asset_prefix)
            )
        ) or (
            self.file_type == "shot"
            and file.get("file_name") is not None
            and (
                (file["file_name"].startswith(types[self.file_type]))
                if self.sequence == "all"
                else (file["file_name"].split("_", 1)[0] == self.sequence)
            )
        ):
            matches.append((dir, file))

    # file_name is zero-padded prefix/sequence/shot numbers (see
    # naming.sequence/shot in config), so plain alphabetical sort already
    # gives prefix+alpha order for assets and sequence+shot order for
    # shots -- no separate sort key needed per file_type.
    matches.sort(key=lambda m: m[1].get("file_name") or "")

    # Fixed number of rows per page (padded with blanks below) so the
    # popup's height stays constant across pages and filters -- it would
    # otherwise resize on every redraw, which reads as the window
    # jumping around.
    total = len(matches)
    total_pages = max(1, -(-total // self.PAGE_SIZE))  # ceil division
    self.page = max(1, min(self.page, total_pages))
    page_items = matches[(self.page - 1) * self.PAGE_SIZE : self.page * self.PAGE_SIZE]

    f_list = layout.box()
    title_list = f_list.split(factor=FIRST_COLUMN)
    title_list.active = False
    title_list.label(text="File", icon="RADIOBUT_ON")
    deps = title_list.row()
    for c in columns:
        deps.label(text=c.capitalize(), icon="KEYFRAME_HLT")

    f_list.separator(factor=1)

    for dir, file in page_items:
        _draw_monitor_row(self, f_list, dir, file, columns, FIRST_COLUMN)

    for _ in range(self.PAGE_SIZE - len(page_items)):
        _draw_monitor_blank_row(f_list, columns, FIRST_COLUMN)

    footer = f_list.row()
    footer.active = False
    if total == 0:
        footer.label(text="No files found with this filter", icon="ERROR")
    else:
        footer.label(text=f"{total} file(s) found", icon="BLANK1")
        if total_pages > 1:
            pager = footer.row(align=True)
            pager.alignment = "RIGHT"
            pager.label(text=f"Page {self.page} / {total_pages}")
            pager.prop(self, "page", text="")


def _draw_monitor_row(self, f_list, dir, file, columns, first_column):
    row = f_list.column()
    split = row.split(factor=first_column)
    name = split.row()
    name.alignment = "LEFT"
    icon = (
        TYPE_ICON.get(
            file.get("file_name", "Unknown").split("_", 1)[0],
            "ASSET_MANAGER",
        )
        if self.file_type == "asset"
        else TYPE_ICON.get("sh", "OUTLINER_OB_CAMERA")
    )
    op = name.operator(
        "m_pipeline.tracking_file_details",
        text=file.get("file_name", "Unknown"),
        icon=icon,
        emboss=False,
    )
    op.filepath = str(dir)
    op.custom_tooltip = file.get("description", "")

    details = name.row()
    details.alignment = "RIGHT"
    details.active = False
    details.operator(
        "m_pipeline.open_file_version",
        text="",
        icon="FILE_ALIAS",
        emboss=False,
    ).filepath = str(dir)
    deps_row = split.row()
    for c in columns:
        icon_row = deps_row.row()
        icon_row.label(text="", icon="BLANK1")
        if c in file.get("departments_required", []):
            icon_row.alert = _has_rtk(file, c)
            # Read-only status: enabled=False blocks any click (no
            # accidental toggling from this grid -- that's file_details'
            # job), the tooltip is still shown on hover.
            status = icon_row.row()
            status.enabled = False
            tooltip = department_status_tooltip(file, c)
            if (
                c in file["validated_departments"]
                and c not in file["worked_departments"]
            ):
                text, row_icon = "Finished", "CHECKMARK"
            elif c in file["validated_departments"] and c in file["worked_departments"]:
                text, row_icon = "Under RTK", "CHECKBOX_DEHLT"
            elif (
                c not in file["validated_departments"]
                and c in file["worked_departments"]
            ):
                text, row_icon = "Wip", "CHECKBOX_DEHLT"
            else:
                text, row_icon = "Not started", "CHECKBOX_DEHLT"
            status.operator(
                "m_pipeline.department_status_info",
                text=text,
                icon=row_icon,
                emboss=False,
            ).custom_tooltip = tooltip
        else:
            icon_row.label(text=" ", icon="BLANK1")
    f_list.separator(factor=0.5, type="LINE")


def _draw_monitor_blank_row(f_list, columns, first_column):
    """Empty placeholder row, same height as a real one, so a half-filled
    last page doesn't shrink the popup."""
    row = f_list.column()
    row.active = False
    split = row.split(factor=first_column)
    split.row().label(text="")
    deps_row = split.row()
    for c in columns:
        deps_row.row().label(text="", icon="BLANK1")
    f_list.separator(factor=0.5, type="LINE")


def _has_rtk(data: dict, department: str) -> bool:
    """Whether data has an un-done RTK entry tagged with department."""
    if "entries" in data:
        for e in data["entries"]:
            if e.get("department") == department and e.get("done") is False:
                return True
    return False
