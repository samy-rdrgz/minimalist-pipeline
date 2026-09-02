"""Append-only JSONL pipeline log, rotated by size into config/logs/archives/."""

import json
from pathlib import Path

# Rotate a log past this size into config/logs/archives/. Size, not a line
# count -- see NOTES.md.
LOG_ROTATE_MAX_BYTES = 5_000_000


def log(
    level: str,
    action: str,
    message: str,
    *,
    log_file_key: str = "pipeline_log_file",
    **extra,
):
    """Append JSON log line. Never raises. log_file_key: target ConfigCache
    path, "sessions_log_file" for session_end (own file). Rotated past
    LOG_ROTATE_MAX_BYTES -- see _rotate_if_needed()."""
    from .config import ConfigCache, get_active_project_root
    from .core import acquire_lock, get_machine_id, now, release_lock
    from .session import get_user

    try:
        project_root = get_active_project_root()
        if not project_root:
            return
        user = get_user()
        entry = {
            "ts": now(),
            "level": level.lower(),
            "user": user.lower(),
            "action": action.lower(),
            "message": message,
            **extra,
        }
        log_file = ConfigCache.get_path(log_file_key)
        line = json.dumps(entry, ensure_ascii=False) + "\n"

        machine_id = get_machine_id()
        if not acquire_lock(log_file, machine_id):
            return  # never block on a log write
        try:
            _rotate_if_needed(log_file, ConfigCache.get_path("logs_archives"), now)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
        finally:
            release_lock(log_file, machine_id)
    except Exception:
        pass


def _rotate_if_needed(log_file: Path, archives_dir: Path, now) -> None:
    """Move log_file into archives_dir, timestamped, once past
    LOG_ROTATE_MAX_BYTES. Called under log_file's own lock (see log()).
    Never raises."""
    try:
        if log_file.stat().st_size <= LOG_ROTATE_MAX_BYTES:
            return
        archives_dir.mkdir(parents=True, exist_ok=True)
        stamp = now(iso=False).strftime("%Y%m%d-%H%M%S")
        archived = archives_dir / f"{log_file.stem}_{stamp}{log_file.suffix}"
        log_file.rename(archived)
    except OSError:
        pass
