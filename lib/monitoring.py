"""The monitoring windows -- Project monitoring and Farm monitoring: each a
Properties editor on its Tool tab, where panels/monitoring_panel.py draws.
See NOTES.md, "Monitoring: windows, not popups"."""

import os
import sys
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
    """The open monitoring windows (of that kind), their screens marked
    again first (_window_kinds). Looked up every time, never kept: a window,
    its areas and regions are freed when it closes or a file loads (see
    NOTES.md, "Project walk")."""
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


def bring_monitoring_to_front(context, kind: str) -> bool:
    """Bring that kind's open monitoring window to the front. No Blender
    API does (Window has no such method, its x/y are read-only): on Windows
    the system's own SetForegroundWindow on its handle -- it stays where it
    is, a second screen included; elsewhere, or if that failed, a new one
    opened in front and the old one closed -- same content (filters, page,
    detail live in memory), over the old one, as big (_duplicate_window()).
    False if it couldn't. See NOTES.md, "Monitoring windows: to the front"."""
    old = monitoring_windows(kind)
    if not old:
        return False
    if sys.platform == "win32" and _raise_win32(old[0]):
        return True
    # The new one first: it takes the focus, and no window this operator
    # runs in is closed under it. A copy of the old one's editor where it
    # is, as big (_duplicate_window()); a plain new window if that failed.
    if not _duplicate_window(context, old[0], kind) and not open_monitoring_window(
        context, kind
    ):
        return False
    for window in old:
        try:
            with context.temp_override(window=window):
                bpy.ops.wm.window_close()
        except (RuntimeError, TypeError):
            pass
    return True


def _duplicate_window(context, window, kind: str) -> bool:
    """A new window holding a copy of window's editor (screen.area_dupli,
    "Duplicate Area into New Window"): opened over that area, at its size
    -- what window_new() can't be told. Marked as a monitoring window of
    kind. False if Blender didn't open one."""
    wm = context.window_manager
    before = {w.as_pointer() for w in wm.windows}
    area = max(window.screen.areas, key=lambda a: a.width * a.height)
    try:
        with context.temp_override(window=window, screen=window.screen, area=area):
            bpy.ops.screen.area_dupli("INVOKE_DEFAULT")
    except (RuntimeError, TypeError):
        return False
    new = [w for w in wm.windows if w.as_pointer() not in before]
    if not new:
        return False
    new[0].screen[MONITORING_SCREEN_KEY] = kind
    _window_kinds[new[0].as_pointer()] = kind
    bpy.app.timers.register(_show_tool_tab(new[0].as_pointer()), first_interval=0.0)
    ensure_monitoring_tick()
    return True


def _raise_win32(window) -> bool:
    """SetForegroundWindow on the native window of this Blender process
    whose client area is window's size (its position breaking a tie: two
    monitoring windows alike). Allowed: this process is the foreground one,
    the click came from it. False on any failure."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        pid = os.getpid()
        handles = []
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def visit(hwnd, _lparam):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(hwnd):
                handles.append(hwnd)
            return True

        user32.EnumWindows(enum_proc(visit), 0)
        best = None
        for hwnd in handles:
            rect = wintypes.RECT()
            corner = wintypes.POINT(0, 0)
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            user32.ClientToScreen(hwnd, ctypes.byref(corner))
            size_gap = abs(rect.right - window.width) + abs(rect.bottom - window.height)
            score = (size_gap, abs(corner.x - window.x))
            if best is None or score < best[0]:
                best = (score, hwnd)
        if best is None or best[0][0] > 4:
            return False
        hwnd = best[1]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        return False


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
            with bpy.context.temp_override(
                window=window, screen=window.screen, area=area
            ):
                try:
                    space.context = "TOOL"
                except TypeError:
                    pending = True
        return 0.05 if pending and tries > 0 else None

    return tick


def redraw_monitoring(kind: str | None = None) -> None:
    """Redraw the monitoring windows (of that kind): their editor's main region."""
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
    """Stop _monitoring_tick (the last monitoring window closed, unregister)."""
    if bpy.app.timers.is_registered(_monitoring_tick):
        bpy.app.timers.unregister(_monitoring_tick)


def _monitoring_tick():
    """Redraw the open monitoring windows when what they show changed;
    Project: scan an unscanned project, re-read the farm every
    _FARM_READ_EVERY; Farm: keep its refresh timer running. Stops with the
    last window. See NOTES.md, "Monitoring: windows, not popups"."""
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
        seen = (
            str(root),
            cache.get("status"),
            id(cache.get("jobs")),
            id(cache.get("workers")),
        )
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
    """memory_prop() for an enum. Its get/set deal in item values -- an
    item's own number when it has one (the departments': 1, 2, 4...), else
    its index: kept by identifier, so a dynamic list (prefixes, sequences)
    changing keeps the choice."""

    def values(self) -> dict:
        found = items(self, bpy.context) if callable(items) else items
        return {
            item[0]: item[-1] if len(item) in (4, 5) else i
            for i, item in enumerate(found)
        }

    def get(self):
        by_id = values(self)
        return by_id.get(store.get(key), next(iter(by_id.values()), 0))

    def set(self, value):
        for identifier, item_value in values(self).items():
            if item_value == value:
                store[key] = identifier

    return bpy.props.EnumProperty(items=items, get=get, set=set, **kwargs)


# Pages sized on the window -- see NOTES.md, "Monitoring windows: pages
# sized on the window". A list row's height (a widget line, the spacing
# and the LINE separator under it), in widget units: the one constant to
# recalibrate if a page overflows the window or leaves a gap.
ROW_UNITS = 1.9
# A list never shows fewer rows (blank ones below) -- under that, the
# window's region scrolls.
MIN_ROWS = 6

# Each window's page and page count, in memory like its filters, with the
# filters it was counted for.
_pages: dict = {kind: {} for kind in MONITORING_KINDS}


def turn_page(kind: str, step: int, to_end: bool = False) -> None:
    """step pages on (-1 / +1), or to the first / last with to_end --
    within the page count last drawn."""
    store = _pages[kind]
    pages = store.get("pages", 1)
    page = (1 if step < 0 else pages) if to_end else store.get("page", 1) + step
    store["page"] = max(1, min(page, pages))
    redraw_monitoring(kind)


def rows_that_fit(context, reserved_units: float) -> int:
    """List rows that fit the window's region once reserved_units (its
    filters, header, footer, margins -- widget units) are taken, never
    under MIN_ROWS."""
    unit = 20 * (context.preferences.system.ui_scale or 1.0)  # 0 in background
    return max(MIN_ROWS, int((context.region.height / unit - reserved_units) / ROW_UNITS))


def paginate(kind: str, items: list, per_page: int, filters: tuple) -> tuple:
    """(items on the page, page, page count) of a window's list: its page
    clamped to the count, back to 1 when filters changed since. draw()-safe:
    writes the store, not the property."""
    store = _pages[kind]
    if store.get("filters") != filters:
        store["filters"] = filters
        store["page"] = 1
    pages = store["pages"] = max(1, -(-len(items) // per_page))
    page = store["page"] = max(1, min(store.get("page", 1), pages))
    start = (page - 1) * per_page
    return items[start : start + per_page], page, pages


# "< Page 12 / 34 >" with its spacing, in widget units: the footer's right part.
_PAGER_UNITS = 8


def split_footer(context, layout) -> tuple:
    """(left, right) of a list's footer: right just wide enough for
    draw_pager(), its content against the window's right edge."""
    unit = 20 * (context.preferences.system.ui_scale or 1.0)
    factor = max(0.5, 1 - _PAGER_UNITS * unit / max(context.region.width, 1))
    split = layout.split(factor=factor)
    left = split.row()
    left.alignment = "LEFT"
    right = split.row()
    right.alignment = "RIGHT"
    return left, right


def draw_pager(layout, page: int, pages: int) -> None:
    """ "< Page 2 / 5 >" -- nothing for one page. The arrows:
    m_pipeline.monitoring_page (Ctrl+click: first / last; the arrow keys
    too, see register_monitoring_keymap())."""
    if pages < 2:
        return
    pager = layout.row(align=True)
    pager.alignment = "RIGHT"
    prev = pager.row(align=True)
    prev.enabled = page > 1
    prev.operator("m_pipeline.monitoring_page", text="", icon="TRIA_LEFT").step = -1
    pager.separator(factor=0.5)
    text = f"Page {page} / {pages}"
    label = pager.row(align=True)
    label.active = False
    # Sized on its text and centred: left to Blender, the label came out
    # far wider than its text, a gap before the right arrow.
    label.ui_units_x = 0.35 * len(text) + 0.6
    label.alignment = "CENTER"
    label.label(text=text)
    pager.separator(factor=0.5)
    nxt = pager.row(align=True)
    nxt.enabled = page < pages
    nxt.operator("m_pipeline.monitoring_page", text="", icon="TRIA_RIGHT").step = 1


# The monitoring windows' keys: (keymap, space, operator, key, ctrl,
# properties). Their operators' poll() keeps them to those windows. The
# arrows go in "Frames", whose own Left / Right (frame step, Ctrl: time
# jump) a region checks before the Properties editor's keymap -- an
# addon's item wins inside the same keymap. See NOTES.md, "Monitoring
# windows: pages sized on the window".
_KEYMAP_ITEMS = (
    ("Frames", "EMPTY", "m_pipeline.monitoring_page", "LEFT_ARROW", False, {"step": -1}),
    ("Frames", "EMPTY", "m_pipeline.monitoring_page", "RIGHT_ARROW", False, {"step": 1}),
    (
        "Frames",
        "EMPTY",
        "m_pipeline.monitoring_page",
        "LEFT_ARROW",
        True,
        {"step": -1, "to_end": True},
    ),
    (
        "Frames",
        "EMPTY",
        "m_pipeline.monitoring_page",
        "RIGHT_ARROW",
        True,
        {"step": 1, "to_end": True},
    ),
    ("Property Editor", "PROPERTIES", "m_pipeline.monitoring_back", "ESC", False, {}),
    ("Property Editor", "PROPERTIES", "m_pipeline.monitoring_switch", "TAB", False, {}),
)
_keymap_items: list = []


def register_monitoring_keymap() -> None:
    """Arrows: previous / next page (Ctrl: first / last); Esc: back from a
    detail to the list; Tab: assets <-> shots, jobs <-> workers. Needs the addon keyconfig (not there at register())."""
    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc or _keymap_items:
        return
    for km_name, space, idname, key, ctrl, props in _KEYMAP_ITEMS:
        km = kc.keymaps.new(name=km_name, space_type=space)
        kmi = km.keymap_items.new(idname, type=key, value="PRESS", ctrl=ctrl)
        for name, value in props.items():
            setattr(kmi.properties, name, value)
        _keymap_items.append((km, kmi))


def draw_addon_keys(context, layout) -> None:
    """The addon's shortcuts, editable (the user keyconfig's copy, saved
    with the preferences like any shortcut): Ctrl+S, and the monitoring
    windows' keys."""
    import rna_keymap_ui

    kc = context.window_manager.keyconfigs.user
    wanted = {("Window", "wm.safe_save")} | {
        (km_name, idname) for km_name, _space, idname, *_rest in _KEYMAP_ITEMS
    }
    for km_name in dict.fromkeys(name for name, _ in wanted):
        km = kc.keymaps.get(km_name)
        if km is None:
            continue
        for kmi in km.keymap_items:
            if (km_name, kmi.idname) in wanted:
                rna_keymap_ui.draw_kmi([], kc, km, kmi, layout, 0)


def unregister_monitoring_keymap() -> None:
    """Remove the shortcuts register_monitoring_keymap() added."""
    for km, kmi in _keymap_items:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    _keymap_items.clear()


# Blender's active tool (its name and settings) heads the Properties
# editor's Tool tab, above the monitoring panels: hidden in their windows
# by wrapping its poll() -- see NOTES.md, "Monitoring windows: pages sized
# on the window".
_ACTIVE_TOOL_PANEL = "VIEW3D_PT_active_tool_duplicate"


def hide_active_tool_in_monitoring() -> None:
    """Wrap the active tool panel's poll() to say no in a monitoring
    window. Nothing if Blender's panel or its poll() isn't there."""
    cls = getattr(bpy.types, _ACTIVE_TOOL_PANEL, None)
    if cls is None or "poll" not in cls.__dict__ or "_m_pipeline_poll" in cls.__dict__:
        return
    original = cls.poll

    def poll(_cls, context):
        return not monitoring_kind(context.screen) and original(context)

    cls._m_pipeline_poll = cls.__dict__["poll"]
    cls.poll = classmethod(poll)


def restore_active_tool() -> None:
    """Undo hide_active_tool_in_monitoring()."""
    cls = getattr(bpy.types, _ACTIVE_TOOL_PANEL, None)
    if cls is not None and "_m_pipeline_poll" in cls.__dict__:
        # From __dict__: the attribute would unwrap the classmethod.
        cls.poll = cls.__dict__["_m_pipeline_poll"]
        del cls._m_pipeline_poll


def open_mainfile(filepath: str) -> None:
    """bpy.ops.wm.open_mainfile(), keeping the interface as it is while a
    monitoring window is open: loading the file's own closes every window
    the file doesn't have, that one included."""
    if monitoring_windows():
        bpy.ops.wm.open_mainfile(filepath=filepath, load_ui=False)
    else:
        bpy.ops.wm.open_mainfile(filepath=filepath)
