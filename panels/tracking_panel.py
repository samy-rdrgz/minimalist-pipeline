"""Tracking panel in the 3D View sidebar: current file's department status and notes/todos."""

import os
from pathlib import Path

import bpy
import bpy.utils.previews

from ..farm import farm_activity
from .farm_panel import job_icon
from ..lib import (
    ConfigCache,
    REVIEW_SOURCE,
    ProjectScan,
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
    get_linked_libraries_cached,
    owner_render_dir,
    render_root,
    json_get,
    project_path,
    read_render_state,
    region_char_budget,
    owner_key,
    render_to_check_label,
    responsive_layout,
    safe_icon,
    shots_in_segment,
    text_to_lines,
    thumbnail_path,
)

# Monitoring popups' width: this share of the Blender window, never under
# MONITOR_POPUP_MIN_WIDTH (unless the window itself is smaller).
MONITOR_POPUP_SHARE = 0.8
MONITOR_POPUP_MIN_WIDTH = 900


def popup_width(context) -> int:
    """Width for a monitoring popup's invoke_props_dialog(), from the
    window it opens in. A dialog's width is unscaled px (Blender applies
    the UI scale to it), the window's is real px."""
    scale = context.preferences.system.ui_scale or 1.0
    window = context.window.width / scale
    return int(min(window, max(MONITOR_POPUP_MIN_WIDTH, window * MONITOR_POPUP_SHARE)))

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
        icon=safe_icon("GRIP_CORNER_BOTTOM_RIGHT", "GRIP"),
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
    if e.get("source") == REVIEW_SOURCE:
        text = f"{text}\nImported from a prod review"
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
        done_at = e.get("done_at")
        done_at = done_at.replace("T", " ") if done_at else "//"
        text = f"{text}\n\nDone by : {e.get('done_by', '//')}\nAt : {done_at}"
    return text


# File details' thumbnail: loaded when a file is clicked (the details
# operator's execute()), never in draw() -- nothing on disk while drawing.
_previews = None
_preview_ids: dict[str, int] = {}
# Folder -> read_render_state(), filled on click (load_file_renders()).
_last_renders: dict[str, list] = {}


def load_file_thumbnail(folder: str) -> None:
    """Load (or reuse) folder's thumbnail into the preview collection, keyed
    on its mtime so a remade one shows up. No thumbnail: nothing drawn."""
    global _previews
    _preview_ids.pop(folder, None)
    root = get_active_project_root()
    if not root or not folder:
        return
    path = thumbnail_path(owner_render_dir(root, Path(folder)))
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
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
    root = get_active_project_root()
    if not root or not folder:
        return
    owner = Path(folder)
    kind = "shot" if owner.parent.parent == Path(root) / "shots" else "asset"
    v_prefix = json_get(ConfigCache.get(), "naming.version.prefix", "v")
    renders = read_render_state(Path(root), kind, owner, v_prefix)
    if any(r["path"] for r in renders):
        _last_renders[folder] = renders


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
    for r in last:
        label = f"{r['shot']} " if block else ""
        if not r["path"]:
            _render_row(col, f"{label}not rendered").active = False
            continue
        row = _render_row(col, label + r["folder"])
        _video_button(row, {"render": r["path"]}, label + r["folder"])
        _folder_button(row, r["path"])
    return True


def _draw_renders_to_check(layout, filepath: str, data: dict) -> None:
    """File details' "Renders to check" box, full width under the
    thumbnail row: each render with its date, video, folder and Checked."""
    to_check = _to_check_lines(data)
    if not to_check:
        return
    col = layout.box().column(align=True)
    title = col.row()
    title.alert = True
    title.label(text="Renders to check:", icon="HIDE_OFF")
    for shot, info in to_check:
        label = render_to_check_label(shot, info)
        row = _render_row(col, f"{label}   {_to_check_at(info)}")
        _video_button(row, info, label)
        if info.get("render"):
            # project_path(): plain join, no disk access in a draw().
            _folder_button(row, str(project_path(info["render"])))
        row.separator(factor=1.5)
        op = row.operator(
            "m_pipeline.render_checked", text="Checked", icon="CHECKMARK"
        )
        op.filepath = filepath
        op.shot = shot
        op.custom_tooltip = "Mark this render as checked"


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
        row.label(text=f"{label}   {job['text']}", icon=job_icon(job["stage"]))


def _render_row(col, text: str):
    row = col.row(align=True)
    row.alignment = "LEFT"
    row.separator(factor=2)
    row.label(text=text)
    return row


def _folder_button(row, path: str) -> None:
    op = row.operator("wm.open_folder", text="", icon="FILE_FOLDER", emboss=False)
    op.filepath = path
    op.custom_tooltip = "Open this render's folder"


def unregister_thumbnail_previews() -> None:
    global _previews
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
    _preview_ids.clear()
    _last_renders.clear()


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
        icon=safe_icon("FILE_ALIAS", "FILE_BLEND"),
        emboss=False,
    ).filepath = str(filepath)

    op = row_right.operator("wm.open_folder", text="", icon="FILE_FOLDER", emboss=False)
    op.filepath = str(filepath)
    op.custom_tooltip = "Open this file's folder"

    root = get_active_project_root()
    if root:
        op = row_right.operator(
            "wm.open_folder", text="", icon="RENDER_STILL", emboss=False
        )
        # Pure path work, no resolve() in a draw(): renders/<seq>/<shot> for
        # a shot, renders/assets/... for an asset.
        op.filepath = str(render_root(root, Path(filepath)))
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
                by_folder.setdefault(project_path(entry["file"]).parent, []).append(
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

    layout.separator(factor=1)
    _draw_renders_to_check(layout, filepath, data)
    _draw_farm_jobs(layout, filepath)
    layout.separator(factor=2)

    # Drawn in M_PIPELINE_OT_tracking_monitor's dialog, whose region isn't
    # context.region: pass the dialog's real width -- see
    # region_char_budget() / POPUP_WIDTH_SCALE in lib/core.py.
    budget = region_char_budget(context, width_px=self.popup_width)
    width = int(budget * ENTRIES_INDENT_FACTOR)
    draw_entries(layout.column(align=True), filepath, filters=self, width=width)
    layout.separator(factor=2)


def draw_monitor_table(self, context, layout, columns):
    """Filtered, paginated file list for M_PIPELINE_OT_tracking_monitor's main
    view -- self is that operator instance (file_type/asset_prefix/sequence/
    search/page state lives on it, same convention as draw_file_details() above)."""
    # Memory only: ProjectScan fills the cache in the background, the farm
    # column comes from the farm monitor's cache.
    data = TrackingStatusCache.known(Path(self.project_root))
    activity = farm_activity()
    FIRST_COLUMN = 0.3
    types = {
        # Defaults: a config without library_prefixes (or asset_prefixes)
        # used to raise None + list here and break the whole popup.
        "asset": json_get(ConfigCache.get(), "structure.asset_prefixes", [])
        + json_get(ConfigCache.get(), "structure.library_prefixes", []),
        "shot": json_get(ConfigCache.get(), "naming.sequence.prefix"),
    }

    search = self.search.strip().lower()
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
            if self.only_rtk and not _has_rtk(file):
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
    cells = _equal_cells(title_list.row(), len(columns) + 1)
    for cell, c in zip(cells, columns):
        cell.label(text=c.capitalize(), icon="KEYFRAME_HLT")
    cells[-1].label(text="Farm", icon="RENDER_ANIMATION")

    f_list.separator(factor=1)

    for dir, file in page_items:
        _draw_monitor_row(
            self, f_list, dir, file, columns, FIRST_COLUMN, activity.get(owner_key(dir))
        )

    for _ in range(self.PAGE_SIZE - len(page_items)):
        _draw_monitor_blank_row(f_list, columns, FIRST_COLUMN)

    footer = f_list.row()
    # Dimmed, except the legend: its colours are the point.
    status = footer.row()
    status.alignment = "LEFT"
    status.active = False
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
    legend = footer.row(align=True)
    legend.alignment = "LEFT"
    legend.separator(factor=3)
    for icon, text in _FARM_LEGEND:
        legend.label(text=text, icon=icon)
    if total_pages > 1:
        pager = footer.row(align=True)
        pager.alignment = "RIGHT"
        pager.active = False
        pager.label(text=f"Page {self.page} / {total_pages}")
        pager.prop(self, "page", text="")


def _draw_monitor_row(self, f_list, dir, file, columns, first_column, jobs=None):
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
        icon=safe_icon("FILE_ALIAS", "FILE_BLEND"),
        emboss=False,
    ).filepath = str(dir)
    cells = _equal_cells(split.row(), len(columns) + 1)
    for icon_row, c in zip(cells, columns):
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
    _draw_farm_cell(cells[-1], dir, file, jobs or [])
    f_list.separator(factor=0.5, type="LINE")


def _equal_cells(layout, count: int) -> list:
    """count equal-width rows side by side. Splits, not a row: a row sizes
    its items by their content, so a cell of icons and one of text would
    no longer line up with the header's."""
    cells = []
    for i in range(count - 1):
        layout = layout.split(factor=1 / (count - i))
        cells.append(layout.row())
    cells.append(layout.row())
    return cells


def _to_check_lines(file: dict) -> list[tuple[str, dict]]:
    """(shot, info) of every render waiting for a check, by shot."""
    to_check = file.get("to_check")
    return sorted(to_check.items()) if isinstance(to_check, dict) else []


def _to_check_at(info: dict) -> str:
    """ "2026-10-14 18:04" -- when the render was flagged."""
    return (info.get("at") or "")[:16].replace("T", " ")


# Farm column: one icon per render, the Farm popup's for its stage
# (job_icon()); a render to check is a finished job's.
_TO_CHECK_ICON = job_icon("finished")
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
    cell.label(text="", icon="BLANK1")
    renders = _to_check_lines(file)
    if not renders and not jobs:
        cell.label(text=" ", icon="BLANK1")
        return
    icons = cell.row(align=True)
    icons.alignment = "LEFT"
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
                "m_pipeline.open_render_video", text="", icon=_TO_CHECK_ICON
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
            icon=job_icon(item["stage"]),
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


def _video_button(layout, info: dict, label: str) -> None:
    """Play a render's video (m_pipeline.open_render_video)."""
    op = layout.operator(
        "m_pipeline.open_render_video", text="", icon="FILE_MOVIE", emboss=False
    )
    op.render = info.get("render") or ""
    op.video = info.get("video") or ""
    at = _to_check_at(info)
    op.custom_tooltip = f"Play {label}" + (f"  ({at})" if at else "")


def _draw_monitor_blank_row(f_list, columns, first_column):
    """Empty placeholder row, same height as a real one, so a half-filled
    last page doesn't shrink the popup."""
    row = f_list.column()
    row.active = False
    split = row.split(factor=first_column)
    split.row().label(text="")
    for cell in _equal_cells(split.row(), len(columns) + 1):  # + "Farm"
        cell.label(text="", icon="BLANK1")
    f_list.separator(factor=0.5, type="LINE")


def _has_rtk(data: dict, department: str | None = None) -> bool:
    """Whether data has an un-done RTK entry tagged with department (any
    department when None). Never a todo: un-done too, not an RTK."""
    return any(
        e.get("type") == "rtk"
        and e.get("done") is False
        and (department is None or e.get("department") == department)
        for e in data.get("entries") or []
    )
