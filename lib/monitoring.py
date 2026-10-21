"""The monitoring windows -- Project monitoring and Farm monitoring: each a
Properties editor on its Tool tab, where panels/monitoring_panel.py draws.
See NOTES.md, "Monitoring: windows, not popups"."""

import time

import bpy

from .config import get_active_project_root
from .tracking import ProjectScan

# ID property marking a window's screen with what it shows ("project" or
# "farm") -- the panels' poll() reads it, and it survives the .blend being
# saved with the window open.
MONITORING_SCREEN_KEY = "m_pipeline_monitoring"
MONITORING_KINDS = ("project", "farm")

# Redraw check, and how often Project monitoring's Farm column is read again.
_TICK = 0.5
_FARM_READ_EVERY = 10.0

# Which windows are monitoring windows, by pointer: a window opened by
# window_new() is the main window's child, and follows it to every workspace
# it switches to -- on a new screen each time, without the mark. Re-marked
# from here (monitoring_windows()).
_window_kinds: dict = {}

_last_seen: dict = {}
_last_farm_read = 0.0
# Whether _monitoring_tick started the farm's refresh timer (for a Farm
# monitoring window), so it only stops its own.
_farm_refresh_ours = False


def monitoring_kind(screen) -> str:
    """What a screen's monitoring window shows, "" for any other screen."""
    value = screen.get(MONITORING_SCREEN_KEY) if screen else None
    if value is True or value == 1:
        return "project"  # marked before Farm monitoring had a window
    return value if value in MONITORING_KINDS else ""


def monitoring_windows(kind: str | None = None) -> list:
    """The open monitoring windows (of that kind). Looked up every time,
    never kept: a window, its areas and regions are freed when it closes or
    a file loads (see NOTES.md, "Project walk")."""
    wm = bpy.context.window_manager
    if wm is None:
        return []
    live = {w.as_pointer(): w for w in wm.windows}
    for ptr in [p for p in _window_kinds if p not in live]:
        del _window_kinds[ptr]  # closed, or a file load
    for ptr, window_kind in _window_kinds.items():
        window = live[ptr]
        if monitoring_kind(window.screen) != window_kind:
            window.screen[MONITORING_SCREEN_KEY] = window_kind
            for area in window.screen.areas:
                area.tag_redraw()
    return [
        w
        for w in wm.windows
        if monitoring_kind(w.screen) and kind in (None, monitoring_kind(w.screen))
    ]


def open_monitoring_window(context, kind: str) -> bool:
    """A new window holding one Properties editor, on the Tool tab once it
    has been drawn. False if Blender didn't open it."""
    wm = context.window_manager
    before = {w.as_pointer() for w in wm.windows}
    bpy.ops.wm.window_new()
    new = [w for w in wm.windows if w.as_pointer() not in before]
    if not new:
        return False
    window = new[0]
    screen = window.screen
    # One area (the main window's biggest editor) -- the biggest, should
    # a Blender version open more.
    area = max(screen.areas, key=lambda a: a.width * a.height)
    area.type = "PROPERTIES"
    # No search field: it would filter the table's labels.
    area.spaces.active.show_region_header = False
    screen[MONITORING_SCREEN_KEY] = kind
    _window_kinds[window.as_pointer()] = kind
    try:
        # The tab column: nothing to switch to here.
        with context.temp_override(window=window, area=area):
            bpy.ops.screen.region_toggle(region_type="NAVIGATION_BAR")
    except (RuntimeError, TypeError, AttributeError):
        pass
    # The editor's tabs are only known once it has been drawn: "TOOL" isn't
    # a valid value yet.
    bpy.app.timers.register(_show_tool_tab(window.as_pointer()), first_interval=0.0)
    ensure_monitoring_tick()
    return True


def _show_tool_tab(window_ptr: int, tries: int = 20):
    """That window's Properties editor on its Tool tab -- that window only,
    and in its context: a timer has none, and setting a space's property
    without one can crash Blender."""

    def tick():
        nonlocal tries
        tries -= 1
        wm = bpy.context.window_manager
        window = next((w for w in wm.windows if w.as_pointer() == window_ptr), None)
        if window is None:
            return None
        pending = False
        for area in window.screen.areas:
            space = area.spaces.active
            if area.type != "PROPERTIES" or space.context == "TOOL":
                continue
            with bpy.context.temp_override(window=window, screen=window.screen, area=area):
                try:
                    space.context = "TOOL"
                except TypeError:
                    pending = True
        return 0.05 if pending and tries > 0 else None

    return tick


def redraw_monitoring(kind: str | None = None) -> None:
    for window in monitoring_windows(kind):
        for area in window.screen.areas:
            if area.type != "PROPERTIES":
                continue
            for region in area.regions:
                if region.type == "WINDOW":
                    region.tag_redraw()


def ensure_monitoring_tick() -> None:
    """Start _monitoring_tick() if it isn't running -- the windows' panels
    call it too: a window can come back with a .blend saved with it open."""
    if not bpy.app.timers.is_registered(_monitoring_tick):
        bpy.app.timers.register(_monitoring_tick, first_interval=0.0, persistent=True)


def stop_monitoring_tick() -> None:
    if bpy.app.timers.is_registered(_monitoring_tick):
        bpy.app.timers.unregister(_monitoring_tick)


def _monitoring_tick():
    """While a monitoring window is open, redraw it when what it shows
    changed -- a popup redrew on every mouse move, a window only when told
    to. Project monitoring: scan the active project if it hasn't been (a
    switch of project, a window reopened with its .blend), read the farm
    again every _FARM_READ_EVERY. Farm monitoring: keep the farm's own
    refresh timer running (a file load stops it). Stops itself once no
    window is left."""
    global _last_farm_read, _farm_refresh_ours
    from ..farm import (
        farm_activity,
        get_monitor_cache,
        register_refresh_timer,
        request_monitor_refresh,
        unregister_refresh_timer,
    )

    project = monitoring_windows("project")
    farm = monitoring_windows("farm")

    if farm:
        register_refresh_timer()  # no-op while it runs
        _farm_refresh_ours = True
    elif _farm_refresh_ours:
        unregister_refresh_timer()
        _farm_refresh_ours = False

    if not (project or farm):
        _last_seen.clear()
        return None

    root = get_active_project_root()
    if project:
        if root and not ProjectScan.covers(root):
            ProjectScan.start(root)
        if time.monotonic() - _last_farm_read >= _FARM_READ_EVERY:
            _last_farm_read = time.monotonic()
            request_monitor_refresh()
        seen = (
            str(root),
            ProjectScan.done,
            ProjectScan.phase,
            ProjectScan.owners_found,
            ProjectScan.statuses_done,
            farm_activity(),
        )
        if seen != _last_seen.get("project"):
            _last_seen["project"] = seen
            redraw_monitoring("project")
    if farm:
        cache = get_monitor_cache()
        # A farm read replaces the cache's lists: their identity is enough.
        seen = (str(root), cache.get("status"), id(cache.get("jobs")), id(cache.get("workers")))
        if seen != _last_seen.get("farm"):
            _last_seen["farm"] = seen
            redraw_monitoring("farm")
    return _TICK


def memory_prop(store: dict, key: str, prop, default, **kwargs):
    """A property drawable with layout.prop() whose value lives in `store`
    (memory) -- a monitoring window's filters: a WindowManager property is
    saved into every .blend and comes back as each opened file had it."""

    def get(self):
        return store.get(key, default)

    def set(self, value):
        store[key] = value

    return prop(default=default, get=get, set=set, **kwargs)


def memory_enum(store: dict, key: str, items, **kwargs):
    """memory_prop() for an enum. Its get/set deal in item indices: kept by
    identifier, so a dynamic list (prefixes, sequences) changing keeps the
    choice."""

    def item_list(self):
        return items(self, bpy.context) if callable(items) else items

    def get(self):
        ids = [item[0] for item in item_list(self)]
        value = store.get(key)
        return ids.index(value) if value in ids else 0

    def set(self, index):
        found = item_list(self)
        if 0 <= index < len(found):
            store[key] = found[index][0]

    return bpy.props.EnumProperty(items=items, get=get, set=set, **kwargs)


def open_mainfile(filepath: str) -> None:
    """bpy.ops.wm.open_mainfile(), keeping the interface as it is while a
    monitoring window is open: loading the file's own closes every window
    the file doesn't have, that one included."""
    if monitoring_windows():
        bpy.ops.wm.open_mainfile(filepath=filepath, load_ui=False)
    else:
        bpy.ops.wm.open_mainfile(filepath=filepath)
