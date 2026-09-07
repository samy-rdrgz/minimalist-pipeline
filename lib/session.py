"""Logging, session tracking, and project backup persistence."""

import os
from datetime import datetime
from pathlib import Path

import bpy

from .config import (
    ConfigCache,
    file_in_active_project,
    get_active_project_root,
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


# ---------------------------------------------------------------------------
# Project backup (addon-level persistence of opened projects list)
# ---------------------------------------------------------------------------


def get_backup_filepath() -> Path:
    """Path to addon backup JSON, in this extension's own user data
    directory -- bpy.utils.extension_path_user(), not script_path_user()
    (assumes a legacy, pre-Extensions addon layout; flagged by a Blender
    Extensions Platform review, see NOTES.md)."""
    pkg = __package__.rsplit(".", 1)[0]  # "minimalist_pipeline.lib" -> "minimalist_pipeline"
    root = bpy.utils.extension_path_user(pkg, path="config", create=True)
    return Path(root) / "pipeline_backup.json"


def save_project_data(prefs) -> bool:
    """Persist opened projects list to backup JSON."""
    data = {
        "active_project_root": prefs.active_project_root,
        "opened_projects": [
            {"name": item.name, "path": item.path} for item in prefs.opened_projects
        ],
    }
    filepath = get_backup_filepath()
    filepath.parent.mkdir(parents=True, exist_ok=True)

    try:
        with locked_json(filepath) as box:
            box["data"] = data
            box["action"] = "to_write"
        log("INFO", "backup", f"Backup saved: {filepath}")
        return True
    except Exception as e:
        raise PipelineError(f"Backup save failed: {e}")


def load_project_data(prefs) -> bool:
    """Restore opened projects list from backup JSON."""
    filepath = get_backup_filepath()
    if not filepath.exists():
        raise PipelineError("Backup file not found.", level="WARNING")

    try:
        with locked_json(filepath) as box:
            data = box["data"] or {}

            prefs.active_project_root = data.get("active_project_root", "")
            prefs.opened_projects.clear()

            for item_data in data.get("opened_projects", []):
                new_item = prefs.opened_projects.add()
                new_item.name = item_data.get("name", "unknown")
                new_item.path = item_data.get("path", "")

            log("INFO", "backup", "Project data loaded.")
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
        log(
            "INFO",
            "session_end",
            f"{data['filepath']} ({duration:.0f}s){closing}",
            file_type=data.get("file_type", "unknown"),
            filepath=data["filepath"],
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


_opened_as_read_only: dict = {"value": "", "reason": ""}


def get_opened_as_read_only() -> str:
    """Filepath currently flagged read-only in this session, or ""."""
    return _opened_as_read_only["value"]


def get_read_only_reason() -> str:
    """Why that filepath is read-only: "stable" | "profile" | "reopened" | "locked" | "" ."""
    return _opened_as_read_only["reason"]


def set_opened_as_read_only(value: str = "", reason: str = ""):
    """Flag filepath as read-only for this session (empty string clears it)."""
    global _opened_as_read_only
    _opened_as_read_only["value"] = value
    _opened_as_read_only["reason"] = reason
