"""Tracking panel in the 3D View sidebar: current file's department status and notes/todos."""

import os
from pathlib import Path

from ..lib.status import project_stages

import bpy
import bpy.utils.previews

from ..farm import farm_activity
from ..lib import (
    APPROVAL_SOURCE,
    REVIEW_SOURCE,
    TEAM_REVIEW_SOURCE,
    ConfigCache,
    ProjectScan,
    TrackingStatusCache,
    WorkTimeCache,
    any_outdated_links,
    box_tip_units,
    covering_role,
    department_status_tooltip,
    draw_box_tip,
    draw_pager,
    entry_departments,
    farm_renders,
    filter_review_boxes,
    find_linked_by,
    format_work_time,
    get_active_project_root,
    get_current_departments,
    get_description,
    get_entries,
    get_entries_grouped,
    get_linked_libraries_cached,
    get_user,
    get_user_role,
    group_renders,
    highest_approval,
    json_get,
    list_is_narrow,
    local_time,
    monitoring_detail,
    open_rtks,
    open_task_counts,
    outdated_links,
    owner_key,
    owner_thumbnail_dirs,
    paginate,
    position_in_list,
    project_path,
    read_render_state,
    region_char_budget,
    render_root,
    render_to_check_label,
    assigned_to,
    rows_that_fit,
    safe_icon,
    shots_in_segment,
    shots_label,
    monitor_footer,
    list_rows,
    list_row,
    legend_button,
    text_to_lines,
    thumbnail_path,
    time_key,
    to_check_entries,
    validation_roles,
)
from ..lib.icons import icon_kw
from ..lib.status import OMIT_STATES, STATE_LABELS, department_state, omitted
from ..lib.ui import draw_legend, icon_button, link_rows
from .farm_panel import draw_frame_lookup_button, job_icon

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
    """The File panel's notes & tasks. Its departments: Project monitoring's
    file detail (the panel's Details button)."""
    if required:
        box.separator(factor=1)
    draw_entries(box, filepath, width=width)


def draw_entries(box, filepath, filters=None, width: int | None = None):
    """Draw a file's entries. filters: the object holding entries_hide_done
    / entries_department_filter / entries_min_version -- the WindowManager
    for the sidebar, File details' own operator (see NOTES.md, "Small
    gotchas, out of the docstrings")."""
    filters = filters or bpy.context.window_manager
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


def _draw_approval(
    row, data: dict, department: str, filepath: str, role: str, tooltip: str
):
    """A done department's validation, after its name: the highest role
    that validated it (a star), and, for a user with a validation role,
    the button giving or withdrawing theirs."""
    best = highest_approval(data, department)
    mine = role and role in (data.get("approvals") or {}).get(department, {})
    # The star alone as the button, the role a label after it: a button's
    # text is centred in its width, a label's starts at its left.
    if role:
        op = row.operator(
            "m_pipeline.toggle_department_approval",
            text="",
            icon="SOLO_ON" if mine else "SOLO_OFF",
            emboss=False,
        )
        op.department = department
        op.filepath = filepath
        action = "Withdraw" if mine else "Give"
        op.custom_tooltip = f"{action} your {role} validation.\n\n{tooltip}"
        if best:
            row.label(text=best)
    elif best:
        info = row.row(align=True)
        info.enabled = False
        info.operator(
            "m_pipeline.department_status_info", text="", icon="SOLO_ON", emboss=False
        ).custom_tooltip = tooltip
        info.label(text=best)


def _to_validate(file: dict, role: str) -> bool:
    """A done department of this file not validated yet: for this role
    (covered by an equal or higher one counts), else by any role."""
    roles = validation_roles()
    for d in file.get("validated_departments", {}):
        approvals = (file.get("approvals") or {}).get(d, {})
        if role and covering_role(approvals, role, roles) is None:
            return True
        if not role and not approvals:
            return True
    return False


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


# File details' thumbnail: loaded when a file is clicked (the details
# operator's execute()), never in draw() -- nothing on disk while drawing.
_previews = None
_preview_ids: dict[str, int] = {}
# Folder -> read_render_state(), filled on click (load_file_renders()).
_last_renders: dict[str, list] = {}
# Folder -> farm_renders(): the frame lookup's renders to pick from.
_farm_renders: dict[str, list] = {}


def load_file_thumbnail(folder: str) -> None:
    """Load (or reuse) folder's thumbnail into the preview collection, keyed
    on its mtime so a remade one shows up. No thumbnail: nothing drawn."""
    global _previews
    _preview_ids.pop(folder, None)
    root = get_active_project_root()
    if not root or not folder:
        return
    # The first shot's, else a block rendered whole's own.
    for d in owner_thumbnail_dirs(root, Path(folder)):
        path = thumbnail_path(d)
        try:
            mtime = os.stat(path).st_mtime
            break
        except OSError:
            continue
    else:
        return
    if _previews is None:
        _previews = bpy.utils.previews.new()
    key = f"{folder}|{mtime}"
    preview = _previews.get(key) or _previews.load(key, str(path), "IMAGE")
    _preview_ids[folder] = preview.icon_id


def load_file_renders(folder: str) -> None:
    """Read folder's last render per shot (read_render_state()) for its
    details -- on click, never in draw()."""
    _last_renders.pop(folder, None)
    _farm_renders.pop(folder, None)
    root = get_active_project_root()
    if not root or not folder:
        return
    owner = Path(folder)
    kind = "shot" if owner.parent.parent == Path(root) / "shots" else "asset"
    v_prefix = json_get(ConfigCache.get(), "naming.version.prefix", "v")
    stages = project_stages(ConfigCache.get(), f"{kind}s")
    renders = read_render_state(Path(root), kind, owner, v_prefix, stages)
    if any(r["path"] for r in renders):
        _last_renders[folder] = renders
        _farm_renders[folder] = farm_renders(owner)


def _draw_last_renders(layout, filepath: str) -> bool:
    """File details' column between departments and links: the last
    render of each shot, with its video and folder. False if never
    rendered."""
    last = _last_renders.get(filepath) or []
    if not last:
        return False
    col = layout.column(align=True)
    col.scale_y = 0.8  # same as the departments column
    title = col.row()
    title.label(text="Last render:", icon="RENDER_ANIMATION")
    block = len(last) > 1
    every = [r["shot"] for r in last]
    # Shots sharing a render on one line: "sh020-030-040 v004-stable_002".
    grouped = group_renders(last, key="path")
    for shots, r in grouped:
        label = shots_label(shots, every) if block else ""
        label = f"{label} " if label else ""
        if not r["path"]:
            _render_row(col, f"{label}not rendered").active = False
            continue
        dep = f"  ·  {r['department']}" if r.get("department") else ""
        _render_row(
            col,
            label + r["folder"] + dep,
            lambda row, r=r: _video_button(row, {"render": r["path"]}, label + r["folder"]),
            lambda row, r=r: _folder_button(row, r["path"]),
        )
        # The other departments' last renders, under the main one.
        for o in r.get("others") or []:
            text = f"   {o['folder']}  ·  {o['department'] or 'no department'}" + ("  (newer)" if o["newer"] else "")
            row = _render_row(
                col,
                text,
                lambda row, o=o: _video_button(row, {"render": o["path"]}, f"{label}{o['folder']}"),
                lambda row, o=o: _folder_button(row, o["path"]),
            )
            row.active = bool(o["newer"])
    # Which machine wrote frame n -- from render_history.json, there once the
    # job is archived and gone from Farm monitoring.
    renders = [
        (
            f"{shots_label(shots, every)} "
            if block and shots_label(shots, every)
            else "",
            r.get("frame_machines"),
            r.get("machine_seconds"),
        )
        for shots, r in grouped
    ]
    # Which render: every farm render of the file, the newest first -- a
    # block's last renders, every shot, before them.
    choices = [
        (label, [("", record, seconds)])
        for label, record, seconds in _farm_renders.get(filepath, [])
    ]
    if block:
        choices.insert(0, ("Last renders, every shot", renders))
    draw_frame_lookup_button(col, f"file:{filepath}", renders, choices or None)
    return True


def _draw_renders_to_check(layout, filepath: str, data: dict) -> None:
    """File details' "Renders to check" box, full width under the
    thumbnail row: each render with its date, video, folder and Checked."""
    to_check = _to_check_lines(data)
    if not to_check:
        return
    col = layout.box().column(align=False)  # its Checked buttons apart
    title = col.row()
    title.alert = True
    title.label(text="Renders to check:", icon="HIDE_OFF")
    draw_box_tip(col, bpy.context, _TO_CHECK_TIP)
    # Ctrl+click: every render to check at once, as the list's check mark.
    every = (
        "\nCtrl+click: mark all of them checked:\n"
        + "\n".join(
            f"{render_to_check_label(shot, info)}  ({_to_check_at(info)})"
            for shot, info in to_check
        )
        if len(to_check) > 1
        else ""
    )
    for shot, info in to_check:
        label = render_to_check_label(shot, info)

        def previous(row, info=info, label=label):
            op = row.operator(
                "m_pipeline.open_render_video", text="", icon="FRAME_PREV", emboss=False
            )
            op.render = info["render"]
            op.previous = True
            op.custom_tooltip = f"Play the render before {label}, to compare"

        # project_path(): plain join, no disk access in a draw().
        buttons = [lambda row, info=info, label=label: _video_button(row, info, label)]
        if info.get("render"):
            buttons += [previous, lambda row, info=info: _folder_button(row, str(project_path(info["render"])))]
        row = _render_row(col, f"{label}   {_to_check_at(info)}", *buttons, slots=3)
        row.separator(factor=1.5)
        op = row.operator("m_pipeline.render_checked", text="Checked", icon="CHECKMARK")
        op.filepath = filepath
        op.shot = shot
        op.custom_tooltip = "Mark this render as checked" + every


def _draw_farm_jobs(layout, filepath: str) -> None:
    """File details' "In the farm" box, under "Renders to check": each job
    of the file still in the farm (farm_activity()) with its step."""
    jobs = farm_activity().get(owner_key(filepath))
    if not jobs:
        return
    col = layout.box().column(align=True)
    col.label(text="In the farm:", icon="RENDER_ANIMATION")
    for job in jobs:
        label = " ".join(part for part in (job["shot"], job["version"]) if part)
        row = col.row(align=True)
        row.alignment = "LEFT"
        row.separator(factor=2)  # same indent as _render_row()
        row.alert = job["state"] == "failed"
        row.label(text=f"{label}   {job['text']}", **icon_kw(job_icon(job["stage"])))


def _render_row(col, text: str, *buttons, slots: int = 2):
    """A render's line: its buttons first (each a function of the row),
    blanks for the missing ones up to slots, then its words -- the words
    aligned whatever a department's name. Returns the row."""
    row = col.row(align=True)
    row.alignment = "LEFT"
    row.separator(factor=2)
    for draw in buttons:
        draw(row)
    for _ in range(slots - len(buttons)):
        row.label(text="", icon="BLANK1")
    row.label(text=text)
    return row


def _folder_button(row, path: str) -> None:
    op = row.operator("wm.open_folder", text="", icon="FILE_FOLDER", emboss=False)
    op.filepath = path
    op.custom_tooltip = "Open this render's folder"


def unregister_thumbnail_previews() -> None:
    """Free the thumbnails' preview collection and forget what it held."""
    global _previews
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
    _preview_ids.clear()
    _last_renders.clear()
    _farm_renders.clear()


def draw_file_details(state, context, layout):
    """Project monitoring's file detail (monitoring_detail("file")) -- state is
    WindowManager.pipeline_monitoring (its notes/tasks filters)."""

    box = layout
    row = box.row(align=True)

    row_left = row.box().row(align=True)
    row_left.alignment = "LEFT"
    row_left.operator(
        "m_pipeline.tracking_file_details", text="", icon="BACK", emboss=False
    )

    filepath = monitoring_detail("file")

    # The list's previous / next file (the Left / Right keys too), with its
    # filters and sort: m_pipeline.monitoring_page. Dimmed at an end; a file
    # outside the list (opened from a link) has no rank, no arrows. In
    # Back's own box -- a box of their own got an equal share of the row,
    # the name pushed to its middle --, the rank sized on its text as
    # draw_pager()'s label.
    rank, count = position_in_list("project", filepath)
    if count > 1 and rank:
        for step, icon in ((-1, "TRIA_LEFT"), (0, ""), (1, "TRIA_RIGHT")):
            cell = row_left.row(align=True)
            if step:
                cell.enabled = rank > 1 if step < 0 else rank < count
                icon_button(cell, "m_pipeline.monitoring_page", icon, step=step)
                continue
            text = f"{rank} / {count}"
            cell.active = False
            cell.ui_units_x = 0.35 * len(text) + 0.6
            cell.alignment = "CENTER"
            cell.label(text=text)

    data = TrackingStatusCache.get(filepath)
    description = get_description(Path(filepath))

    # monitoring_detail("file") is the tracked folder, not a versioned .blend --
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
    mark = omitted(data or {})
    if mark:
        # Set aside: said first, its reason with it.
        why = f": {mark['reason']}" if mark.get("reason") else ""
        txt = f"[{OMIT_STATES[mark['state']].upper()}{why}]  {txt}"
    row_left = row.box().row(align=True)
    row_left.alignment = "EXPAND"
    row_left.active = not mark
    row_left.label(text=txt, icon=icon)

    row_right = row.box().row(align=False)
    row_right.alignment = "RIGHT"
    root = get_active_project_root()
    try:
        is_block = is_shot and len(shots_in_segment(shot_name[len(shot_prefix) :])) > 1
    except ValueError:
        is_block = False
    for idname, icon, tooltip, props, shown in (
        (
            "m_pipeline.edit_description",
            "GREASEPENCIL",
            "",
            {"filepath": filepath},
            True,
        ),
        (
            "m_pipeline.file_omit",
            "PAUSE",
            "Set aside: On hold or Cancelled -- out of the figures and filters, kept in the lists"
            if not mark
            else f"{OMIT_STATES[mark['state']]} by {mark.get('by', '?')}: make it active again",
            {"filepath": filepath},
            True,
        ),
        (
            "m_pipeline.open_file_version",
            safe_icon("FILE_ALIAS", "FILE_BLEND"),
            "",
            {"filepath": str(filepath)},
            True,
        ),
        (
            "wm.open_folder",
            "FILE_FOLDER",
            "Open this file's folder",
            {"filepath": str(filepath)},
            True,
        ),
        # Pure path work, no resolve() in a draw(): renders/<seq>/<shot> for
        # a shot, renders/assets/... for an asset.
        (
            "wm.open_folder",
            "RENDER_STILL",
            "Open this file's render folder",
            {"filepath": str(render_root(root, Path(filepath))) if root else ""},
            bool(root),
        ),
        (
            "m_pipeline.compile_preview",
            "RENDER_ANIMATION",
            "Compile a disposable preview from just this block's own shots.",
            {"scope": "block", "filepath": filepath},
            is_block,
        ),
        (
            "m_pipeline.compile_preview",
            "SEQUENCE",
            "Compile a disposable preview from every rendered shot in this sequence.",
            {"scope": "sequence", "filepath": filepath},
            is_shot,
        ),
    ):
        if shown:
            icon_button(row_right, idname, icon, tooltip, **props)

    total_seconds = WorkTimeCache.get(filepath)
    if total_seconds:
        # Total only -- never a per-person/department breakdown, see
        # design.md "Work duration is logged, never surfaced per person".
        time_row = layout.row()
        time_row.active = False
        time_row.label(
            text=f"Total work time: {format_work_time(total_seconds)}", icon="TIME"
        )

    layout.separator(factor=1)
    tabl = layout.row(align=True)
    tabl.alignment = "LEFT"

    icon_id = _preview_ids.get(filepath)
    if icon_id:
        # A template_icon is always square, the frame centered in it: sized
        # on the departments list next to it (~one 0.8-scaled line per
        # department + its title), boxed so the centering reads as intended.
        lines = len(data.get("departments_required", [])) + 1
        tabl.box().template_icon(
            icon_value=icon_id, scale=max(4.0, min(8.0, lines * 0.8 + 0.6))
        )
        tabl.separator(factor=2)

    required = data.get("departments_required", [])
    if required:
        deps_row = tabl.column(align=True)
        deps_row.scale_y = 0.8
        validated = get_current_departments(Path(filepath))
        # Short: in this LEFT-aligned row, the column only gets its label's
        # estimated width -- "...for this file :" was cut ("...for this fil...").
        txt = deps_row.row(align=True)
        txt.separator(factor=0.5)
        txt.label(text="Departments required:", icon="TAG")
        role = get_user_role(context)
        for d in required:
            btn = deps_row.row(align=True)
            btn.label(text="", icon="BLANK1")
            btn.active = d in validated
            btn.alignment = "LEFT"
            tooltip = department_status_tooltip(data, d)
            op = btn.operator(
                "m_pipeline.toggle_validated_department",
                text=d.upper(),
                icon="CHECKMARK" if d in validated else "REMOVE",
                emboss=False,
            )
            op.department = d
            op.filepath = filepath
            op.custom_tooltip = tooltip
            if d in validated:
                _draw_approval(btn, data, d, filepath, role, tooltip)
            # Who it's assigned to (Edit project's Team): their names, a
            # click picks them.
            people = (data.get("assignees") or {}).get(d) or []
            assign = btn.row(align=True)
            assign.active = bool(people)
            icon_button(
                assign,
                "m_pipeline.assign_department",
                "COMMUNITY",
                f"Assigned to {', '.join(people)}: click to change" if people else "Assign it to someone of the team",
                text=", ".join(people),
                filepath=filepath,
                department=d,
            )
            if ((data.get("flags") or {}).get(d) or {}).get("to_redo"):
                icon_button(
                    btn,
                    "m_pipeline.department_still_done",
                    "mark:to_redo",
                    "To redo: "
                    + data["flags"][d]["to_redo"]
                    + ".\nStill done: the work done holds -- not a validation",
                    text="Still done",
                    filepath=filepath,
                    department=d,
                )
    else:
        deps_row = tabl.column()
        deps_row.scale_y = 0.5
        deps_row.label(text="No departments required for this file.")
        deps_row.label(
            text="(editable via /.pipeline/tracking.json > departments_required)"
        )

    tabl.separator(factor=4)

    if _draw_last_renders(tabl, filepath):
        tabl.separator(factor=4)

    linked = get_linked_libraries_cached(Path(filepath))
    linked_by = find_linked_by(get_active_project_root(), Path(filepath))
    if not ProjectScan.done and not linked_by:
        # The "Linked by" index is built by the background scan -- say so
        # rather than show "nothing links here" before it's known.
        pending = tabl.row()
        pending.active = False
        pending.label(text="Linked by: scanning project...", icon="SORTTIME")
    if linked or linked_by:
        links_col = tabl.column(align=True)
        links_col.scale_y = 0.7
        if linked:
            # One entry per linked file; grouped by folder -- more than one
            # means several versions of the same asset linked.
            by_folder: dict[Path, list[str]] = {}
            for entry in linked:
                if entry.get("file"):
                    by_folder.setdefault(project_path(entry["file"]).parent, []).append(
                        Path(entry["file"]).name
                    )
            # A link to an older version than its folder's latest stable.
            newer = dict(outdated_links(filepath))
            link_rows(
                links_col,
                "Links to:",
                [
                    (
                        "m_pipeline.tracking_file_details",
                        f"{lib_dir.name} ({len(names)})"
                        if len(names) > 1
                        else lib_dir.name,
                        "LIBRARY_DATA_BROKEN"
                        if any(n in newer for n in names)
                        else "BLANK1",
                        {
                            "filepath": str(lib_dir),
                            "custom_tooltip": "\n".join(
                                f"{n} -> {newer[n]} available" if n in newer else n
                                for n in names
                            ),
                            "alert": any(n in newer for n in names),
                        },
                    )
                    for lib_dir, names in by_folder.items()
                ],
            )
        if linked_by:
            link_rows(
                links_col,
                "Linked by:",
                [
                    (
                        "m_pipeline.tracking_file_details",
                        folder.name,
                        "BLANK1",
                        {"filepath": str(folder)},
                    )
                    for folder in linked_by
                ],
            )

    layout.separator(factor=1)
    _draw_renders_to_check(layout, filepath, data)
    _draw_farm_jobs(layout, filepath)
    layout.separator(factor=2)

    # Drawn in the monitoring window's own region: its real width.
    width = int(region_char_budget(context) * ENTRIES_INDENT_FACTOR)
    draw_entries(layout.column(align=True), filepath, filters=state, width=width)
    layout.separator(factor=2)


# A status cell's width (px at UI scale 1): with its words ("Done, reworked
# since"), with its marks alone (a retake's mark and the state's).
_CELL_TEXT_WIDTH = 150
_CELL_ICON_WIDTH = 48
# The names' column: its least, then what its icons and buttons take
# beside a name's letters. The Farm column: its least, then per icon.
_NAME_MIN_WIDTH = 110
_NAME_ICONS_WIDTH = 70
_FARM_MIN_WIDTH = 70
_FARM_ICON_WIDTH = 22
_TABLE_TIP = (
    "Click a file for its details (Ctrl+click the Project monitoring button: "
    "the file open here). Each department's state since the last stable, "
    "legend at the bottom. Farm: renders in the farm or waiting to be checked "
    "-- that filter, and RTK (open retakes), narrow the list. Right-click a "
    "file's name: its render folder, its folder, a render. The wheel or "
    "Left / Right turn pages, Tab switches assets / shots, Esc goes back."
)
_TO_CHECK_TIP = (
    "A farm render waits here until someone has watched it. Checked asks which "
    "departments are validated after watching it (untick one to unvalidate "
    "it), then archives its farm job. Ctrl+click: all of them at once."
)


def monitor_matches(self, context, project_root, activity=None) -> tuple:
    """(matches, filters) of Project monitoring's list: its (folder, file)
    pairs as filtered and sorted on screen, and the filters they were
    filtered for -- self is WindowManager.pipeline_monitoring. Read by
    draw_monitor_table() and by File details' previous / next file
    (operators/monitoring_ops.py, _step_file()). activity: farm_activity(),
    when the caller has it."""
    me = get_user(context)
    # Memory only: ProjectScan fills the cache in the background, the farm
    # column comes from the farm monitor's cache.
    data = TrackingStatusCache.known(Path(project_root))
    activity = farm_activity() if activity is None else activity
    types = {
        # Defaults: a config without library_prefixes (or asset_prefixes)
        # used to raise None + list here and break the whole popup.
        "asset": json_get(ConfigCache.get(), "structure.asset_prefixes", [])
        + json_get(ConfigCache.get(), "structure.library_prefixes", []),
        "shot": json_get(ConfigCache.get(), "naming.sequence.prefix"),
    }

    search = self.search.strip().lower()
    role = get_user_role(context)
    # Its button gone (nothing outdated any more): no filter left on.
    only_outdated = self.only_outdated and any_outdated_links(Path(project_root))
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
            if (
                self.only_farm
                and not file.get("to_check")
                and owner_key(dir) not in activity
            ):
                continue
            # A file set aside (On hold / Cancelled) is in no filter's list.
            if (self.only_rtk or self.only_to_validate) and omitted(file):
                continue
            if self.only_rtk and not _has_rtk(file):
                continue
            if self.only_mine and not assigned_to(file, me):
                continue
            if self.only_to_validate and not _to_validate(file, role):
                continue
            if only_outdated and not outdated_links(dir):
                continue
            if search and search not in (
                f"{file['file_name']} {file.get('description') or ''}".lower()
            ):
                continue
            matches.append((dir, file))

    # file_name is zero-padded prefix/sequence/shot numbers (see
    # naming.sequence/shot in config), so plain alphabetical sort already
    # gives prefix+alpha order for assets and sequence+shot order for
    # shots -- no separate sort key needed per file_type.
    matches.sort(key=lambda m: m[1].get("file_name") or "")
    # Stable sorts: ties stay in name order. No open RTK / never saved last.
    if self.sort == "rtk":
        matches.sort(key=lambda m: _date_last(_oldest_open_rtk(m[1])))
    elif self.sort == "work":
        matches.sort(key=lambda m: _date_last(m[1].get("last_saved_at")))

    filters = (
        self.file_type,
        self.asset_prefix,
        self.sequence,
        search,
        self.only_farm,
        self.only_rtk,
        self.only_to_validate,
        self.only_mine,
        only_outdated,
        self.sort,
    )
    return matches, filters


def draw_monitor_table(self, context, layout, columns, project_root):
    """Filtered file list, Project monitoring's main view -- self is
    WindowManager.pipeline_monitoring (file_type/asset_prefix/sequence/search
    filters, page). Paged by as many rows as the window fits, padded with
    blank rows: the footer stays at its bottom."""
    activity = farm_activity()
    matches, filters = monitor_matches(self, context, project_root, activity)
    # The columns shown (Filters > the columns menu).
    hidden = set(filter(None, self.hidden_columns.split(",")))
    columns = [c for c in columns if c not in hidden]
    show_farm = "farm" not in hidden
    narrow = list_is_narrow(context)
    scale = context.preferences.system.ui_scale or 1.0
    total = len(matches)
    per_page = list_rows(context, "project", box_tip_units(context, _TABLE_TIP))
    shown, page, pages = paginate(
        "project", matches, per_page, filters, key=lambda m: str(m[0])
    )
    # What fits, from the page's own names and Farm icons.
    # The marks alone, by choice too (Filters > the columns menu).
    FIRST_COLUMN, shares, icon_only = _column_widths(
        context.region.width / scale,
        shown,
        len(columns),
        show_farm,
        activity,
        words="·words" not in hidden,
    )

    draw_box_tip(layout, context, _TABLE_TIP)
    # A column, as Farm monitoring's list: the same rows, one height.
    f_list = layout.column()
    title_list = f_list.split(factor=FIRST_COLUMN) if FIRST_COLUMN < 1 else f_list.row()
    title_list.active = False
    title_list.label(text="File", icon="RADIOBUT_ON")
    if FIRST_COLUMN < 1:
        cells = _cells(title_list.row(), shares)
        for c_layout, c in zip(cells, columns):
            c_layout.label(text=c.capitalize())
        if show_farm:
            cells[-1].alignment = "RIGHT"
            cells[-1].label(text="Farm", icon="RENDER_ANIMATION")

    f_list.separator(factor=1)

    for dir, file in shown:
        _draw_monitor_row(
            self,
            f_list,
            dir,
            file,
            columns,
            FIRST_COLUMN,
            shares,
            activity.get(owner_key(dir)),
            icon_only=icon_only,
            show_farm=show_farm,
        )
    for _ in range(per_page - len(shown)):
        _draw_monitor_blank_row(f_list, shares, FIRST_COLUMN)
    # Dimmed, except the legend: its colours are the point (monitor_footer()).
    status, legend, _, pager = monitor_footer(context, f_list)
    # The table is what ProjectScan last found -- refresh on demand.
    if ProjectScan.done:
        status.operator(
            "m_pipeline.tracking_refresh", text="", icon="FILE_REFRESH", emboss=False
        )
    else:
        progress = (
            f"Scanning project... {ProjectScan.owners_found} folders found"
            if ProjectScan.phase == "walk"
            else f"Updating... {ProjectScan.statuses_done}/{ProjectScan.owners_found}"
            if ProjectScan.phase == "status"
            else "Updating links..."
        )
        status.label(text=progress, icon="SORTTIME")
    if total == 0:
        status.label(text="No files found with this filter", icon="ERROR")
    else:
        status.label(text=f"{total} file(s) found", icon="BLANK1")
    # The legend in the footer when it fits, else a button: it in a menu.
    groups = legend_groups(self.file_type, show_farm)
    if not narrow and context.region.width / scale >= _legend_width(groups):
        for _, group in groups:
            legend.separator(factor=2)
            for icon, text in group:
                legend.label(text=text, **icon_kw(icon))
    else:
        legend_button(legend, "M_PIPELINE_MT_monitor_legend")
    draw_pager(pager, page, pages)


def _column_widths(
    width: float,
    shown: list,
    departments: int,
    show_farm: bool,
    activity: dict,
    words: bool = True,
) -> tuple:
    """(the names' share of a row, each other column's width, marks alone)
    for a list width px wide (UI scale 1) showing shown: each department as
    wide as its content -- its words, else its marks alone (words False:
    always) --, the Farm column as its most icons, the names the rest (with
    words, up to 55 % of the row, the cells sharing what's beyond). Too narrow even
    so: the names alone, (1.0, [], False). See NOTES.md, "Monitoring: the
    detail beside the list"."""
    longest = max((len(f.get("file_name", "")) for _, f in shown), default=12)
    names_need = max(_NAME_MIN_WIDTH, _NAME_ICONS_WIDTH + 8 * longest)
    farm = 0
    if show_farm:
        icons = max(
            (
                len(_to_check_lines(f)) * 2 + len(activity.get(owner_key(d)) or [])
                for d, f in shown
            ),
            default=0,
        )
        farm = max(_FARM_MIN_WIDTH, 30 + _FARM_ICON_WIDTH * icons)
    if not departments:
        if not show_farm or width - farm < _NAME_MIN_WIDTH:
            return 1.0, [], False
        return (width - farm) / width, [farm], False
    tries = ((_CELL_TEXT_WIDTH, False, names_need),) if words else ()
    for cell, icon_only, least in tries + ((_CELL_ICON_WIDTH, True, _NAME_MIN_WIDTH),):
        names = width - farm - departments * cell
        if names >= least:
            break
    else:
        return 1.0, [], False
    # Wide, with their words: the names no wider than they'd ever need, the
    # cells the rest. Marks alone stay together, the names taking the room.
    most = max(names_need, 0.55 * width)
    if not icon_only and names > most:
        cell += (names - most) / departments
        names = most
    return names / width, [cell] * departments + [farm] * show_farm, icon_only


def legend_groups(file_type: str, show_farm: bool = True) -> list:
    """Project monitoring's legend, group by group: the states, the stages'
    marks once the project has stages (lib/status.py), the Farm column's:
    [(title, [(icon, text)])]."""
    kind = "shots" if file_type == "shot" else "assets"
    stages = ConfigCache.get().get("department_stages", {}).get(kind)
    return (
        [("Departments", _STATES_LEGEND)]
        + [("Stages", _STAGES_LEGEND)] * bool(stages)
        + [("Farm", _FARM_LEGEND)] * show_farm
    )


def _legend_width(groups: list) -> float:
    """The width (px at scale 1) the footer needs for the legend inline: its
    words and marks, plus the file count and the pager beside it."""
    return 420 + sum(40 + sum(26 + 7 * len(text) for _, text in g) for _, g in groups)


class M_PIPELINE_MT_monitor_legend(bpy.types.Menu):
    """Project monitoring's legend, when the footer has no room for it."""

    bl_idname = "M_PIPELINE_MT_monitor_legend"
    bl_label = "Legend"

    def draw(self, context):
        state = context.window_manager.pipeline_monitoring
        hidden = set(filter(None, state.hidden_columns.split(",")))
        draw_legend(self.layout, legend_groups(state.file_type, "farm" not in hidden))


def _draw_monitor_row(
    self,
    f_list,
    dir,
    file,
    columns,
    first_column,
    shares,
    jobs=None,
    icon_only=False,
    show_farm=True,
):
    """One file's row of Project monitoring: name (opens its detail), a
    status cell per department column, then its Farm cell."""
    row = list_row(f_list)
    mark = omitted(file)
    row.active = not mark  # set aside: greyed, still listed
    split = row.split(factor=first_column) if first_column < 1 else row
    name = split.row()
    name.alignment = "LEFT"
    # An RTK: its red mark, in that department's cell -- one on none, after
    # the name.
    rtk, general_rtk = open_rtks(file)
    icon = (
        TYPE_ICON.get(
            file.get("file_name", "Unknown").split("_", 1)[0],
            "ASSET_MANAGER",
        )
        if self.file_type == "asset"
        else TYPE_ICON.get("sh", "OUTLINER_OB_CAMERA")
    )
    # Right-click: its folders, a render.
    icon_button(
        name,
        "m_pipeline.tracking_file_details",
        icon,
        # Set aside: its mark here only with the names alone -- else it's
        # across the cells.
        text=file.get("file_name", "Unknown")
        + (f"  · {OMIT_STATES[mark['state']]}" if mark and first_column >= 1 else ""),
        filepath=str(dir),
        custom_tooltip=file.get("description", ""),
        rmb="file",
    )

    details = name.row()
    details.alignment = "RIGHT"
    if general_rtk:
        # A retake on no department: its own button, as a department's cell.
        icon_button(
            details,
            "m_pipeline.department_rtks",
            "mark:rtk",
            "A retake on no department",
            folder=str(dir),
            department="",
        )
    details = details.row()
    details.active = False
    icon_button(
        details,
        "m_pipeline.open_file_version",
        safe_icon("FILE_ALIAS", "FILE_BLEND"),
        filepath=str(dir),
    )
    if first_column >= 1:  # names only
        return
    if mark:
        # Set aside: its mark across the cells -- no "not started" left to
        # read in them.
        why = f": {mark['reason']}" if mark.get("reason") else ""
        split.row().label(text=f"{OMIT_STATES[mark['state']]}{why}", icon="PAUSE")
        return
    cells = _cells(split.row(), shares)
    roles = validation_roles()
    top = max((r["level"] for r in roles), default=None)
    top_roles = {r["name"] for r in roles if r["level"] == top}
    for icon_row, c in zip(cells, columns):
        if c in file.get("departments_required", []):
            # Read-only status: each button disabled below (no accidental
            # toggling from this grid -- that's file_details' job), the
            # tooltip still shown on hover. Never the row itself: a
            # disabled row disables whatever it holds.
            status = icon_row.row(align=True)

            tooltip = department_status_tooltip(file, c)
            text, row_icon, best = _department_cell(file, c)
            # Icon then text, each its own button in a left-aligned row:
            # one button's text is centred in its cell (both keep the tooltip).
            # Labels as the snapshot page's.
            status.alignment = "LEFT"
            # Grey, the star in full once validated by the top role
            # ("Done · prod"): what's through stands out.
            star = text.startswith("Done · ") and best in top_roles
            if star:
                row_icon = "mark:done_top"
            elif best:
                row_icon = "mark:valid"  # by a lower role
            # Too narrow for the words: the icon alone, its words first in
            # the tooltip.
            if icon_only:
                tooltip = f"{text}\n\n{tooltip}"
            # An open RTK: the mark with its red post-it under it (one icon,
            # tools/make_icons.py), a click shows the retakes.
            open_rtk = c in rtk and row_icon.startswith("mark:")
            for t, i in (
                (("", row_icon),) if icon_only else (("", row_icon), (text, "NONE"))
            ):
                button = status.row(align=True)
                button.alignment = "LEFT"  # its own width, not the cell's
                # The mark in its colours (the button does nothing), the
                # words greyed.
                button.enabled = t == ""
                if open_rtk and t == "":
                    icon_button(
                        button,
                        "m_pipeline.department_rtks",
                        f"{i}_rtk",
                        f"Retakes on {c}: click to read them\n\n{tooltip}",
                        folder=str(dir),
                        department=c,
                    )
                    continue
                icon_button(
                    button, "m_pipeline.department_status_info", i, tooltip, text=t
                )
        else:
            # Not required: a grey dash where the marks are (a label's
            # "–" sat apart from them).
            status = icon_row.row(align=True)
            status.alignment = "LEFT"
            status.enabled = False
            icon_button(
                status,
                "m_pipeline.department_status_info",
                "mark:none",
                "Not required for this file",
            )
    if show_farm:
        _draw_farm_cell(cells[-1], dir, file, jobs or [])


def _department_cell(file: dict, department: str) -> tuple[str, str, str | None]:
    """(text, icon, its highest validation) of a department's cell in
    Project monitoring: done (validated at the latest stable, not worked
    since -- "Done · prod" once validated by a role), done and reworked
    since, in progress (worked since, or validated / worked before the
    latest stable), not started. Labels as the snapshot page's."""
    state = department_state(file, department)
    flag = (file.get("flags") or {}).get(department) or {}
    if flag.get("waiting"):
        # Its own state stays in the tooltip (department_status_tooltip()).
        return f"Waiting: {flag['waiting']}", "mark:waiting", None
    if flag.get("to_redo"):
        return f"To redo: {flag['to_redo']}", "mark:to_redo", None
    if state == "done":
        best = highest_approval(file, department)
        return (
            (f"Done · {best}", "mark:done", best)
            if best
            else ("Done", "mark:done", None)
        )
    return STATE_LABELS[state], f"mark:{state}", None


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


def _to_check_lines(file: dict) -> list[tuple[str, dict]]:
    """(key, info) of every render waiting for a check, by shot and
    department (to_check_entries())."""
    return to_check_entries(file) if isinstance(file.get("to_check"), dict) else []


def _to_check_at(info: dict) -> str:
    """ "2026-10-14 18:04" -- when the render was flagged."""
    return local_time(info.get("at"))


# Farm column: one icon per render, Farm monitoring's for its stage
# (job_icon()); a render to check is a finished job's.
_TO_CHECK_ICON = job_icon("finished")
_STATES_LEGEND = (
    ("mark:todo", "Not started"),
    ("mark:wip", "In progress"),
    ("mark:rework", "Reworked since"),
    ("mark:done", "Done"),
    ("mark:valid", "Validated"),
    ("mark:done_top", "Validated, top role"),
    ("mark:done_rtk", "Open retake (click)"),
)
_STAGES_LEGEND = (("mark:waiting", "Waiting"), ("mark:to_redo", "To redo"))
_FARM_LEGEND = (
    (_TO_CHECK_ICON, "To check"),
    (job_icon("pending"), "Submitted"),
    (job_icon("queued"), "Queued"),
    (job_icon("setup_finished"), "Waiting"),
    (job_icon("render_start"), "In progress"),
    (job_icon("render_failed"), "Failed"),
)


def _draw_farm_cell(cell, dir, file, jobs: list) -> None:
    """Project monitoring's "Farm" column: an icon per render, shot by
    shot (a block's sub-shots side by side) -- a render to check (a button:
    plays it), or a job still in the farm (farm_activity()) with the Farm
    popup's icon for its stage.
    Details in the tooltips. Then one checkbox marks every render to check
    checked (one by one in the file's details)."""
    # Against the row's right edge.
    cell.alignment = "RIGHT"
    renders = _to_check_lines(file)
    if not renders and not jobs:
        cell.label(text=" ", icon="BLANK1")
        return
    icons = cell.row(align=True)
    icons.alignment = "RIGHT"
    icons.scale_x = 0.9  # icons close together
    # An older render to check comes before the shot's new job.
    items = [(shot, 0, info) for shot, info in renders]
    items += [(job["shot"], 1, job) for job in jobs]
    # Consecutive to-check buttons share one aligned sub-row (rounded corners
    # at its ends), set apart from the flat icons around them.
    group, group_is_job = None, None
    for shot, is_job, item in sorted(items, key=lambda i: (i[0], i[1])):
        if is_job != group_is_job:
            if group is not None:
                icons.separator(factor=0.3)
            group, group_is_job = icons.row(align=True), is_job
        if not is_job:
            label = render_to_check_label(shot, item)
            # Embossed: the only clickable ones (play the video).
            op = group.operator(
                "m_pipeline.open_render_video", text="", **icon_kw(_TO_CHECK_ICON)
            )
            op.render = item.get("render") or ""
            op.video = item.get("video") or ""
            op.custom_tooltip = (
                f"To check: {label}  ({_to_check_at(item)})\nClick to play it."
            )
            continue
        group.operator(
            "m_pipeline.department_status_info",
            text="",
            **icon_kw(job_icon(item["stage"])),
            emboss=False,
        ).custom_tooltip = " ".join(
            part for part in (shot, item["version"], "--", item["text"]) if part
        )
    if renders:
        icons.separator(factor=1.5)
        op = icons.operator("m_pipeline.render_checked", text="", icon="CHECKMARK")
        op.filepath = str(dir)
        op.all_shots = True
        op.custom_tooltip = "Mark checked:\n" + "\n".join(
            f"{render_to_check_label(shot, info)}  ({_to_check_at(info)})"
            for shot, info in renders
        )
    sep = icons.row()
    sep.scale_x = 0.5
    sep.label(text="", icon="BLANK1")


def _video_button(layout, info: dict, label: str) -> None:
    """Play a render's video (m_pipeline.open_render_video)."""
    op = layout.operator(
        "m_pipeline.open_render_video", text="", icon="FILE_MOVIE", emboss=False
    )
    op.render = info.get("render") or ""
    op.video = info.get("video") or ""
    at = _to_check_at(info)
    op.custom_tooltip = f"Play {label}" + (f"  ({at})" if at else "")


def _draw_monitor_blank_row(f_list, shares, first_column):
    """Empty row, same height as a file's -- a page's padding."""
    row = list_row(f_list)
    row.active = False
    if first_column >= 1:  # names only
        row.label(text="")
    else:
        split = row.split(factor=first_column)
        split.row().label(text="")
        for cell in _cells(split.row(), shares):
            cell.label(text="", icon="BLANK1")


def _oldest_open_rtk(data: dict) -> str:
    """created_at (ISO) of data's oldest un-done RTK, "" without one."""
    return min(
        (
            e.get("created_at") or ""
            for e in data.get("entries") or []
            if e.get("type") == "rtk" and e.get("done") is False
        ),
        key=time_key,
        default="",
    )


def _date_last(value) -> tuple:
    """Sort key: oldest date first, none last."""
    return (not value, time_key(value))


def _has_rtk(data: dict, department: str | None = None) -> bool:
    """Whether data has an un-done RTK entry tagged with department --
    among its departments, an entry may have several -- (any department
    when None). Never a todo: un-done too, not an RTK."""
    return any(
        e.get("type") == "rtk"
        and e.get("done") is False
        and (department is None or department in entry_departments(e))
        for e in data.get("entries") or []
    )
