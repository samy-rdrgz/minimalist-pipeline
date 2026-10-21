"""Project monitoring's own window: a Properties editor on its Tool tab, where
panels/monitoring_panel.py draws. See NOTES.md, "Project monitoring: a
window, not a popup"."""

import time

import bpy

from .config import get_active_project_root
from .tracking import ProjectScan

# ID property marking the window's screen -- the panel's poll() looks for it,
# and it survives the .blend being saved with the window open.
MONITORING_SCREEN_KEY = "m_pipeline_monitoring"

# Redraw check, and how often the Farm column is read again.
_TICK = 0.5
_FARM_READ_EVERY = 10.0

_last_seen = None
_last_farm_read = 0.0


def is_monitoring_screen(screen) -> bool:
    return bool(screen and screen.get(MONITORING_SCREEN_KEY))


def monitoring_windows() -> list:
    """The open Project monitoring windows. Looked up every time, never kept:
    a window, its areas and regions are freed when it closes or a file loads
    (see NOTES.md, "Project walk")."""
    wm = bpy.context.window_manager
    if wm is None:
        return []
    return [w for w in wm.windows if is_monitoring_screen(w.screen)]


def open_monitoring_window(context) -> bool:
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
    screen[MONITORING_SCREEN_KEY] = True
    try:
        # The tab column: nothing to switch to here.
        with context.temp_override(window=window, area=area):
            bpy.ops.screen.region_toggle(region_type="NAVIGATION_BAR")
    except (RuntimeError, TypeError, AttributeError):
        pass
    # The editor's tabs are only known once it has been drawn: "TOOL" isn't
    # a valid value yet.
    bpy.app.timers.register(_show_tool_tab(), first_interval=0.0)
    ensure_monitoring_tick()
    return True


def _show_tool_tab(tries: int = 20):
    def tick():
        nonlocal tries
        tries -= 1
        pending = False
        for window in monitoring_windows():
            for area in window.screen.areas:
                space = area.spaces.active
                if area.type != "PROPERTIES" or space.context == "TOOL":
                    continue
                try:
                    space.context = "TOOL"
                except TypeError:
                    pending = True
        return 0.05 if pending and tries > 0 else None

    return tick


def redraw_monitoring() -> None:
    for window in monitoring_windows():
        for area in window.screen.areas:
            if area.type != "PROPERTIES":
                continue
            for region in area.regions:
                if region.type == "WINDOW":
                    region.tag_redraw()


def ensure_monitoring_tick() -> None:
    """Start _monitoring_tick() if it isn't running -- the window's panel
    calls it too: a window can come back with a .blend saved with it open."""
    if not bpy.app.timers.is_registered(_monitoring_tick):
        bpy.app.timers.register(_monitoring_tick, first_interval=0.0, persistent=True)


def stop_monitoring_tick() -> None:
    if bpy.app.timers.is_registered(_monitoring_tick):
        bpy.app.timers.unregister(_monitoring_tick)


def _monitoring_tick():
    """While a monitoring window is open: scan the active project if it
    hasn't been (a switch of project, a window reopened with its .blend),
    read the farm again every _FARM_READ_EVERY, and redraw when what the
    table shows changed -- a popup redrew on every mouse move, a window
    only when told to. Stops itself once no window is left."""
    global _last_seen, _last_farm_read
    if not monitoring_windows():
        _last_seen = None
        return None
    from ..farm import farm_activity, request_monitor_refresh

    root = get_active_project_root()
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
    if seen != _last_seen:
        _last_seen = seen
        redraw_monitoring()
    return _TICK


def open_mainfile(filepath: str) -> None:
    """bpy.ops.wm.open_mainfile(), keeping the interface as it is while a
    monitoring window is open: loading the file's own closes every window
    the file doesn't have, that one included."""
    if monitoring_windows():
        bpy.ops.wm.open_mainfile(filepath=filepath, load_ui=False)
    else:
        bpy.ops.wm.open_mainfile(filepath=filepath)
