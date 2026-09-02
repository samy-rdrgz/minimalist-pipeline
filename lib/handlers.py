"""Core Blender operators and app handlers."""

from pathlib import Path

import bpy

from .actions import (
    LOCKED_FILE_EXPLANATION,
    READ_ONLY_EXPLANATION,
    STABLE_FILE_EXPLANATION,
    PipelineAction,
    set_pending_action,
)
from .config import (
    file_in_active_project,
    find_known_project_for_file,
    get_active_project_root,
)
from .core import (
    acquire_lock,
    addon_pref,
    get_machine_id,
    locked_json,
    refresh_lock,
)
from .errors import PipelineError
from .libraries import import_warnings
from .logs import log
from .session import (
    close_session,
    get_opened_as_read_only,
    save_project_data,
    scan_sessions,
    session_update,
    set_active_project_root,
    set_opened_as_read_only,
)
from .tracking import check_library_update, wipmeta_touch

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _propose_project_switch(project_path: str):
    """Build and show a PipelineAction proposing to activate project_path.
    Never switches silently, the artist must confirm."""

    def _switch():
        prefs = addon_pref()
        set_active_project_root(prefs, project_path)
        try:
            save_project_data(prefs)
        except PipelineError as e:
            log(e.level, "project_switch", e.message)
        session_update()

    action = PipelineAction(
        title="Different project detected",
        message=f"This file belongs to:\n{Path(project_path).name}\nnot the active project.",
        severity="warning",
        choices=[
            ("Not now", lambda: None, "Keep the current active project."),
            (
                "Switch to this project",
                _switch,
                f"Make {Path(project_path).name} the active project.",
            ),
        ],
    )
    set_pending_action(action)
    if not bpy.app.background:
        bpy.ops.pipeline.action_popup("INVOKE_DEFAULT")


def _propose_read_only_increment(msg: str, explanation: str = ""):
    """Build and show a PipelineAction offering to increment out of a
    read-only file, or keep working read-only."""

    def _increment():
        # Deferred one timer tick: increment_version opens its own
        # invoke_props_dialog -- calling it synchronously from inside this
        # popup's own execute() risks the popup-chaining issue documented in
        # saving.py's WM_OT_safe_save._open_popup.
        bpy.app.timers.register(
            lambda: bpy.ops.pipeline.increment_version("INVOKE_DEFAULT"),
            first_interval=0.05,
        )

    action = PipelineAction(
        title="Opened as Read-Only",
        message=msg,
        severity="warning",
        choices=[
            ("Continue read-only", lambda: None, "Keep working as-is."),
            (
                "Increment outside stable",
                _increment,
                "Get a writable copy via increment.",
            ),
        ],
        explanation=explanation,
    )
    set_pending_action(action)
    bpy.ops.pipeline.action_popup("INVOKE_DEFAULT")


@bpy.app.handlers.persistent
def post_load_handler(*args):
    """After file load: log, then gate all further pipeline behavior to the
    active project -- active project's file: normal flow (session +
    auto-version); a *different* known project's: propose a switch, stop;
    unknown file: total silence, no popup. *args (unused): load_post's arity
    isn't a contract we control, stays robust either way."""
    if not bpy.data.filepath:
        return

    log("INFO", "file_open", f"{Path(bpy.data.filepath).name} opened")

    project_root = get_active_project_root()

    if not project_root or not file_in_active_project(
        bpy.data.filepath, str(project_root)
    ):
        other_path = find_known_project_for_file(
            bpy.data.filepath, addon_pref().opened_projects
        )
        if other_path and other_path != str(project_root):
            _propose_project_switch(other_path)
        return  # unknown file, or user dismissed the switch already -> silence

    if not bpy.app.background:
        scan_sessions()
        session_update()
        check_library_update()

        path = Path(bpy.data.filepath)
        tag = path.stem.rsplit("-", 1)
        is_stable = len(tag) == 2 and tag[1] == "stable"
        already_flagged = get_opened_as_read_only() == bpy.data.filepath
        if addon_pref().always_read_only or already_flagged or is_stable:
            set_opened_as_read_only(bpy.data.filepath)
            msg = (
                "This is a stable version, opened read-only. Increment or continue in read-only."
                if is_stable
                else "This file is opened read-only. Increment or continue in read-only."
            )
            _propose_read_only_increment(
                msg, STABLE_FILE_EXPLANATION if is_stable else READ_ONLY_EXPLANATION
            )
            return

        free = acquire_lock(Path(bpy.data.filepath), get_machine_id())
        if not free:
            set_opened_as_read_only(bpy.data.filepath)
            with locked_json(path.parent / f".{path.name}.lock") as box:
                data = box.get("data", {})
            lines = ["File is lock by another user :"] + [
                f"{n} : {m}" for n, m in data.items()
            ]
            bpy.ops.pipeline.text_popup(
                "INVOKE_DEFAULT",
                title="Opened as Read-Only",
                message="\n".join(lines),
                icon="ERROR",
                explanation=LOCKED_FILE_EXPLANATION,
            )
            return

        bpy.ops.pipeline.auto_version("INVOKE_DEFAULT")


@bpy.app.handlers.persistent
def on_quit_handler(*args):
    """Before Blender quits: close the current session. Worked departments
    are recorded live via the asset/shot panel toggles, not here -- exit_pre
    fires while Blender is already tearing down, too late for a popup.
    *args (unused): see post_load_handler's note on handler arity."""
    close_session()


@bpy.app.handlers.persistent
def save_post_handler(*args):
    """After a manual save: refresh the session heartbeat, and stamp this
    version's .wipmeta with who saved it (auto_version's same-day-different
    -user check relies on this). *args (unused): see post_load_handler's
    note on handler arity."""
    session_update()
    filepath = bpy.data.filepath
    if filepath and file_in_active_project(filepath):
        wipmeta_touch(Path(filepath))


@bpy.app.handlers.persistent
def import_post_handler(import_context, *_extra):
    """After an append/link: run the append-vs-link warning logic. Never raises.
    *_extra (unused): see post_load_handler's note on handler arity."""
    try:
        import_warnings(import_context.import_items)

    except Exception:
        pass


def heartbeat_30s() -> float:
    """Update session heartbeat every 30 seconds, and refresh the current
    file's lock too if this session is the one holding it."""
    if bpy.app.background:
        return 30
    session_update()
    filepath = bpy.data.filepath
    if (
        filepath
        and get_opened_as_read_only() != filepath
        and file_in_active_project(filepath)
    ):
        refresh_lock(Path(filepath), get_machine_id())
    return 30


def register_handlers():
    """Register post-load handler for auto-versioning."""
    if not bpy.app.timers.is_registered(heartbeat_30s):
        bpy.app.timers.register(heartbeat_30s, persistent=True)
    if post_load_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(post_load_handler)
    if on_quit_handler not in bpy.app.handlers.exit_pre:
        bpy.app.handlers.exit_pre.append(on_quit_handler)
    if save_post_handler not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(save_post_handler)
    if import_post_handler not in bpy.app.handlers.blend_import_post:
        bpy.app.handlers.blend_import_post.append(import_post_handler)


def unregister_handlers():
    """Unregister post-load handler."""
    if bpy.app.timers.is_registered(heartbeat_30s):
        bpy.app.timers.unregister(heartbeat_30s)
    if post_load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(post_load_handler)
    if on_quit_handler in bpy.app.handlers.exit_pre:
        bpy.app.handlers.exit_pre.remove(on_quit_handler)
    if save_post_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(save_post_handler)
    if import_post_handler in bpy.app.handlers.blend_import_post:
        bpy.app.handlers.blend_import_post.remove(import_post_handler)
