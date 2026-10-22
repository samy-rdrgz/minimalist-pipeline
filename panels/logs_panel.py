"""Pipeline log window: the project's pipeline_log.jsonl, filterable."""

import datetime
import threading

import bpy

from ..lib import (
    ConfigCache,
    draw_pager,
    paginate,
    read_log_tail,
    redraw_monitoring,
    rows_that_fit,
    split_footer,
)

# Read on open and on refresh (load_pipeline_log()), on a thread -- never
# from draw().
_log_cache: dict = {
    "entries": [],
    "truncated": False,
    "read_at": None,
    "loading": False,
    # Built once per read: the enum callbacks run on every redraw.
    "values": {"action": [], "user": []},
}
# draw() runs on every mouse move: the filtered list is only rebuilt when
# the read or a filter changed, a page change is just a slice of it.
_filtered: dict = {"key": None, "matches": []}

LEVEL_ICONS = {
    "error": "CANCEL",
    "warning": "ERROR",
    "success": "CHECKMARK",
    "info": "INFO",
}

# Message length drawn in the list; the whole of it is in the tooltip.
_SHORT = 160

# Column widths of a log line: time, user, action, then the message.
_TIME, _USER, _ACTION = 0.16, 0.09, 0.13

# What the window holds besides its lines (filters, column titles, footer,
# margins), and one line's height, in widget units -- see rows_that_fit().
_LOG_RESERVED_UNITS = 7.4
_LINE_UNITS = 1.0


def _log_time(ts) -> str:
    """ "20/10/2026 15:20:11" -- day before month, always. The raw value if
    it isn't an ISO timestamp (a hand-edited line)."""
    try:
        return f"{datetime.datetime.fromisoformat(str(ts)):%d/%m/%Y %H:%M:%S}"
    except ValueError:
        return str(ts)


def load_pipeline_log() -> None:
    """Read the end of the project's pipeline log into the window's cache,
    on a thread (several MB on a share): the window shows the previous
    read, and "Reading..." until it's done."""
    if _log_cache["loading"]:
        return
    path = ConfigCache.get_path("pipeline_log_file")  # bpy: main thread only
    result = []
    thread = threading.Thread(
        target=lambda: result.append(read_log_tail(path)),
        daemon=True,
        name="pipeline-log-read",
    )
    _log_cache["loading"] = True
    thread.start()

    def poll():
        redraw_monitoring("log")
        if thread.is_alive():
            return 0.1
        entries, truncated = result[0] if result else ([], False)
        entries.reverse()  # newest first
        for entry in entries:
            message = str(entry.get("message", ""))
            entry["_search"] = message.lower()  # on every filter change
            # Drawn on every redraw: Blender re-clips a button's whole text
            # each time, and farm errors carry 1000+ chars of output.
            first = message.split("\n", 1)[0]
            entry["_short"] = first if len(first) <= _SHORT else first[:_SHORT] + "..."
            if first != message and len(first) <= _SHORT:
                entry["_short"] += " ..."
            entry["_time"] = _log_time(entry.get("ts") or "")
        _log_cache.update(
            entries=entries,
            truncated=truncated,
            read_at=datetime.datetime.now(),
            loading=False,
            values={
                key: sorted({str(e.get(key) or "") for e in entries} - {""})
                for key in ("action", "user")
            },
        )
        redraw_monitoring("log")
        return None

    bpy.app.timers.register(poll, first_interval=0.1)


def log_values(key: str) -> list[str]:
    """Every distinct "action" or "user" of the cached log, sorted."""
    return _log_cache["values"][key]


def log_read_at():
    """When the cached log was read -- None before the first read."""
    return _log_cache["read_at"]


def _matches(self, entry: dict, search: str) -> bool:
    """Whether a log entry passes the Pipeline log's filters: level, action,
    user, search."""
    level = entry.get("level", "")
    if self.level == "warning" and level not in ("warning", "error"):
        return False
    if self.level == "error" and level != "error":
        return False
    if self.action != "all" and entry.get("action") != self.action:
        return False
    if self.user != "all" and entry.get("user") != self.user:
        return False
    return not search or search in entry["_search"]


def draw_pipeline_logs(state, context, layout) -> None:
    """The Pipeline log window's list -- state is
    WindowManager.pipeline_log_monitoring (its filters), the page in
    memory like the other windows' (paginate())."""
    search = state.search.strip().lower()
    key = (_log_cache["read_at"], state.level, state.action, state.user, search)
    if _filtered["key"] != key:
        _filtered.update(
            key=key,
            matches=[e for e in _log_cache["entries"] if _matches(state, e, search)],
        )
    matches = _filtered["matches"]
    per_page = rows_that_fit(context, _LOG_RESERVED_UNITS, _LINE_UNITS)
    page_items, page, pages = paginate("log", matches, per_page, key[1:])

    box = layout.box()
    title = _line(box)
    for cell, text in zip(title, ("Time", "User", "Action", "Message")):
        cell.active = False
        cell.label(text=text)
    box.separator(factor=0.5, type="LINE")

    col = box.column(align=True)
    for entry in page_items:
        time, user, action, message = _line(col)
        level = entry.get("level", "")
        icon = LEVEL_ICONS.get(level, "BLANK1")
        time.label(text=entry["_time"], icon=icon)
        user.label(text=str(entry.get("user", "")))
        action.label(text=str(entry.get("action", "")))
        message.alert = level == "error"
        message.alignment = "LEFT"
        op = message.operator(
            "m_pipeline.copy_log_line", text=entry["_short"], emboss=False
        )
        op.text = _full_line(entry)
    for _ in range(per_page - len(page_items)):
        col.label(text="")

    left, right = split_footer(context, box)
    left.active = False
    left.operator(
        "m_pipeline.pipeline_logs_refresh", text="", icon="FILE_REFRESH", emboss=False
    )
    read_at = _log_cache["read_at"]
    shown = f"{len(matches)} line(s)"
    if _log_cache["loading"]:
        shown += " -- reading the log..."
    elif read_at:
        shown += f" -- read at {read_at:%H:%M:%S}"
    if _log_cache["truncated"]:
        shown += " -- latest entries only"
    left.label(text=shown)
    draw_pager(right, page, pages)


def _full_line(entry: dict) -> str:
    """The whole log entry as text, for the clipboard: time, level, user,
    action and message, then any extra field (filepath, duration...)."""
    main = ("ts", "level", "user", "action", "message")
    # Time as the list shows it: day before month.
    first = "  ".join([entry["_time"], *(str(entry.get(k, "")) for k in main[1:])])
    extra = [
        f"{k}: {v}"
        for k, v in entry.items()
        if k not in main and not k.startswith("_")  # _search, _short
    ]
    return "\n".join([first, *extra])


def _line(layout) -> tuple:
    """(time, user, action, message) cells of one log line."""
    time = layout.split(factor=_TIME)
    cells = [time.row()]
    rest = time.split(factor=_USER / (1 - _TIME))
    cells.append(rest.row())
    rest = rest.split(factor=_ACTION / (1 - _TIME - _USER))
    cells.append(rest.row())
    cells.append(rest.row())
    return tuple(cells)
