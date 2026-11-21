"""Tracking panel in the 3D View sidebar: current file's department status and notes/todos."""

from pathlib import Path


import bpy
import bpy.utils.previews

from ..lib import (
    APPROVAL_SOURCE,
    REVIEW_SOURCE,
    TEAM_REVIEW_SOURCE,
    ConfigCache,
    TrackingStatusCache,
    draw_box_tip,
    entry_departments,
    filter_review_boxes,
    get_entries,
    get_entries_grouped,
    json_get,
    local_time,
    open_task_counts,
    project_path,
    safe_icon,
    text_to_lines,
)
from ..lib.ui import icon_button

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
    """The File panel's notes & tasks. Its departments: the live page's
    file detail (the panel's Details button)."""
    if required:
        box.separator(factor=1)
    draw_entries(box, filepath, width=width)


def draw_entries(box, filepath, width: int | None = None):
    """Draw a file's entries, filtered by the WindowManager's
    entries_hide_done / entries_department_filter / entries_min_version."""
    filters = bpy.context.window_manager
    title = box.column(align=True)
    title_row = title.box().row(align=True)
    # Title on the left with what's left to do (open RTKs red, todos grey,
    # folded or not), the + on the right.
    left = title_row.row(align=True)
    left.alignment = "LEFT"
    left.prop(
        filters,
        "entries_collapse",
        icon="DOWNARROW_HLT" if filters.entries_collapse else "RIGHTARROW",
        text="Notes & tasks",
        emboss=False,
    )
    rtk, todo = open_task_counts(TrackingStatusCache.get(filepath))
    # Each count its own LEFT row: its text's width, not a share of the row.
    if rtk:
        red = left.row(align=True)
        red.alignment = "LEFT"
        red.alert = True
        red.label(text=f"{rtk} RTK")
    if todo:
        grey = left.row(align=True)
        grey.alignment = "LEFT"
        grey.active = False
        grey.label(text=f"{todo} todo")
    right = title_row.row(align=True)
    right.alignment = "RIGHT"
    btn = right.operator("m_pipeline.create_entry", icon="ADD", text="", emboss=False)
    btn.filepath = filepath

    if filters.entries_collapse:
        draw_box_tip(
            title,
            bpy.context,
            "Note = a free remark. Todo = something still to do. RTK "
            "(retake) = a correction requested in review. Check it off "
            "once it's addressed. Right-click one's icons: reply, edit, "
            "tick, delete.",
        )
        raw_boxes = get_entries_grouped(filepath)
        if raw_boxes:
            filters_row = title.row(align=True)
            filters_row.scale_y = 0.8
            wide = width is not None and width > 80
            if wide:  # a monitoring window: sized, not stretched across it
                filters_row.alignment = "LEFT"
            # Hide done first, the one switched most (done RTKs, to check a
            # render against): not greyed out. Each in a box, one height.
            done = filters_row.box()
            done.prop(
                filters,
                "entries_hide_done",
                text="Hide done",
                icon="HIDE_ON" if filters.entries_hide_done else "HIDE_OFF",
                emboss=False,
            )
            others = filters_row.row(align=True)
            others.active = False
            department = others.box()
            department.prop(
                filters,
                "entries_department_filter",
                text="",
                emboss=False,
                icon="TAG",
            )
            version = others.box()
            version.prop(
                filters,
                "entries_min_version",
                text="Since version",
                emboss=False,
                icon="CON_TRANSFORM_CACHE",
            )
            if wide:
                done.ui_units_x = 6
                department.ui_units_x = 9
                version.ui_units_x = 8
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
        for review_box in _approval_runs(review_boxes):
            reviews_col.separator(factor=1.5)
            if "approvals" in review_box:
                _draw_approvals(
                    reviews_col.box().column(align=True), review_box["approvals"]
                )
                continue
            container = reviews_col.box().column(align=True)

            for thread in review_box["threads"]:
                thread_col = container.column(align=True)
                _draw_thread(thread, thread_col, filepath, width)
        box.separator()


def _approval_note(review_box: dict) -> dict | None:
    """The note a validation wrote, when it's all this box holds (no reply)."""
    threads = review_box["threads"]
    if len(threads) != 1 or threads[0]["replies"]:
        return None
    e = threads[0]["root"]
    return e if e.get("source") == APPROVAL_SOURCE else None


def _approval_runs(review_boxes: list) -> list:
    """review_boxes with the notes validations wrote, one after another, in
    one box: {"approvals": [entry, ...]} -- read as a line per role,
    stable and way (validated / withdrawn), not a box per department."""
    out = []
    for review_box in review_boxes:
        e = _approval_note(review_box)
        if e is None:
            out.append(review_box)
        elif out and "approvals" in out[-1]:
            out[-1]["approvals"].append(e)
        else:
            out.append({"approvals": [e]})
    return out


def _draw_approvals(col, entries: list) -> None:
    """Validation notes, compact: "★ prod  fixanim, render-ld  v003-stable",
    a line per role, stable and way, newest first -- each note in its tooltip."""
    lines: dict[tuple, list] = {}
    for e in entries:
        withdrawn = e.get("text", "").startswith("Validation withdrawn")
        stable = Path(e.get("referenced_version") or "").stem
        key = (e.get("role") or "?", stable, withdrawn)
        lines.setdefault(key, []).append(e)
    for (role, stable, withdrawn), group in lines.items():
        departments = []
        for e in group:
            for d in entry_departments(e):
                if d not in departments:
                    departments.append(d)
        row = col.row(align=True)
        op = row.operator(
            "m_pipeline.department_status_info",
            text="",
            icon="SOLO_OFF" if withdrawn else "SOLO_ON",
            emboss=False,
        )
        op.custom_tooltip = "\n".join(
            f"{e.get('text', '')} -- {e.get('author', '?')}, "
            f"{local_time(e.get('created_at'))}"
            for e in group
        )
        what = " withdrawn" if withdrawn else ""
        row.label(text=f"{role}{what}: {', '.join(departments)}")
        version = row.row(align=True)
        version.alignment = "RIGHT"
        version.active = False
        version.label(text=stable.rsplit("_", 1)[-1] if stable else "")


def _draw_thread(thread, note, filepath, width: int | None = None):
    """A thread: its root entry, then its replies indented, greyed once done."""
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

    # Right-click on its icons: reply, edit, tick, delete.
    # Written under a validation role: its box, tick and dot violet (the
    # page's review colour); the team's Blender's own.
    role = bool(e.get("role"))
    if e.get("done") is not None:
        icon = (
            ("mark:check_role" if role else "CHECKMARK")
            if e["done"]
            else ("mark:box_role" if role else "CHECKBOX_DEHLT")
        )
        icon_button(
            body,
            "m_pipeline.toggle_entry_task",
            icon,
            id=e["id"],
            filepath=filepath,
            rmb="entry",
        )
    else:
        # A button, not a label: it takes the right-click menu (and a click
        # replies, as the grip on the right).
        _entry_button(body, e, filepath, "mark:dot_role" if role else "LAYER_USED")

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
        # Red text: an open RTK from a validation role (the team's has its
        # orange mark).
        text_row.alert = (
            e.get("done") is False and e["type"] == "rtk" and bool(e.get("role"))
        )

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
            project_path(referenced_version).parent == Path(bpy.data.filepath).parent
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

        for frame in (f_start, f_end) if e.get("frame_end") else (f_start,):
            frames_row.operator(
                "m_pipeline.current_frame",
                text=label.format(frame),
                emboss=not e.get("done", False),
            ).frame = frame
        frames_row.separator(factor=0.75)

    btn = btns_row.row(align=True)
    btn.alignment = "RIGHT"
    btns = btn.row(align=True)
    btns.scale_x = 0.85
    _entry_button(btns, e, filepath, safe_icon("GRIP_CORNER_BOTTOM_RIGHT", "GRIP"))


def _entry_button(layout, e: dict, filepath: str, icon: str) -> None:
    """An entry's icon: a click replies, its tooltip its whole text."""
    icon_button(
        layout,
        "m_pipeline.generic_entry_button",
        icon,
        id=e["id"],
        filepath=filepath,
        custom_tooltip=_get_entry_tooltip(e, filepath),
        rmb="entry",
    )


def _get_entry_by_id(entries, id):
    """The entry with this id, None if there's none."""
    for e in entries:
        if e.get("id") == id:
            return e
    return None


def _get_entry_tooltip(e, filepath):
    """An entry's hover text: who and when, the version it's about, edits,
    departments, review origin, id, the entry it replies to."""
    file = e.get("referenced_version")
    file = Path(file).stem if file else "unknown version"

    text = f"By: {e.get('author', 'unknown')}\nAt: {e['created_at'].replace('T', ' ')}\nBased on: {file}"
    if e.get("render"):
        text = f"{text} (render {e['render']})"
    if e.get("role"):
        text = f"{text}\nAs: {e['role']}"
    if e.get("edited_by"):
        text = f"{text}\n\nEdited by: {e['edited_by']}\nAt: {e['edited_at'].replace('T', ' ')}"
    departments = entry_departments(e)
    if departments:
        plural = "s" if len(departments) > 1 else ""
        text = f"{text}\nFor department{plural}: {', '.join(departments)}"
    if e.get("source") == REVIEW_SOURCE:
        text = f"{text}\nImported from a prod review"
    elif e.get("source") == TEAM_REVIEW_SOURCE:
        text = f"{text}\nImported from a team review"
    elif e.get("source") == APPROVAL_SOURCE:
        text = f"{text}\nWritten by a validation"
    review_id = f" (review_id : {e.get('review_id')})" if e.get("review_id") else ""
    text = f"{text}\nId : {e.get('id')}{review_id}"

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
        done_at = local_time(e.get("done_at")) or "//"
        text = f"{text}\n\nDone by : {e.get('done_by', '//')}\nAt : {done_at}"
    return text


def _cells(layout, widths: list) -> list:
    """Rows side by side, each its share of widths. Splits, not a row: a
    row sizes its items by their content, so a cell of icons and one of
    text would no longer line up with the header's."""
    cells = []
    for i in range(len(widths) - 1):
        layout = layout.split(factor=widths[i] / max(sum(widths[i:]), 1e-6))
        cells.append(layout.row())
    cells.append(layout.row())
    return cells


