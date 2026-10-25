"""Logging, session tracking, and project backup persistence."""

import os
from datetime import datetime
from pathlib import Path

import bpy

from .actions import PipelineAction, set_pending_action
from .config import (
    ConfigCache,
    blender_version_mismatch,
    file_in_active_project,
    get_active_project_root,
    to_relative,
    type_by_folder,
)
from .core import (
    addon_pref,
    get_machine_id,
    locked_json,
    now,
)
from .errors import PipelineError
from .logs import log

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def get_user_data(user: str = "unknown") -> dict:
    """Return current user identity for logging: display name + a locally-
    generated machine id (no hostname/IP/OS-name reads -- see NOTES.md,
    "Addon register()"). "machine" is a short slice of machine_id, just
    enough to tell two machines apart in a UI label; "uuid" keeps the full
    id for exact matching (worker/lock ownership lookups)."""
    machine_id = get_machine_id() or "unknown"
    return {
        "pid": os.getpid(),
        "machine": machine_id[:8],
        "user": user,
        "uuid": machine_id,
    }


def get_user(context=None) -> str:
    """Current user login for logging: prefs.user_name, or "unknown" if
    unset. No OS-login fallback -- see NOTES.md, "Addon register()";
    prefs.user_name is seeded with a locally-generated placeholder at first
    register(), so this is effectively defensive-only (prefs unreachable)."""
    try:
        if bpy.app.background:
            return "cmd"
        prefs = addon_pref(context)
        if prefs:
            name = getattr(prefs, "user_name", "")
            if name:
                return name.lower()
    except Exception:
        pass
    return "unknown"


def get_user_role(context=None) -> str:
    """The validation role this user writes under (prefs.user_role), if the
    active project has it -- "" otherwise: the team's own notes, no
    approval to give."""
    from .config import validation_roles

    try:
        prefs = addon_pref(context)
        role = (getattr(prefs, "user_role", "") or "").strip().lower() if prefs else ""
    except Exception:
        return ""
    return role if role in {r["name"] for r in validation_roles()} else ""


# ---------------------------------------------------------------------------
# Project backup (addon-level persistence of opened projects list)
# ---------------------------------------------------------------------------


def get_backup_filepath() -> Path:
    """Path to addon backup JSON, in this extension's own user data
    directory -- bpy.utils.extension_path_user(), not script_path_user()
    (assumes a legacy, pre-Extensions addon layout; flagged by a Blender
    Extensions Platform review, see NOTES.md)."""
    pkg = __package__.rsplit(".", 1)[
        0
    ]  # "minimalist_pipeline.lib" -> "minimalist_pipeline"
    root = bpy.utils.extension_path_user(pkg, path="config", create=True)
    return Path(root) / "pipeline_backup.json"


# The addon's own settings (Preferences), kept in the backup JSON too:
# Blender's storage for them doesn't survive an extension update -- see
# NOTES.md, "Addon settings lost on update". Saved on every change
# (save_settings(), their update callback), so the backup is always the
# latest and restored over whatever Blender kept.
ADDON_SETTINGS = (
    "experience_level",
    "silent_auto_increment",
    "auto_worker_on_open",
    "always_read_only",
    "ffmpeg_path",
    "onboarding_seen",
    "user_role",
)
# True while load_project_data() restores them: their update callback would
# write the backup back while it's being read.
_restoring = False


def save_settings(prefs, _context=None) -> None:
    """Update callback of the ADDON_SETTINGS properties: write the backup
    now. Never raises (a property update can't report)."""
    if _restoring:
        return
    try:
        save_project_data(prefs)
    except Exception as e:
        log("WARNING", "session", f"Could not back up the addon settings: {e}")


def save_project_data(prefs) -> bool:
    """Persist opened projects list, user_name and the ADDON_SETTINGS -- see
    NOTES.md, "Addon register()" -- to backup JSON."""
    data = {
        "active_project_root": prefs.active_project_root,
        "opened_projects": [
            {"name": item.name, "path": item.path} for item in prefs.opened_projects
        ],
        "user_name": prefs.user_name,
        "settings": {name: getattr(prefs, name) for name in ADDON_SETTINGS},
    }
    filepath = get_backup_filepath()
    filepath.parent.mkdir(parents=True, exist_ok=True)

    try:
        with locked_json(filepath) as box:
            box["data"] = data
            box["action"] = "to_write"
        # No success log: a per-machine file has no place in the project's
        # shared log, written on every launch and farm subprocess (NOTES.md).
        return True
    except Exception as e:
        raise PipelineError(f"Backup save failed: {e}")


def load_project_data(prefs) -> bool:
    """Restore opened projects list and the ADDON_SETTINGS from backup
    JSON, and user_name if Blender's own AddonPreferences storage came back
    empty -- see NOTES.md, "Addon register()"."""
    global _restoring
    filepath = get_backup_filepath()
    if not filepath.exists():
        raise PipelineError("Backup file not found.", level="WARNING")

    try:
        with locked_json(filepath) as box:
            data = box["data"] or {}

            # The backup wins: written on every change, it's the latest. A
            # backup from before they were kept has none: left as they are.
            _restoring = True
            try:
                for name, value in (data.get("settings") or {}).items():
                    if name in ADDON_SETTINGS:
                        try:
                            setattr(prefs, name, value)
                        except (TypeError, ValueError, AttributeError):
                            pass  # renamed enum item, wrong type: keep it
            finally:
                _restoring = False

            prefs.active_project_root = data.get("active_project_root", "")
            prefs.opened_projects.clear()

            for item_data in data.get("opened_projects", []):
                new_item = prefs.opened_projects.add()
                new_item.name = item_data.get("name", "unknown")
                new_item.path = item_data.get("path", "")

            # Backup is a fallback only -- don't overrule a live value.
            if not prefs.user_name and data.get("user_name"):
                prefs.user_name = data["user_name"]

            return True
    except Exception as e:
        raise PipelineError(f"Backup load failed: {e}")


def set_active_project_root(prefs, new_root: str) -> None:
    """Change prefs.active_project_root, handling the farm-role side effects:
    stop this instance's role for the project being left, auto-launch a
    worker for the new one if auto_worker_on_open is on. Centralized so
    every caller behaves the same way -- opened_projects bookkeeping stays
    the caller's own job, this only owns active_project_root itself."""
    # Deferred: lib/ must not import farm/ at module level, since farm/ itself
    # imports from lib/ at its own module level (circular otherwise).
    from ..farm import (
        refresh_monitor_cache,
        reset_monitor_cache,
        stop_farm_role_for_project,
    )

    stop_farm_role_for_project(prefs.active_project_root)
    prefs.active_project_root = new_root

    # Keep the monitor cache in sync -- otherwise it shows the previous
    # project's status/jobs until the next _refresh_tick.
    if new_root:
        refresh_monitor_cache(force_rescan=True)
    else:
        reset_monitor_cache()

    if new_root and prefs.auto_worker_on_open:
        from ..farm import launch_worker

        launch_worker()


# ---------------------------------------------------------------------------
# Session tracking
# ---------------------------------------------------------------------------


def session_update():
    """Update the session state. Never raises: called from timers and app
    handlers with no operator around it to catch or report a lock failure."""
    if bpy.app.background or not bpy.data.filepath:
        return
    try:
        project_root = get_active_project_root()
    except Exception:
        return
    if not file_in_active_project(bpy.data.filepath, str(project_root)):
        return
    pid = os.getpid()
    data = {}
    path = ConfigCache.get_path("sessions") / f".session_{pid}.json"
    try:
        with locked_json(path) as box:
            data = box["data"] or {}

            # File switched without quitting Blender -- close the old session
            # (with its summary) instead of leaving it frozen.
            if data and data["filepath"] != bpy.data.filepath:
                _log_session_end(data)
                data = {}

            if not data:
                # No session_start line -- see _log_session_end() / NOTES.md.
                data = get_user_data(get_user()) | {
                    "filepath": bpy.data.filepath,
                    "file_type": type_by_folder(bpy.data.filepath, str(project_root)),
                    "opened_at": now(),
                    "last_ping": now(),
                }
                box["data"] = data
                box["action"] = "to_write"
            else:
                data["last_ping"] = now()
                box["data"] = data
                box["action"] = "to_write"
            return True
    except PipelineError as e:
        log("WARNING", "session_update", e.message)
        return False


def _log_session_end(data: dict) -> None:
    """Log the session_end summary line (work duration) to sessions_log_file.
    filepath is its own field, not parsed from message -- read back by
    WorkTimeCache (lib/tracking.py, see NOTES.md)."""
    try:
        opened_at = datetime.fromisoformat(data["opened_at"])
        last_ping = datetime.fromisoformat(data["last_ping"])
        nw = now(iso=False)
        duration = (last_ping - opened_at).total_seconds()
        closing = " (crash)" if (nw - last_ping).total_seconds() > 31 else ""
        # Project-relative: the log is shared, and each machine mounts the
        # project its own way (S:\..., \\host\share\...).
        filepath = to_relative(data["filepath"])
        log(
            "INFO",
            "session_end",
            f"{filepath} ({duration:.0f}s){closing}",
            file_type=data.get("file_type", "unknown"),
            filepath=filepath,
            duration_seconds=duration,
            log_file_key="sessions_log_file",
        )
    except Exception:
        pass


def close_session(session_file: Path | None = None):
    """Log session end and remove session file. Never raises: called from
    exit_pre (no operator to catch/report) and from scan_sessions's own loop."""
    if not session_file or not session_file.is_file():
        pid = os.getpid()
        try:
            session_file = ConfigCache.get_path("sessions") / f".session_{pid}.json"
        except Exception:
            return  # No active project -- nothing was ever tracked to close.
    if session_file.is_file():
        try:
            with locked_json(session_file) as box:
                data = box["data"] or {}
                box["action"] = "to_delete"
        except PipelineError as e:
            log("WARNING", "close_session", e.message)
            return

        if not data:
            return  # No session file found (no active project, or already cleaned up)

        _log_session_end(data)


def scan_sessions():
    """Scan for orphan session files and log crashes. Called from
    post_load_handler; never raises (close_session() is itself safe)."""
    if bpy.app.background:
        return
    sessions_dir = ConfigCache.get_path("sessions")
    for session_file in sessions_dir.glob(".session_*.json"):
        try:
            with locked_json(session_file) as box:
                data = box["data"]
            if data:
                last_ping = datetime.fromisoformat(data["last_ping"])
                nw = now(iso=False)
                if (nw - last_ping).total_seconds() > 40:
                    close_session(session_file)
        except Exception:
            pass


# mtime: the file's on disk when it was flagged -- what this session opened.
_opened_as_read_only: dict = {"value": "", "reason": "", "mtime": None}


def get_opened_as_read_only() -> str:
    """Filepath currently flagged read-only in this session, or ""."""
    return _opened_as_read_only["value"]


def get_read_only_reason() -> str:
    """Why that filepath is read-only: "stable" | "profile" | "reopened" | "locked" | "" ."""
    return _opened_as_read_only["reason"]


def _mtime(filepath: str) -> float | None:
    """filepath's mtime, None if it has none or can't be read."""
    try:
        return os.stat(filepath).st_mtime if filepath else None
    except OSError:
        return None


def set_opened_as_read_only(value: str = "", reason: str = ""):
    """Flag filepath as read-only for this session (empty string clears it),
    noting its mtime: the version on disk this session opened."""
    global _opened_as_read_only
    _opened_as_read_only["value"] = value
    _opened_as_read_only["reason"] = reason
    _opened_as_read_only["mtime"] = _mtime(value)


def read_only_unchanged_on_disk(filepath: str) -> bool:
    """Whether filepath, flagged read-only, is still on disk as this session
    opened it (or last saved it over): nobody saved it since, so saving
    over it loses nothing."""
    recorded = _opened_as_read_only["mtime"]
    return (
        _opened_as_read_only["value"] == filepath
        and recorded is not None
        and _mtime(filepath) == recorded
    )


def note_read_only_saved(filepath: str) -> None:
    """This session just saved over filepath, flagged read-only: what's on
    disk is its own again (read_only_unchanged_on_disk())."""
    if _opened_as_read_only["value"] == filepath:
        _opened_as_read_only["mtime"] = _mtime(filepath)


def warn_blender_version_mismatch() -> None:
    """Red (critical) popup when the active project expects another Blender
    major.minor than the one running. Never in background mode (farm
    workers, batch subprocesses). Timer-safe: returns None."""
    if bpy.app.background:
        return None
    try:
        mismatch = blender_version_mismatch()
    except Exception:
        return None  # no active project / unreadable config: nothing to compare
    if not mismatch:
        return None
    project, running = mismatch
    set_pending_action(
        PipelineAction(
            title=f"Wrong Blender version: {running} (project: {project})",
            message=(
                f"This project is made with Blender {project}, and this is "
                f"Blender {running}.\n\n"
                f"A file saved here may not open, or not look the same, in "
                f"Blender {project} -- for the rest of the team and for the "
                f"farm.\n\n"
                f"Close Blender and reopen the project with Blender {project}."
            ),
            severity="critical",
        )
    )
    bpy.ops.m_pipeline.action_popup("INVOKE_DEFAULT")
    return None
