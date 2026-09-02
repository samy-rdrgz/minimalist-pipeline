"""Project config: cache, reading, filename parsing, file routing utilities."""

import json
import re
from pathlib import Path

import bpy

from .core import addon_pref, json_get, locked_json
from .errors import PipelineError

# ---------------------------------------------------------------------------
# Project config I/O
# ---------------------------------------------------------------------------


def get_config_filepath(project_root: str | Path | None = None) -> Path:
    """Path to project_config.json for project_root, or the active project
    if omitted. Thread project_root explicitly rather than relying on
    ConfigCache.get_path()'s ambient active-project lookup, or a caller
    targeting a specific non-active project silently hits the wrong one."""
    if project_root:
        return Path(project_root) / "config" / "project_config.json"
    return ConfigCache.get_path("config_file")


def read_project_config(project_root: str) -> dict:
    """Read and return project config dict. Raises PipelineError on failure."""
    if not project_root:
        raise PipelineError("No active project path.")

    config_file = get_config_filepath(project_root)

    if not config_file.exists():
        raise PipelineError(f"Config not found: {config_file}")

    try:
        with locked_json(config_file) as box:
            return box["data"] or {}
    except json.JSONDecodeError:
        raise PipelineError("Config file corrupted (invalid JSON).")
    except Exception as e:
        raise PipelineError(f"Failed to read config: {e}")


# ---------------------------------------------------------------------------
# Config cache
# ---------------------------------------------------------------------------

_daemon_active_project_root = ""


def set_daemon_active_project_root(project_root: str | Path) -> None:
    """Set the project root used by get_active_project_root() in a headless
    (bpy.app.background) process that never loads an actual .blend file --
    e.g. templates/batch_create_entry.py, which only knows its project via
    the request JSON. No-op guard against None/empty by design: callers
    pass a definite path."""
    global _daemon_active_project_root
    _daemon_active_project_root = str(project_root)


def get_active_project_root() -> Path | None:
    """Return the base project path depending of context execution. None if not found."""
    if bpy.app.background:
        if _daemon_active_project_root:
            return Path(_daemon_active_project_root)
        if bpy.data.filepath:
            root = find_project_root(bpy.data.filepath)
            if root:
                return Path(root)
        return None

    if bpy and hasattr(bpy.context, "preferences"):
        prefs = addon_pref()
        if prefs:
            path = prefs.active_project_root
            return Path(path) if path else None
        else:
            return None
    return _daemon_active_project_root  # settable by the daemon at startup


class ConfigCache:
    """Cache for the active project's config, invalidated when the JSON file
    changes. All classmethods: ConfigCache.get(), .get_path("monitor_file"),
    .invalidate() -- never instantiated."""

    _cache: dict | None = None
    _mtime: float | None = None
    _path: Path | None = None

    @classmethod
    def get(cls) -> dict:
        """Return config dict, re-reading only if file changed on disk."""
        project_root = get_active_project_root()
        if not project_root:
            cls.invalidate()
            return {}
        config_file = get_config_filepath()
        current_mtime = config_file.stat().st_mtime
        if cls._path != config_file or cls._mtime != current_mtime:
            cls._cache = read_project_config(project_root)
            cls._mtime = current_mtime
            cls._path = config_file

        return cls._cache or {}

    @classmethod
    def get_asset_regex(cls) -> re.Pattern:
        """Return a regex pattern for asset filenames based on the project config."""
        config = cls.get()
        prefixes = json_get(config, "structure.asset_prefixes", ["ch"]) + json_get(
            config, "structure.library_prefixes", []
        )
        prefixes = "|".join(prefixes)
        version_prefix = json_get(config, "naming.version.prefix", "v")
        tags = "|".join(json_get(config, "tags", ["stable"]))

        pattern_str = (
            rf"^(?P<prefix>{prefixes})"
            rf"_(?P<name>[a-z0-9\-]+)"
            rf"_{version_prefix}(?P<number>\d+)"
            rf"(?:-(?P<tag>{tags}))?"
            rf"\.blend$"
        )
        return re.compile(pattern_str)

    @classmethod
    def get_shot_regex(cls) -> re.Pattern:
        """Return a regex pattern for shot filenames based on the project config."""
        config = cls.get()
        sequence_prefix = json_get(config, "naming.sequence.prefix", "sq")
        shot_prefix = json_get(config, "naming.shot.prefix", "sh")
        version_prefix = json_get(config, "naming.version.prefix", "v")
        tags = "|".join(json_get(config, "tags", ["stable"]))

        pattern_str = (
            rf"^{sequence_prefix}(?P<sequence>\d+)"
            rf"_{shot_prefix}(?P<shot>\d+(?:-\d+)*)"
            rf"_{version_prefix}(?P<number>\d+)"
            rf"(?:-(?P<tag>{tags}))?"
            rf"\.blend$"
        )
        return re.compile(pattern_str)

    @classmethod
    def invalidate(cls):
        """Force re-read on next get() call."""
        cls._cache = None
        cls._mtime = None
        cls._path = None

    @classmethod
    def get_path(cls, name: str) -> Path:
        """Return the absolute path of parameter based on the folder tree convention."""
        config = "config"
        logs = f"{config}/logs"
        farm = f"{config}/.farm"
        queue = f"{farm}/queue"
        presets = f"{config}/presets"

        dictionary = {
            "config": config,
            "presets": presets,
            "ffmpeg_presets": f"{presets}/ffmpeg_presets",
            "logs": logs,
            "logs_archives": f"{logs}/archives",
            "sessions": f"{config}/.sessions",
            # Farm
            "farm": f"{config}/.farm",
            "workers": f"{farm}/workers",
            "queue": f"{farm}/queue",
            "farm_incomings": f"{queue}/incomings",
            "farm_actives": f"{queue}/actives",
            "farm_archives": f"{queue}/archives",
            "farm_requests": f"{queue}/requests",
            # Files
            "config_file": f"{config}/project_config.json",
            "pipeline_log_file": f"{logs}/pipeline_log.jsonl",
            "sessions_log_file": f"{logs}/sessions_log.jsonl",
            "monitor_file": f"{farm}/monitor.lock",
            "asset_preset_file": f"{presets}/asset_file_preset.py",
        }
        return to_absolute(dictionary[name])


# ---------------------------------------------------------------------------
# Filename utilities
# ---------------------------------------------------------------------------


def parse_filename(filename: str) -> dict | None:
    """Parse pipeline filename into {prefix, name, number, tag} or None."""
    match = ConfigCache.get_asset_regex().match(filename)
    if not match:
        match = ConfigCache.get_shot_regex().match(filename)
    if not match:
        return None
    return match.groupdict()


def get_base_filename(filename: str) -> str | None:
    """Return base file name without version."""
    dict = parse_filename(filename)
    if dict and dict["number"]:
        v_prefix = json_get(ConfigCache.get(), "naming.version.prefix", "v")
        return filename.split("_" + v_prefix + dict["number"], 1)[0]
    else:
        return None


def sanitize_name(raw: str) -> str:
    """Sanitize user input into a valid asset name component.
    Lowercase, a-z 0-9 and hyphens only. Spaces become hyphens.
    """
    s = raw.strip().lower()
    s = s.replace(" ", "-")
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    return s or "unnamed"


def format_shot_segment(shot_numbers: list[int], config: dict | None = None) -> str:
    """Sorted, deduped, zero-padded shot numbers joined by '-' (e.g. [45, 30, 40] -> "030-040-045")."""
    config = config if config is not None else ConfigCache.get()
    digits = json_get(config, "naming.shot.digits", 3)
    return "-".join(f"{n:0{digits}d}" for n in sorted(set(shot_numbers)))


def format_camera_name(
    sequence_label: str, shot_number: int, config: dict | None = None, version: int = 1
) -> str:
    """Deterministic camera name for one shot: cam_sq040_sh045_v001."""
    config = config if config is not None else ConfigCache.get()
    shot_digits = json_get(config, "naming.shot.digits", 3)
    shot_prefix = json_get(config, "naming.shot.prefix", "sh")
    v_prefix = json_get(config, "naming.version.prefix", "v")
    v_digits = json_get(config, "naming.version.digits", 3)
    sh = f"{shot_prefix}{shot_number:0{shot_digits}d}"
    v = f"{v_prefix}{version:0{v_digits}d}"
    return f"cam_{sequence_label}_{sh}_{v}"


def shots_in_segment(shot_segment: str) -> list[int]:
    """Parse a shot segment ("030-040-045") back into individual shot numbers."""
    return [int(n) for n in shot_segment.split("-")]


def parse_camera_name(
    camera_name: str, sequence_label: str, config: dict | None = None
) -> int | None:
    """Shot number from a camera name ("cam_sq040_sh045_v002" -> 45), or
    None if it doesn't match this sequence's convention. Only the prefix is
    checked -- whatever follows the shot number (version, a "_closeup"
    tag, nothing at all) is accepted as-is, not required to be a version."""
    config = config if config is not None else ConfigCache.get()
    shot_prefix = json_get(config, "naming.shot.prefix", "sh")
    pattern = re.compile(
        rf"^cam_{re.escape(sequence_label)}_{re.escape(shot_prefix)}(?P<shot>\d+)"
    )
    m = pattern.match(camera_name)
    return int(m.group("shot")) if m else None


def prefix_to_parent_folder(prefix: str, config: dict) -> str:
    """Determine parent folder name ('assets' or 'library') from prefix."""
    asset_prefixes = config["structure"]["asset_prefixes"]
    library_prefixes = config["structure"]["library_prefixes"]
    if prefix in asset_prefixes:
        return "assets"
    if prefix in library_prefixes:
        return "library"
    raise PipelineError(f"Unknown prefix: {prefix}")


def type_by_folder(filepath: str, project_root: str) -> str:
    """Determine file type based on its folder (asset, library, shot)."""
    rel = Path(filepath).relative_to(project_root)
    top_folder = rel.parts[0] if rel.parts else ""
    return {
        "assets": "asset",
        "library": "library",
        "shots": "shot",
    }.get(top_folder, "other")


def file_in_active_project(filepath: str, project_root: str | None = None) -> bool:
    """True if filepath resolves inside project_path. Case-insensitive via a
    plain .lower() on both resolved strings -- os.path.normcase() is a no-op
    on POSIX (macOS included), so it wouldn't actually protect against a
    casing mismatch there despite its name."""
    if project_root is None:
        project_root = get_active_project_root()
    if not filepath or not project_root:
        return False
    try:
        fp = Path(filepath).resolve()
        pp = Path(project_root).resolve()
    except OSError:
        return False
    return str(fp).lower().startswith(str(pp).lower())


def find_known_project_for_file(filepath: str, opened_projects) -> str | None:
    """Search opened_projects (PipelineProjectItem collection) for the project
    that owns filepath, via find_project_root(). Returns the matching
    project's stored path, or None if filepath belongs to no known project."""
    root = find_project_root(filepath)
    if not root:
        return None
    try:
        root_str = str(root.resolve()).lower()
    except OSError:
        return None
    for item in opened_projects:
        try:
            item_str = str(Path(item.path).resolve()).lower()
        except OSError:
            continue
        if item_str == root_str:
            return item.path
    return None


def find_project_root(start_path: str) -> Path | None:
    """Walk up directory tree to find a project_config.json."""
    current = Path(start_path)
    if current.is_file():
        current = current.parent
    for _ in range(10):
        if (current / "config" / "project_config.json").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None


def to_relative(path: str | Path, project_root: Path | None = None) -> str:
    """Path stored in a shared JSON file - always relative to the project, always ending with a slash.
    This is what allows a job_*.json or worker_*.json file to be interpreted the same way,
    regardless of whether the machine that wrote it mounts the NAS via Y:, /mnt/nas, ou \\\\ip\\share."""
    if not project_root:
        project_root = get_active_project_root()

    p = Path(path)
    try:
        rel = p.relative_to(project_root)
    except ValueError:
        rel = p  # already relative, or outside the project -- left as-is
    return rel.as_posix()


def to_absolute(rel_path: str, project_root: Path | None = None) -> Path:
    """Local resolution - each machine reconstructs the absolute path
    based on ITS OWN view of the project_root."""
    if not project_root:
        project_root = get_active_project_root()

    return (
        Path(project_root / str(rel_path)).resolve()
        if not Path(rel_path).is_absolute()
        else Path(rel_path)
    )
