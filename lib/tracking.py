"""Per-asset tracking: notes/todos, wip/stable meta history, department status."""

import hashlib
import json
import os
import queue
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import bpy

from .actions import PipelineAction, set_pending_action
from .config import (
    ConfigCache,
    file_in_active_project,
    get_active_project_root,
    get_base_filename,
    parse_filename,
    prefix_to_parent_folder,
    shots_in_segment,
    to_absolute,
    to_relative,
)
from .core import (
    SCANDIR_TTL,
    cached_scandir,
    get_machine_id,
    json_get,
    locked_json,
    now,
    read_json_quiet,
    resolve_bpy_path,
)
from .errors import PipelineError
from .logs import log
from .session import get_user
from .versioning import get_version_number


def _meta_stem(filepath: Path) -> str:
    """Short .pipeline/ sidecar stem for filepath -- "v004" or "v004-stable",
    version+tag only, since the base name is already implied by the parent
    folder (dropping it keeps sidecar paths short on deep multishot blocks,
    see NOTES.md §6). Falls back to the full stem for a non-conforming
    filepath (e.g. hand-renamed outside the addon)."""
    parsed = parse_filename(filepath.name)
    if not parsed:
        return filepath.stem
    v_prefix = json_get(ConfigCache.get(), "naming.version.prefix", "v")
    stem = f"{v_prefix}{parsed['number']}"
    return f"{stem}-{parsed['tag']}" if parsed.get("tag") else stem


# Top-level folders that can hold tracked assets/shots -- never renders/
# (every rendered frame, by far the slowest subtree to walk) or config/.
_DATA_ROOTS = ("assets", "library", "shots")


# Depth below assets/, library/ or shots/ at which a folder can be an asset
# or a shot: <prefix>/<asset> and <sequence>/<shot> are depth 2 (an archived
# block, <sequence>/old/<shot>, is 3). Depth 0-1 -- the top folder itself, a
# prefix or a sequence folder -- is never one, even with a .pipeline/ in it.
_MIN_OWNER_DEPTH = 2


def _is_tracked_owner(
    folder: Path, entries: list, depth: int = _MIN_OWNER_DEPTH
) -> bool:
    """Whether a folder (given its own listing) is a tracked asset/shot: deep
    enough, and a .pipeline/ *with a tracking.json in it* -- a stray, empty
    .pipeline/ doesn't count (see NOTES.md, "Project walk"). Thread-safe
    (pure os)."""
    if depth < _MIN_OWNER_DEPTH:
        return False
    if not any(e.name == ".pipeline" and e.is_dir() for e in entries):
        return False
    try:
        os.stat(folder / ".pipeline" / "tracking.json")
        return True
    except OSError:
        return False


def _walk_owner_dirs(folder: Path, depth: int = 0):
    """Yield every tracked folder under `folder` (see _is_tracked_owner()),
    in name order, without descending into one: one listing per folder
    visited, never into an asset's textures/caches. Thread-safe (pure os)."""
    try:
        entries = sorted(os.scandir(folder), key=lambda e: e.name)
    except OSError:
        return
    if _is_tracked_owner(folder, entries, depth):
        yield folder
        return
    for e in entries:
        if e.is_dir() and not e.name.startswith("."):
            yield from _walk_owner_dirs(Path(e.path), depth + 1)


def _meta_path(filepath: Path, suffix: str) -> Path:
    """<folder>/.pipeline/<version stem><suffix> for a versioned .blend.
    Raises PipelineError for anything else: given a folder, .parent would be
    the prefix folder (see NOTES.md, "Project walk")."""
    filepath = Path(filepath)
    if filepath.suffix.lower() != ".blend":
        raise PipelineError(f"Expected a .blend file, got {filepath}")
    return filepath.parent / ".pipeline" / (_meta_stem(filepath) + suffix)


def _owner_dir(filepath: Path) -> Path:
    """The asset/shot folder owning filepath: its parent for a .blend, the
    path itself for a folder. Decided from the name (no disk call)."""
    return filepath.parent if filepath.suffix.lower() == ".blend" else filepath


def tracking_json_path(filepath: Path | str, must_exist: bool = False) -> Path:
    """.pipeline/tracking.json of the asset/shot owning filepath (a .blend
    or its folder, see _owner_dir()). must_exist (every writer but
    create_tracking()): raise PipelineError rather than create a tracking.json
    where there was none -- see NOTES.md, "tracking.json: one path, never
    created by a write"."""
    path = _owner_dir(Path(filepath)) / ".pipeline" / "tracking.json"
    if must_exist and not path.is_file():
        raise PipelineError(f"Tracking file not found: {path}")
    return path


def _is_under(key: str, project_root: Path | str) -> bool:
    """Whether cache key `key` (a folder path) lies inside project_root --
    a plain prefix test would also match a sibling "<root>2" project."""
    root = str(project_root).rstrip("/\\")
    return key.startswith(root) and key[len(root) : len(root) + 1] in ("/", "\\")


class TrackingStatusCache:
    """Cache of computed department/tracking status per asset folder, invalidated
    when .pipeline/ (or its tracking.json) changes on disk."""

    _cache: dict[str, tuple[float, dict]] = {}
    # Last time (time.monotonic()) a given filepath argument was re-checked
    # against disk, and the cache key it maps to.
    _validated_at: dict[str, float] = {}
    _key_of: dict[str, str] = {}
    # get() is called several times per redraw: within this window it
    # doesn't re-stat at all (see NOTES.md, "Sidebar redraw").
    _VALIDATE_TTL = 2.0

    @classmethod
    def get(cls, filepath: str, force_reload: bool = False) -> dict:
        """Return the tracking status dict for the asset owning filepath, or
        {} if it can't be computed (missing tracking.json, locked file...).
        Never raises: read by draw()/enum-items callbacks on every redraw,
        with no way to catch or report an error."""
        checked_at = time.monotonic()
        if not force_reload:
            last_checked = cls._validated_at.get(filepath)
            if (
                last_checked is not None
                and checked_at - last_checked < cls._VALIDATE_TTL
            ):
                key = cls._key_of.get(filepath)
                if key in cls._cache:
                    return cls._cache[key][1]

        fp = Path(filepath)
        # Normalize the key to the asset folder, consistent whether we're
        # passed a .blend file or the folder directly
        key = str(_owner_dir(fp))
        mtime = cls._pipeline_mtime(fp)
        cls._validated_at[filepath] = checked_at
        cls._key_of[filepath] = key

        if not force_reload and key in cls._cache and cls._cache[key][0] == mtime:
            return cls._cache[key][1]

        try:
            status = cls._scan_and_compute(fp)
        except PipelineError as e:
            log("WARNING", "tracking", f"Could not compute tracking for {fp}: {e}")
            status = {}
        cls._cache[key] = (mtime, status)
        return status

    @staticmethod
    def _scan_and_compute(filepath: Path) -> dict:
        """Read tracking.json and derive worked/validated departments since
        the last stable (_collect_folder() + _status_from_raw())."""
        asset_dir = _owner_dir(Path(filepath))
        wip_stem = (
            _meta_stem(Path(filepath))
            if Path(filepath).suffix.lower() == ".blend"
            else None
        )
        raw = _collect_folder(asset_dir, wip_stem=wip_stem)
        if raw is None:
            raise PipelineError(
                f"Tracking file not found: {asset_dir / '.pipeline' / 'tracking.json'}"
            )
        return _status_from_raw(raw)

    @staticmethod
    def _pipeline_mtime(filepath: Path) -> float:
        """Latest mtime of .pipeline/ and its tracking.json, used as the cache
        key. Two stats, no exists() first -- a missing one just counts as 0:
        each disk call is a network round-trip on a share."""
        pipeline_dir = _owner_dir(filepath) / ".pipeline"
        mtimes = [0.0]
        for path in (pipeline_dir, pipeline_dir / "tracking.json"):
            try:
                mtimes.append(os.stat(path).st_mtime)
            except OSError:
                pass
        return max(mtimes)

    @classmethod
    def known(cls, project_root: Path) -> list[tuple[str, dict]]:
        """(asset_dir, status) for every non-archived folder cached under
        project_root -- memory only, for draw(). ProjectScan fills it."""
        return [
            (key, data)
            for key, (_, data) in cls._cache.items()
            if _is_under(key, project_root) and not data.get("archived")
        ]


class ProjectScan:
    """Background refresh of the whole project for Project monitoring: every
    tracked folder's status, and the linked-by index. A reader thread does
    the disk work (pure os/json); a main-thread timer applies its results to
    the caches. Folders whose .pipeline/ is unchanged since last cached cost
    two stats, nothing read. See NOTES.md, "Popups on a network share"."""

    done = True
    owners_found = 0
    statuses_done = 0
    phase = ""
    _root: str | None = None
    _thread = None
    _queue = None
    _owners: list = []

    @classmethod
    def start(cls, project_root: Path) -> None:
        """Start a scan of project_root -- no-op if one for the same project
        is already running."""
        if (
            cls._thread is not None
            and cls._thread.is_alive()
            and cls._root == str(project_root)
        ):
            return
        cls._root = str(project_root)
        cls._queue = queue.SimpleQueue()
        cls._owners = []
        cls.done = False
        cls.owners_found = cls.statuses_done = 0
        cls.phase = "walk"
        # Snapshots for the thread: it compares, never mutates shared state.
        known = {k: v[0] for k, v in TrackingStatusCache._cache.items()}
        links = {k: v[0] for k, v in _linker_targets.items()}
        cls._thread = threading.Thread(
            target=cls._read_project,
            args=(Path(project_root), known, links, cls._queue),
            daemon=True,
            name="pipeline-project-scan",
        )
        cls._thread.start()
        if not bpy.app.timers.is_registered(cls._tick):
            bpy.app.timers.register(cls._tick, first_interval=0.1)

    @staticmethod
    def _read_project(root: Path, known: dict, links: dict, out) -> None:
        """Reader thread: disk work only, results posted to `out`."""
        try:
            owners = []
            for top in _DATA_ROOTS:
                for owner in _walk_owner_dirs(root / top):
                    owners.append(owner)
                    out.put(("found", len(owners)))
            out.put(("owners", owners))

            for owner in owners:
                key = str(owner)
                pipeline_dir = owner / ".pipeline"
                try:
                    dir_mtime = os.stat(pipeline_dir).st_mtime
                except OSError:
                    out.put(("skip", key))
                    continue
                try:
                    tracking_mtime = os.stat(pipeline_dir / "tracking.json").st_mtime
                except OSError:
                    tracking_mtime = None
                status_mtime = (
                    None if tracking_mtime is None else max(dir_mtime, tracking_mtime)
                )
                need_status = (
                    tracking_mtime is not None and known.get(key) != status_mtime
                )
                need_links = links.get(key) != dir_mtime
                entries = (
                    _pipeline_entries(owner) if (need_status or need_links) else []
                )
                raw = _collect_folder(owner, entries) if need_status else None
                targets = (
                    _read_link_targets(owner, root, entries) if need_links else None
                )
                out.put(
                    (
                        "folder",
                        key,
                        status_mtime,
                        raw,
                        tracking_mtime is not None,
                        dir_mtime,
                        targets,
                    )
                )
            out.put(("done",))
        except Exception as e:  # never die silently: the tick reports it
            out.put(("error", repr(e)))

    @classmethod
    def _tick(cls):
        """Main thread: apply what the reader thread posted (memory only).
        Never redraws the popup: holding its region across ticks crashes
        Blender once it's closed (see NOTES.md, "Project walk")."""
        global _linked_by_index, _linked_by_project
        if cls._queue is None:
            return None

        deadline = time.monotonic() + 0.01
        finished = False
        while time.monotonic() < deadline:
            try:
                msg = cls._queue.get_nowait()
            except queue.Empty:
                break
            kind = msg[0]
            if kind == "found":
                cls.owners_found = msg[1]
            elif kind == "owners":
                cls._owners = msg[1]
                cls.owners_found = len(msg[1])
                cls.phase = "status"
            elif kind == "folder":
                _, key, status_mtime, raw, tracked, dir_mtime, targets = msg
                if raw is not None:
                    try:
                        TrackingStatusCache._cache[key] = (
                            status_mtime,
                            _status_from_raw(raw),
                        )
                    except Exception as e:
                        log(
                            "WARNING",
                            "tracking",
                            f"Could not compute tracking for {key}: {e}",
                        )
                elif not tracked:
                    TrackingStatusCache._cache.pop(key, None)
                if targets is not None:
                    _linker_targets[key] = (dir_mtime, targets)
                cls.statuses_done += 1
            elif kind == "skip":
                cls.statuses_done += 1
            elif kind in ("done", "error"):
                if kind == "error":
                    log("WARNING", "tracking", f"Project scan stopped: {msg[1]}")
                finished = True
                break

        if finished:
            root = cls._root or ""
            owner_keys = {str(o) for o in cls._owners}
            if owner_keys:
                # Folders gone since an earlier scan of this project.
                for key in [
                    k
                    for k in TrackingStatusCache._cache
                    if _is_under(k, root) and k not in owner_keys
                ]:
                    del TrackingStatusCache._cache[key]
            index: dict[str, set[str]] = {}
            for key in owner_keys:
                for target in _linker_targets.get(key, (None, set()))[1]:
                    index.setdefault(target, set()).add(key)
            _linked_by_index = index
            _linked_by_project = root
            cls.done = True
            cls.phase = ""
            cls._queue = None

        return None if finished else 0.1


class WorkTimeCache:
    """Total logged work time (session_end duration, everyone summed) per
    asset/shot folder -- total only, never per-person (see design.md).
    Rebuilt in one pass over sessions_log.jsonl on its mtime change."""

    _cache: dict[str, float] = {}
    _mtime: float = -1.0
    # Archives (sessions_log_*.jsonl) are rotated out once and never touched
    # again (see NOTES.md, "Rotation trigger") -- cached separately, keyed on
    # which archive files exist, so a session_end (which only ever changes
    # the *current* log) doesn't force a full re-read of every past archive
    # too, just because they share get()'s own invalidation signal.
    _archives_cache: dict[str, float] = {}
    _archives_signature: frozenset[str] | None = None

    _checked_at: float = -1e9

    @classmethod
    def get(cls, folder) -> float:
        """Total seconds for folder, across every version and everyone --
        live log plus rotated archives/sessions_log_*.jsonl (see NOTES.md).
        0.0 if unreadable. Never raises: read by draw()."""
        now_t = time.monotonic()
        if now_t - cls._checked_at < SCANDIR_TTL:
            # Read by draw() on every redraw: re-stat the log at most every
            # SCANDIR_TTL (a network round-trip each on a share).
            return cls._cache.get(str(Path(folder)), 0.0)
        cls._checked_at = now_t
        log_path = ConfigCache.get_path("sessions_log_file")
        try:
            mtime = log_path.stat().st_mtime
        except OSError:
            mtime = -1.0  # still worth checking archives, not just 0.0
        if mtime != cls._mtime:
            archive_paths = list(
                ConfigCache.get_path("logs_archives").glob("sessions_log_*.jsonl")
            )
            signature = frozenset(p.name for p in archive_paths)
            if signature != cls._archives_signature:
                cls._archives_cache = cls._scan(archive_paths)
                cls._archives_signature = signature
            current = cls._scan([log_path])
            cls._cache = {
                k: cls._archives_cache.get(k, 0.0) + current.get(k, 0.0)
                for k in cls._archives_cache.keys() | current.keys()
            }
            cls._mtime = mtime
        return cls._cache.get(str(Path(folder)), 0.0)

    @staticmethod
    def _scan(log_paths) -> dict[str, float]:
        """Sum session_end duration_seconds per folder (Path(filepath).parent)
        across every given log file. Missing/unreadable files are skipped."""
        totals: dict[str, float] = {}
        for log_path in log_paths:
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if entry.get("action") != "session_end":
                            continue
                        fp = entry.get("filepath")
                        duration = entry.get("duration_seconds")
                        if not fp or duration is None:
                            continue
                        key = str(Path(fp).parent)
                        totals[key] = totals.get(key, 0.0) + duration
            except OSError:
                continue
        return totals


class RecentFilesCache:
    """Last few files opened by *this user*, one per asset/shot -- derived
    from sessions_log.jsonl's own session_end lines, filtered to this
    session's own user so someone working shots only never sees a
    teammate's asset opens (no department logic needed: it falls out of
    filtering by who actually opened what). The currently open file is
    never in it (its own session_end isn't logged yet)."""

    _cache: list[tuple[str, str]] = []
    _mtime: float = -1.0

    @classmethod
    def get(cls, limit: int = 3) -> list[tuple[str, str]]:
        """(display name, filepath) pairs, most recent first. [] if
        nothing logged yet or the log can't be read. Never raises: read by
        draw()."""
        log_path = ConfigCache.get_path("sessions_log_file")
        try:
            mtime = log_path.stat().st_mtime
        except OSError:
            return []
        if mtime != cls._mtime:
            cls._cache = cls._scan(log_path, get_user().lower())
            cls._mtime = mtime
        return cls._cache[:limit]

    @staticmethod
    def _scan(log_path: Path, user: str) -> list[tuple[str, str]]:
        """Most recent session_end per folder for user, newest first."""
        latest: dict[str, tuple[str, str]] = {}  # folder -> (ts, filepath)
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (
                        entry.get("action") != "session_end"
                        or entry.get("user") != user
                    ):
                        continue
                    fp = entry.get("filepath")
                    ts = entry.get("ts")
                    if not fp or not ts:
                        continue
                    folder = str(Path(fp).parent)
                    if folder not in latest or ts > latest[folder][0]:
                        latest[folder] = (ts, fp)
        except OSError:
            pass
        ordered = sorted(latest.values(), key=lambda x: x[0], reverse=True)
        return [(Path(fp).stem, fp) for _, fp in ordered]


def format_duration(seconds: float) -> str:
    """Seconds -> compact "XhYY" for display ("Xd YYhZZ" past a day)."""
    total_minutes = int(seconds // 60)
    days, rem_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(rem_minutes, 60)
    if days:
        return f"{days}d {hours:02d}h{minutes:02d}"
    return f"{hours}h{minutes:02d}"


def create_tracking(filepath: Path, departments: list, description: str = ""):
    """Init or update .pipeline/tracking.json for filepath's asset/shot
    folder. Safe to call again on one that already has one (e.g. adding a
    version): entries/departments_required are preserved, description is
    appended (not duplicated) rather than overwritten."""
    if Path(filepath).suffix.lower() != ".blend":
        raise PipelineError(f"Expected a .blend file, got {filepath}")
    try:
        path = tracking_json_path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        name = get_base_filename(filepath.name)

        with locked_json(path) as box:
            existing = box["data"] or {}
            merged_departments = sorted(
                set(existing.get("departments_required", [])) | set(departments)
            )
            existing_description = existing.get("description", "")
            if description and description not in existing_description:
                new_description = (
                    f"{existing_description}\n{description}"
                    if existing_description
                    else description
                )
            else:
                new_description = existing_description

            box["data"] = {
                "file_name": name,
                "created_at": existing.get("created_at", now()),
                "departments_required": merged_departments,
                "description": new_description,
                "entries": existing.get("entries", []),
            }
            box["action"] = "to_write"
    except Exception as e:
        raise PipelineError(f"Error during initializing file entries : {e}")


def get_departments_required(filepath: Path) -> list:
    """Return required departments stored in .pipeline/tracking.json."""
    try:
        path = tracking_json_path(filepath)
        with locked_json(path, read_only=True) as box:
            data = box["data"] or {}
        return data.get("departments_required")
    except Exception as e:
        raise PipelineError(f"Error during reading tracking file : {e}")


def get_last_wipmeta(filepath: Path) -> dict | None:
    """Return last wipmeta file content of the pointing asset folder."""
    path = _owner_dir(Path(filepath)) / ".pipeline"
    wipmetas = []
    for p in path.glob("*.wipmeta"):
        try:
            with locked_json(p, read_only=True) as box:
                data = box["data"]
                if data:
                    wipmetas.append(data)
        except PipelineError:
            continue

    if wipmetas:
        stables = sorted(wipmetas, key=lambda x: x["created_at"], reverse=True)
        return stables[0]
    else:
        return None


def create_wipmeta(
    *, filepath: Path, original_filepath: Path | None, creation_mode: str = ""
):
    """Create the .wipmeta for a new work version, inheriting linked libs
    from the previous one. creation_mode: auto_increment | manual_incrementation
    | branch_from | creation. Keyword-only: filepath/original_filepath are
    both Path, a positional call risks silently swapping them."""

    try:
        last = get_last_wipmeta(filepath)
        nw = now()
        data = {
            "file": str(to_relative(filepath)),
            "created_from": str(to_relative(original_filepath))
            if original_filepath
            else None,
            "creation_mode": creation_mode,
            "created_at": nw,
            "edited_at": nw,
            "edited_by": get_user(),
            "departments_worked": {},
            "linked": (last or {}).get("linked", []),
        }
        path = _meta_path(filepath, ".wipmeta")
        path.parent.mkdir(parents=True, exist_ok=True)
        with locked_json(path) as box:
            box["data"] = data
            box["action"] = "to_write"
    except Exception as e:
        raise PipelineError(f"Error during creating meta file : {e}")


def wipmeta_touch(filepath: Path):
    """Stamp this version's .wipmeta with who/when it was last saved --
    edited_at/edited_by only, doesn't touch departments_worked or linked.
    Called from save_post_handler on every save, so M_PIPELINE_OT_auto_version
    can tell a same-day re-open by a different user from the file's own
    author. Never raises: handler-called, same rule as check_library_update()."""
    path = _meta_path(filepath, ".wipmeta")
    if not path.exists():
        return
    try:
        with locked_json(path) as box:
            data = box["data"] or {}
            data["edited_at"] = now()
            data["edited_by"] = get_user()
            box["action"] = "to_write"
    except Exception as e:
        log("WARNING", "wipmeta_touch", f"Could not stamp wipmeta: {e}")


_session_worked_cache: dict[str, list[str]] = {}


def wipmeta_add_work(
    filepath: Path, departments: list[str] = [], linked_libs: list[str] | None = None
):
    """Record, in this version's .wipmeta, which departments were worked
    this session, and resync linked-libs against the file's actual links.
    linked_libs: pass a pre-captured list when filepath's file is already
    closed (bpy.data no longer refers to it). No-op, doesn't raise, if
    filepath has no .wipmeta -- a -stable file has none by design (only a
    .stablemeta), and there's nothing to track on it; same rule as
    wipmeta_touch()."""
    id = f"{os.getpid()}_{get_machine_id()}"
    path = _meta_path(filepath, ".wipmeta")
    if not path.exists():
        return
    else:
        if linked_libs is None:
            linked_libs = [
                to_relative(resolve_bpy_path(lib.filepath))
                for lib in bpy.data.libraries
            ]
        with locked_json(path) as box:
            data = box["data"] or {}
            data["edited_at"] = now()
            data["edited_by"] = get_user()
            data["departments_worked"][id] = departments
            data["linked"] = clean_libraries(data["linked"], linked_libs)
            box["action"] = "to_write"
        # Kept in sync here rather than invalidated: this is the only writer
        # of our own session's entry, so the cache can never go stale under it.
        _session_worked_cache[str(path)] = list(departments)


def get_session_worked_departments(filepath: Path) -> list[str]:
    """Departments already recorded for *this* session (pid + machine) in
    filepath's .wipmeta. In-memory cache kept in sync by wipmeta_add_work(),
    so draw() never hits disk past the first read. [] by default -- an
    untouched file never claims work that wasn't done. Read by draw():
    never raises -- [] for anything that isn't a versioned .blend."""
    try:
        path = _meta_path(filepath, ".wipmeta")
    except PipelineError:
        return []
    key = str(path)
    if key in _session_worked_cache:
        return _session_worked_cache[key]
    id = f"{os.getpid()}_{get_machine_id()}"
    try:
        with locked_json(path, read_only=True) as box:
            data = box["data"] or {}
        result = list(data.get("departments_worked", {}).get(id, []))
    except Exception:
        result = []
    _session_worked_cache[key] = result
    return result


def wipmeta_add_link(filepath: Path, link: list[dict]):
    """Append freshly linked libraries to this version's .wipmeta linked
    list, deduped by (file, type, name) -- see NOTES.md. No-op, doesn't
    raise, if filepath has no .wipmeta -- linking into an open -stable file
    is legal (Blender doesn't block it in memory, only Save is guarded),
    and a -stable file has nothing to track it in; same rule as
    wipmeta_touch()."""
    path = _meta_path(filepath, ".wipmeta")
    if not path.exists():
        return
    else:
        with locked_json(path) as box:
            data = box["data"] or {}
            seen = set()
            deduped = []
            for d in data.get("linked", []) + link:
                key = (d.get("file"), d.get("type"), d.get("name"))
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(d)
            data["linked"] = deduped
            box["action"] = "to_write"


def wipmeta_sync_links(filepath: Path, links: list[dict]) -> int:
    """Add to this version's .wipmeta linked list every entry of links
    ({file, type, name}, see scan_linked_libraries()) it doesn't already
    have. For links that never went through an import event: a file
    migrated from outside the pipeline, a library repointed by hand or by a
    script... Add-only (removal stays clean_libraries()'s job), and writes
    nothing when there's nothing new, so it's cheap to call on every
    load/save. Compared on the resolved path, like find_linked_by(): an old
    entry's un-collapsed "../" must not read as a new link. Returns the
    number of entries added; 0, no raise, without a .wipmeta (-stable
    file), same rule as wipmeta_touch()."""
    path = _meta_path(filepath, ".wipmeta")
    if not path.exists():
        return 0

    def key(d):
        return (str(to_absolute(d["file"])), d.get("type"), d.get("name"))

    with locked_json(path) as box:
        data = box["data"] or {}
        current = data.get("linked", [])
        known = {key(d) for d in current if d.get("file")}
        new = []
        for d in links:
            if d.get("file") and key(d) not in known:
                known.add(key(d))
                new.append(d)
        if new:
            data["linked"] = current + new
            box["data"] = data
            box["action"] = "to_write"
    return len(new)


def create_stablemeta(
    *,
    filepath: Path,
    original_filepath: Path,
    departments: list[str],
    conflict_warnings: str,
):
    """Create the .stablemeta for a -stable version: validated departments,
    inherited linked libs, any conflict warning. Keyword-only: filepath/
    original_filepath are both Path, a positional call risks swapping them."""
    try:
        original_suffix = (
            ".stablemeta" if "-stable.blend" in original_filepath.name else ".wipmeta"
        )
        with locked_json(
            _meta_path(original_filepath, original_suffix), read_only=True
        ) as box:
            wipdata = box["data"]

        nw = now()
        data = {
            "file": str(to_relative(filepath)),
            "created_from": str(to_relative(original_filepath)),
            "created_at": nw,
            "departments_validated": {
                d: d in departments for d in get_departments_required(filepath)
            },
            "linked": (wipdata or {}).get("linked", []),
            "conflict_warning": conflict_warnings,
        }
        path = _meta_path(filepath, ".stablemeta")
        path.parent.mkdir(parents=True, exist_ok=True)

        with locked_json(path) as box:
            box["data"] = data
            box["action"] = "to_write"
    except Exception as e:
        raise PipelineError(f"Error during creating meta file : {e}")


def set_department_validated(filepath: Path, department: str, validated: bool) -> None:
    """Toggle one department's validated status directly (e.g. "render",
    not tied to file content), mutating the *latest* .stablemeta in place.
    Raises PipelineError if the asset has no stable version yet -- nothing
    to mutate until create_stablemeta() has run at least once."""
    asset_dir = _owner_dir(Path(filepath))
    last = get_last_stable(asset_dir)
    if "file" not in last:
        raise PipelineError(
            "Mark at least one version as stable before validating individual departments."
        )
    path = asset_dir / ".pipeline" / (_meta_stem(Path(last["file"])) + ".stablemeta")
    with locked_json(path) as box:
        data = box["data"] or {}
        data.setdefault("departments_validated", {})[department] = validated
        box["action"] = "to_write"


# Margin when comparing a file's mtime (stamped by the file server or the
# writing machine) with a date stored inside a meta (the writer's clock, see
# now()): only used to *skip* reading files, so it errs on reading one too
# many -- clocks a few minutes apart still give exact results.
_CLOCK_MARGIN_SECONDS = 600


def _pipeline_entries(owner: Path) -> list:
    """os.DirEntry list of owner/.pipeline/ -- one listing; on Windows each
    entry's stat() comes with it, no extra round-trip."""
    try:
        return list(os.scandir(owner / ".pipeline"))
    except OSError:
        return []


def _entry_mtime(entry) -> datetime:
    try:
        return datetime.fromtimestamp(entry.stat().st_mtime)
    except (OSError, ValueError, OverflowError):
        return datetime.max  # unknown: never skipped


_DEFAULT_STABLE = {
    "created_at": datetime.min.isoformat(),
    "departments_validated": {},
    "conflict_warning": False,
}


def _latest_stable(entries: list) -> dict | None:
    """Latest (by created_at) stablemeta among a .pipeline/ listing, or None.
    Reads newest-first by file mtime and stops as soon as the remaining files
    are all older than the best created_at found (a meta's created_at can't
    be later than its own file's mtime) -- usually one read instead of one
    per stable version ever made. Thread-safe (see read_json_quiet())."""
    stables = sorted(
        (e for e in entries if e.name.endswith(".stablemeta")),
        key=_entry_mtime,
        reverse=True,
    )
    best = None
    best_date = None
    for entry in stables:
        if best_date is not None and _entry_mtime(entry) < best_date - timedelta(
            seconds=_CLOCK_MARGIN_SECONDS
        ):
            break
        data = read_json_quiet(Path(entry.path))
        if not data:
            continue
        try:
            created = datetime.fromisoformat(data["created_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if best_date is None or created > best_date:
            best, best_date = data, created
    return best


def get_last_stable(filepath: Path, entries: list | None = None) -> dict:
    """Return the latest (by created_at) stablemeta of the owning folder, or
    a default "no stable yet" dict -- see _latest_stable()."""
    if entries is None:
        entries = _pipeline_entries(_owner_dir(Path(filepath)))
    return _latest_stable(entries) or dict(_DEFAULT_STABLE)


def _collect_folder(
    asset_dir: Path, entries: list | None = None, wip_stem: str | None = None
) -> dict | None:
    """Everything a folder's tracking status is computed from, read from
    disk: tracking.json, the latest stable, and only the wipmetas that can
    matter (changed after that stable -- the others are skipped by file
    mtime, never opened). None if there's no readable tracking.json.
    Thread-safe (see read_json_quiet()); wip_stem restricts to one version's
    wipmeta (TrackingStatusCache.get() on a .blend)."""
    tracking = read_json_quiet(asset_dir / ".pipeline" / "tracking.json")
    if tracking is None:
        return None
    if entries is None:
        entries = _pipeline_entries(asset_dir)
    last_stable = _latest_stable(entries) or dict(_DEFAULT_STABLE)
    try:
        stable_date = datetime.fromisoformat(last_stable.get("created_at") or "")
    except ValueError:
        stable_date = datetime.min
    if wip_stem is not None:
        wip = read_json_quiet(asset_dir / ".pipeline" / f"{wip_stem}.wipmeta")
        wipmetas = [wip or {}]
    else:
        skip_before = (
            stable_date - timedelta(seconds=_CLOCK_MARGIN_SECONDS)
            if stable_date > datetime.min + timedelta(seconds=_CLOCK_MARGIN_SECONDS)
            else datetime.min
        )
        wipmetas = []
        for entry in entries:
            if not entry.name.endswith(".wipmeta") or _entry_mtime(entry) < skip_before:
                continue
            data = read_json_quiet(Path(entry.path))
            if data:
                wipmetas.append(data)
    return {"tracking": tracking, "last_stable": last_stable, "wipmetas": wipmetas}


def _status_from_raw(raw: dict) -> dict:
    """A folder's tracking status from _collect_folder()'s data -- memory
    only, no disk."""
    global_data = raw["tracking"]
    last_stable = raw["last_stable"]
    stable_date_str = last_stable.get("created_at")
    stable_date = (
        datetime.fromisoformat(stable_date_str) if stable_date_str else datetime.min
    )

    # Departments validated at the latest stable
    validated_departments = {
        d: v for d, v in last_stable.get("departments_validated", {}).items() if v
    }

    # Departments worked on since the latest stable
    worked_departments: dict[str, list[dict]] = {}
    for meta in raw["wipmetas"]:
        meta_date_str = meta.get("edited_at", "")
        if not meta_date_str:
            continue
        if datetime.fromisoformat(meta_date_str) <= stable_date:
            continue  # at or before the latest stable, ignored
        # departments_worked : {session_id: [dep1, dep2, ...]}
        for deps_list in meta.get("departments_worked", {}).values():
            for dep in deps_list:
                worked_departments.setdefault(dep, []).append(
                    {"file": meta["file"], "by": meta.get("edited_by")}
                )

    deps_items = [
        (d, d.capitalize(), "", 2**i)
        for i, d in enumerate(global_data.get("departments_required", []))
    ]

    return global_data | {
        "worked_departments": worked_departments,
        "validated_departments": validated_departments,
        "departments_items": deps_items,
        # Computed here (not in draw()) so a UI redraw -- which Blender
        # fires constantly, e.g. on every mouse move over the viewport --
        # never re-groups/re-sorts entries; only a real tracking.json
        # change (this cache's invalidation trigger) does.
        "entries_grouped": group_entries_by_review(global_data.get("entries", [])),
        # Last -stable's own identity, exposed as-is for department_status_tooltip().
        "stable_info": {
            "file": last_stable.get("file"),
            "created_at": last_stable.get("created_at"),
        },
    }


def get_current_departments(filepath: Path) -> dict:
    """Return {department: validated_since_last_stable} for the owning asset."""
    data = TrackingStatusCache.get(filepath=str(filepath))
    if data:
        return data.get("validated_departments", {})
    else:
        return {}


def department_status_tooltip(data: dict, department: str) -> str:
    """Hover text for one department's status cell/toggle, from
    TrackingStatusCache's already-computed worked_departments/
    validated_departments/stable_info. No per-department author or
    timestamp is stored on disk -- toggling "validated" doesn't stamp
    who/when -- so this surfaces the closest real info instead: the stable
    version a department was validated with, and which versions (and who)
    worked it since."""
    validated = department in data.get("validated_departments", {})
    worked = data.get("worked_departments", {}).get(department, [])
    stable = data.get("stable_info") or {}

    if validated:
        stable_name = Path(stable["file"]).stem if stable.get("file") else "unknown"
        stable_date = (stable.get("created_at") or "").replace("T", " ")
        lines = [
            f"Validated as of {stable_name}"
            + (f" ({stable_date})" if stable_date else "")
        ]
    else:
        lines = ["Not validated for the current stable version."]

    if worked:
        lines.append("")
        lines.append("Worked since in:")
        for w in worked:
            by = f" by {w['by']}" if w.get("by") else ""
            lines.append(f"   {Path(w['file']).stem}{by}")

    return "\n".join(lines)


def get_description(filepath: Path) -> str:
    """Return the owning asset/shot's free-text description, or "" if none."""
    return TrackingStatusCache.get(filepath=str(filepath)).get("description", "")


def set_description(filepath: Path, description: str) -> None:
    """Overwrite the owning asset/shot's description outright -- unlike
    create_tracking()'s append-on-recreate behavior, this is a direct edit,
    it replaces whatever text was there."""
    try:
        path = tracking_json_path(filepath, must_exist=True)
        with locked_json(path) as box:
            data = box["data"] or {}
            if not data:
                raise PipelineError(f"Tracking file not found: {path}")
            data["description"] = description
            box["data"] = data
            box["action"] = "to_write"
    except PipelineError:
        raise
    except Exception as e:
        raise PipelineError(f"Error updating description: {e}")


# ---------------------------------------------------------------------------
# Branch
# ---------------------------------------------------------------------------

# Reserved sibling folder name a branched-out block (and a dropped shot's
# renders) gets moved into -- never a real sequence/shot name, so plain
# iteration over a sequence has to skip it explicitly (list_active_blocks()).
ARCHIVE_DIRNAME = "old"


def archive_folder(path: Path) -> Path:
    """Move path into an ARCHIVE_DIRNAME folder next to it, timestamping on
    a name collision. Deliberately not link-safe (see NOTES.md, "Branch")."""
    dest_dir = path.parent / ARCHIVE_DIRNAME
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists():
        stamp = now(iso=False).strftime("%Y%m%d-%H%M%S")
        dest = dest_dir / f"{path.name}_{stamp}"
    try:
        path.rename(dest)
    except OSError as e:
        raise PipelineError(f"Could not archive '{path.name}': {e}")
    return dest


def copy_entries(from_filepath: Path, to_filepath: Path) -> None:
    """Append every entry from from_filepath's tracking.json onto
    to_filepath's, as-is. from_filepath's own entries are untouched."""
    try:
        old_path = tracking_json_path(from_filepath)
        with locked_json(old_path, read_only=True) as box:
            old_entries = (box["data"] or {}).get("entries", [])
        if not old_entries:
            return
        new_path = tracking_json_path(to_filepath, must_exist=True)
        with locked_json(new_path) as box:
            data = box["data"] or {}
            data["entries"] = data.get("entries", []) + old_entries
            box["action"] = "to_write"
    except Exception as e:
        raise PipelineError(f"Error copying entries: {e}")


# tracking.json path -> (mtime or None, archived, last checked -- time.monotonic())
_archived_cache: dict[str, tuple[float | None, bool, float]] = {}


def is_block_archived(shot_dir: Path) -> bool:
    """Whether shot_dir's tracking.json is archived. False if missing or
    unreadable. Cached on tracking.json's own mtime -- list_active_blocks()
    calls this once per shot in a sequence, and Blender re-invokes the enum
    callbacks that walk sequences/shots on every redraw."""
    tracking_file = shot_dir / ".pipeline" / "tracking.json"
    key = str(tracking_file)
    now_t = time.monotonic()
    cached = _archived_cache.get(key)
    # Same TTL as cached_scandir(): within it, no disk call at all -- the
    # mtime check alone was one network round-trip per shot per call.
    if cached and now_t - cached[2] < SCANDIR_TTL:
        return cached[1]
    try:
        mtime = tracking_file.stat().st_mtime
    except OSError:
        _archived_cache[key] = (None, False, now_t)
        return False
    if cached and cached[0] == mtime:
        _archived_cache[key] = (mtime, cached[1], now_t)
        return cached[1]
    try:
        with locked_json(tracking_file, read_only=True, retries=0) as box:
            archived = bool((box["data"] or {}).get("archived"))
    except Exception:
        archived = False
    _archived_cache[key] = (mtime, archived, now_t)
    return archived


def list_active_blocks(
    project_root: Path, sequence_label: str | None = None
) -> list[Path]:
    """Every shot/block folder under shots/ (optionally one sequence) that
    isn't archived."""
    shots_dir = project_root / "shots"
    sequences = (
        [shots_dir / sequence_label]
        if sequence_label
        else sorted(
            (Path(e.path) for e in cached_scandir(shots_dir) if e.is_dir()),
            key=lambda p: p.name,
        )
    )
    out = []
    for sq_dir in sequences:
        # No is_dir() check: a missing folder lists as [] in cached_scandir(),
        # and is_dir() would be one more network call per sequence per call.
        for sh_dir in sorted(
            (Path(e.path) for e in cached_scandir(sq_dir) if e.is_dir()),
            key=lambda p: p.name,
        ):
            if sh_dir.name != ARCHIVE_DIRNAME and not is_block_archived(sh_dir):
                out.append(sh_dir)
    return out


def active_shot_owners(
    project_root: Path, sequence_label: str, config: dict | None = None
) -> dict[int, Path]:
    """{shot_number: owning shot/block folder} for every active file in
    sequence_label -- lets a caller flag a number already claimed
    elsewhere before creating/branching into it."""
    config = config if config is not None else ConfigCache.get()
    shot_prefix = json_get(config, "naming.shot.prefix", "sh")
    owners = {}
    for sh_dir in list_active_blocks(project_root, sequence_label):
        if not sh_dir.name.startswith(shot_prefix):
            continue
        try:
            numbers = shots_in_segment(sh_dir.name[len(shot_prefix) :])
        except ValueError:
            continue
        for n in numbers:
            owners[n] = sh_dir
    return owners


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------


def create_entry(
    filepath: Path,
    *,
    text: str,
    department: str,
    author: str,
    type: str = "note",
    response: str = "",
    frame_reference: str = "abs",
    f_start: int | None = None,
    f_end: int | None = None,
    review_id: str | None = None,
    referenced_version: str | None = None,
    shot: str | None = None,
    created_at: str | None = None,
    source: str | None = None,
):
    """Append a note/todo/rtk entry to the owning asset's tracking.json.
    text/department/author/type are keyword-only: all plain strings, a
    positional call risks silently swapping department and author.
    shot: free-text tag (e.g. "045"), not validated against anything.
    created_at: ISO date to stamp instead of now() (an imported review's
    own date). source: where it came from when not typed in Blender
    ("prod_review"); absent = created by hand."""
    try:
        path = tracking_json_path(filepath, must_exist=True)
        with locked_json(path) as box:
            data = box["data"] or {}

            nw = created_at or now()
            entry = {
                # text folded into the hash (not just nw) so entries created
                # in the same execute() loop -- same nw, different text --
                # don't collide on id.
                "id": hashlib.sha1((nw + text).encode("utf-8")).hexdigest()[:5],
                "type": type,
                "text": text,
                "author": author,
                "created_at": nw,
            }
            if department and department != "NONE":
                entry["department"] = department
            if type in ["todo", "rtk"]:
                entry["done"] = False
            if response:
                entry["response"] = response
            if f_start is not None:
                entry["frame_start"] = f_start
                entry["frame_reference"] = frame_reference
            if f_start is not None and f_end is not None:
                entry["frame_end"] = f_end
            if review_id:
                entry["review_id"] = review_id
            if referenced_version and referenced_version != "NONE":
                entry["referenced_version"] = to_relative(Path(referenced_version))
            if shot:
                entry["shot"] = shot
            if source:
                entry["source"] = source

            data["entries"].append(entry)
            box["action"] = "to_write"
    except Exception as e:
        raise PipelineError(f"Error during editing file entries : {e}")


def edit_entry(
    filepath: Path,
    *,
    text: str,
    department: str,
    editor: str,
    type: str = "note",
    id: str = "",
    frame_reference: str = "abs",
    f_start: int | None = None,
    f_end: int | None = None,
    referenced_version: str | None = None,
    shot: str | None = None,
):
    """Update an existing entry (matched by id) in the owning asset's tracking.json.

    Keyword-only past filepath: text/department/editor are all plain strings,
    a positional call risks silently swapping department and editor.
    editor is stamped as edited_by/edited_at -- unlike create_entry()'s
    author/created_at, it never overwrites who originally wrote the entry
    or when.
    Unlike create_entry(), this replaces the frame/version state outright --
    passing f_start=None clears a previously tagged frame_start/frame_end/
    frame_reference rather than leaving the old values in place."""
    try:
        path = tracking_json_path(filepath, must_exist=True)
        with locked_json(path) as box:
            data = box["data"] or {}
            entries = data.get("entries")
            for e in entries:
                if e["id"] == id:
                    e.update(
                        {
                            "type": type,
                            "text": text,
                            # author/created_at untouched -- they record who
                            # wrote the entry and when, not who last edited it.
                            "edited_by": editor,
                            "edited_at": now(),
                        }
                    )
                    if type not in ("rtk", "todo"):
                        e.pop("done", None)
                        e.pop("done_by", None)
                        e.pop("done_at", None)

                    else:
                        e["done"] = e.get("done", False)
                    if f_start is not None:
                        e["frame_start"] = f_start
                        e["frame_reference"] = frame_reference
                    else:
                        e.pop("frame_start", None)
                        e.pop("frame_reference", None)
                    if f_start is not None and f_end is not None:
                        e["frame_end"] = f_end
                    else:
                        e.pop("frame_end", None)
                    if referenced_version and referenced_version != "NONE":
                        e["referenced_version"] = to_relative(Path(referenced_version))
                    else:
                        e.pop("referenced_version", None)
                    if department and department != "NONE":
                        e["department"] = department
                    else:
                        e.pop("department", None)
                    if shot:
                        e["shot"] = shot
                    else:
                        e.pop("shot", None)
                    box["action"] = "to_write"
                    break
            else:
                raise PipelineError("No entry found with this ID.")
    except Exception as e:
        raise PipelineError(f"Error during editing file entries : {e}")


def delete_entry(filepath: Path, id: str):
    """Remove an entry (matched by id) from the owning asset's tracking.json,
    along with every reply that (transitively) answers it. Deleting only the
    parent would orphan those replies: response would point at an id that no
    longer exists, so they'd never resolve to any root and would never be
    shown again anyway -- dead data left behind in the JSON forever."""
    try:
        path = tracking_json_path(filepath, must_exist=True)
        with locked_json(path) as box:
            data = box["data"] or {}
            entries = data["entries"]
            if not any(e["id"] == id for e in entries):
                raise PipelineError("No entry found with this ID.")

            to_delete = {id}
            frontier = [id]
            while frontier:
                parent = frontier.pop()
                children = [e["id"] for e in entries if e.get("response") == parent]
                to_delete.update(children)
                frontier.extend(children)

            data["entries"] = [e for e in entries if e["id"] not in to_delete]
            box["action"] = "to_write"
    except PipelineError:
        raise
    except Exception as e:
        raise PipelineError(f"Error during deleting file entries : {e}")


def get_entries(filepath: str) -> list:
    """Return the entries list for the owning asset (via TrackingStatusCache), or []."""
    return TrackingStatusCache.get(filepath).get("entries", [])


def get_entries_grouped(filepath: str) -> list:
    """Return entries grouped into review boxes (see group_entries_by_review),
    via TrackingStatusCache, or []."""
    return TrackingStatusCache.get(filepath).get("entries_grouped", [])


def group_entries_by_review(entries: list) -> list[dict]:
    """Group entries into review boxes for draw_entries():

        [{"review_id": "a1b2c" | None, "threads": [
            {"root": entry, "replies": [entry, ...], "meta": {...}},
            ...
        ]}, ...]

    A thread is a root entry (response is unset) plus every descendant that
    answers it, transitively, flattened and sorted chronologically. Only the
    ROOT's review_id decides which box a thread lands in -- a reply can carry
    its own, different review_id (it was added in a later review session),
    that doesn't move the thread; it only marks where, in the flattened
    replies, a draw-time separator belongs (compare consecutive replies'
    review_id -- different, or None, means "space here").
    A root with no review_id (created outside any multi-entry review) is
    standalone: it gets its own box, never merged with other standalone
    roots just because they all lack a review_id.
    Boxes, and threads within a box, are ordered by most recent activity
    first (root or any reply, whichever is latest) -- a chronological feed,
    newest on top.
    """
    by_parent: dict[str, list[dict]] = {}
    for e in entries:
        parent = e.get("response")
        if parent:
            by_parent.setdefault(parent, []).append(e)

    def descendants(root_id: str) -> list[dict]:
        out = []
        frontier = [root_id]
        while frontier:
            kids = by_parent.get(frontier.pop(), [])
            out.extend(kids)
            frontier.extend(k["id"] for k in kids)
        return sorted(out, key=lambda e: e["created_at"])

    def make_thread(root: dict) -> dict:
        replies = descendants(root["id"])
        return {
            "root": root,
            "replies": replies,
            "meta": _thread_meta([root, *replies]),
        }

    grouped: dict[str, list[dict]] = {}
    boxes: list[dict] = []
    for root in entries:
        if root.get("response"):
            continue  # not a root, it's collected as a descendant above
        review_id = root.get("review_id")
        if review_id:
            grouped.setdefault(review_id, []).append(root)
        else:
            boxes.append({"review_id": None, "threads": [make_thread(root)]})

    for review_id, roots in grouped.items():
        threads = [make_thread(root) for root in roots]
        threads.sort(key=lambda t: t["meta"]["date_end"], reverse=True)
        boxes.append({"review_id": review_id, "threads": threads})

    boxes.sort(
        key=lambda b: max(t["meta"]["date_end"] for t in b["threads"]), reverse=True
    )
    return boxes


def _thread_meta(thread_entries: list[dict]) -> dict:
    """Aggregate root+replies into a thread summary: departments/authors/
    versions/frames as sets, date_start (root) / date_end (last reply, or
    root if none) from the entries' own chronological order."""
    dates = [e["created_at"] for e in thread_entries]
    versions = {
        e["referenced_version"] for e in thread_entries if e.get("referenced_version")
    }
    return {
        "departments": {e["department"] for e in thread_entries if e.get("department")},
        "authors": {e["author"] for e in thread_entries if e.get("author")},
        "versions": versions,
        # Parsed once here, not at filter time: version_numbers backs
        # filter_review_boxes()'s min_version filter.
        "version_numbers": {
            n for n in (get_version_number(v) for v in versions) if n is not None
        },
        "frames": {
            (e["frame_start"], e.get("frame_end"))
            for e in thread_entries
            if e.get("frame_start") is not None
        },
        "date_start": min(dates),
        "date_end": max(dates),
    }


def filter_review_boxes(
    review_boxes: list[dict],
    *,
    hide_done: bool = False,
    department: str = "NONE",
    min_version: int = 0,
) -> list[dict]:
    """Filter review boxes (as returned by group_entries_by_review) for
    draw_entries(). Filtering is per-THREAD -- a whole thread is kept if it
    matches, so replies are never orphaned by their root getting filtered
    out:
      - hide_done: drops threads whose ROOT is done AND that have no
        still-pending reply (a reply with done is False). A done root with
        an unresolved todo/rtk reply stays visible -- otherwise that reply
        would vanish along with the parent, silently losing track of it.
      - department: keeps a thread with no department-tagged entry at all
        (a general note, always shown) or where `department` is among its
        meta departments. "NONE" means no filter.
      - min_version: keeps a thread that references no version at all
        (nothing to compare, always shown) or whose highest referenced
        version is >= min_version. 0 means no filter.
    Drops boxes left with zero threads. Pure: never mutates review_boxes or
    anything inside them -- those come straight out of TrackingStatusCache's
    mtime-cache, shared across every redraw until the file changes; mutating
    in place would corrupt it permanently, even after the filter is reset.
    """

    def keep(thread: dict) -> bool:
        if hide_done and thread["root"].get("done") is True:
            has_pending_reply = any(r.get("done") is False for r in thread["replies"])
            if not has_pending_reply:
                return False
        meta = thread["meta"]
        if (
            department != "NONE"
            and meta["departments"]
            and department not in meta["departments"]
        ):
            return False
        if (
            min_version
            and meta["version_numbers"]
            and max(meta["version_numbers"]) < min_version
        ):
            return False
        return True

    out = []
    for review_box in review_boxes:
        threads = [t for t in review_box["threads"] if keep(t)]
        if threads:
            out.append({**review_box, "threads": threads})
    return out


def toggle_entry_task(filepath: Path, id: str, user: str):
    """Flip a todo/rtk entry (matched by id) between done and not done."""
    try:
        path = tracking_json_path(filepath, must_exist=True)
        with locked_json(path) as box:
            data = box["data"] or {}
            entries = data["entries"]
            for e in entries:
                if e["id"] == id:
                    if e["done"]:
                        e["done"] = False
                        del e["done_by"]
                        del e["done_at"]
                    else:
                        e["done"] = True
                        e["done_by"] = user
                        e["done_at"] = now()
                    box["action"] = "to_write"
                    break
            else:
                raise PipelineError("No entry found with this ID.")
    except Exception as e:
        raise PipelineError(f"Error during editing file entries : {e}")


def mark_render_to_check(
    filepath: Path | str,
    shot: str,
    render_dir: str,
    job_id: str,
    project_root: Path | None = None,
    video: str | None = None,
) -> bool:
    """Flag a finished render as waiting for its artist's check, in the
    owning folder's tracking.json: "to_check" {shot or "": {"render",
    "video", "at", "job_id"}} -- a block keeps one per shot, a newer render
    of the same shot replaces the older. Cleared by hand
    (clear_render_to_check()). Never raises. False: not written, worth
    retrying; a folder without tracking.json is True (nothing to flag)."""
    try:
        path = tracking_json_path(to_absolute(filepath, project_root), must_exist=True)
    except PipelineError as e:
        log("WARNING", "tracking", f"Render of {filepath} not flagged to check: {e}")
        return True
    try:
        with locked_json(path) as box:
            data = box["data"] or {}
            data.setdefault("to_check", {})[shot or ""] = {
                "render": render_dir,
                "video": video,
                "at": now(),
                "job_id": job_id,
            }
            box["data"] = data
            box["action"] = "to_write"
    except Exception as e:
        log("WARNING", "tracking", f"Could not flag the render of {filepath} to check: {e}")
        return False
    return True


def clear_render_to_check(filepath: Path | str, shot: str | None = None) -> list[str]:
    """Mark a render checked: drop shot's "to_check" entry ("" for an asset
    or a mono shot), or every one of the folder's if shot is None. Returns
    the dropped entries' job ids."""
    path = tracking_json_path(filepath, must_exist=True)
    with locked_json(path) as box:
        data = box["data"] or {}
        to_check = data.get("to_check") or {}
        if shot is None:
            dropped = list(to_check.values())
            to_check.clear()
        else:
            dropped = [to_check.pop(shot)] if shot in to_check else []
        if to_check:
            data["to_check"] = to_check
        else:
            data.pop("to_check", None)
        box["data"] = data
        box["action"] = "to_write"
    return [d["job_id"] for d in dropped if isinstance(d, dict) and d.get("job_id")]


def render_to_check_label(shot: str, info: dict) -> str:
    """ "sh040 v002-stable_001" -- the render's output folder, prefixed by
    the shot for a block's."""
    name = re.split(r"[\\/]", (info.get("render") or "").rstrip("\\/"))[-1] or "?"
    return f"{shot} {name}" if shot else name


def find_file_by_name(filename: str) -> Path | None:
    """Resolve a bare pipeline filename to its full path in the project, or None."""
    project_root = get_active_project_root()
    dir = None

    match = ConfigCache.get_asset_regex().match(filename)
    if match:
        parent_folder = prefix_to_parent_folder(match["prefix"], ConfigCache.get())
        dir = (
            project_root
            / parent_folder
            / match["prefix"]
            / f"{match['prefix']}_{match['name']}"
            / filename
        )
    else:
        match = ConfigCache.get_shot_regex().match(filename)
        if match:
            config = ConfigCache.get()
            naming = config.get("naming", {})
            if not naming:
                raise PipelineError("Project config is missing or invalid.")

            sq = f"{json_get(naming, 'sequence.prefix', 'sq')}{match['sequence']}"
            sh = f"{json_get(naming, 'shot.prefix', 'sh')}{match['shot']}"

            dir = project_root / "shots" / sq / sh / filename

    if not dir or not dir.exists():
        return None
    else:
        return dir


def valid_department(filepath: Path, department: str) -> str:
    """Return department if it's required for filepath's asset, else ''."""
    valid = department in get_departments_required(filepath)
    return department if valid else ""


def check_library_update():
    """Detect linked libraries with a newer -stable version and propose
    updating them. Never raises: called from post_load_handler, which has
    no self.report -- a lookup failure is logged and skipped, not blocking."""
    try:
        libs = bpy.data.libraries
        update = []
        for lib in libs:
            abs_path = resolve_bpy_path(lib.filepath)
            if file_in_active_project(str(abs_path)):
                last = get_last_file_stable(abs_path)
                if last and str(last) != str(abs_path):
                    update.append((lib, str(last)))
    except Exception as e:
        log("WARNING", "check_library_update", f"Could not check libraries: {e}")
        return

    if update:
        action = PipelineAction(
            title="New stable version available",
            message="\n".join(
                [
                    f"{Path(old.filepath).stem} -> {Path(new).stem}"
                    for old, new in update
                ]
            ),
            severity="warning",
            choices=[
                ("Not now", lambda: None, "Keep the currently linked versions."),
                (
                    "Update libraries",
                    lambda: library_updates(update),
                    "Repoint and reload the outdated libraries.",
                ),
            ],
            explanation=(
                "A newer validated version of a linked file exists. "
                "Updating pulls the latest. Keeping the current one is "
                "fine too: nothing changes unless you choose to."
            ),
        )
        set_pending_action(action)
        bpy.ops.m_pipeline.action_popup("INVOKE_DEFAULT")


def get_last_file_stable(filepath: Path) -> Path | None:
    """Return the highest-numbered *-stable.blend in the owning asset folder, or None."""
    path = _owner_dir(Path(filepath))
    stables = list(path.glob("*-stable.blend"))
    if stables:
        if len(stables) == 1:
            return stables[0]
        else:
            stables = [(p, get_version_number(str(p))) for p in stables]
            stables.sort(key=lambda x: x[1], reverse=True)
            return stables[0][0]
    else:
        return None


def library_updates(update: list[tuple[bpy.types.Library, str]]):
    """Repoint and reload each (library, new_path) pair, then resync the wipmeta."""
    mapping = {
        to_relative(resolve_bpy_path(lib.filepath)): to_relative(new)
        for lib, new in update
    }
    for lib, new_path in update:
        try:
            lib.filepath = bpy.path.relpath(new_path)
            lib.reload()

        except Exception:
            pass
    wipmeta_update_libraries(Path(bpy.data.filepath), mapping)


def wipmeta_update_libraries(filepath: Path, update):
    """Rewrite linked-lib paths in this version's .wipmeta after a library
    reload (old path -> new stable path). No-op, doesn't raise, if filepath
    has no .wipmeta: check_library_update() runs (and "Update libraries" can
    be clicked) on any open file, -stable included -- by the time this
    runs, library_updates() has already repointed/reloaded the libraries
    themselves, so there's nothing left to roll back, just no wipmeta to
    log it in; same rule as wipmeta_touch()."""
    path = _meta_path(filepath, ".wipmeta")
    if not path.exists():
        return
    else:
        with locked_json(path) as box:
            data = box["data"] or {}
            data["linked"] = [
                d | {"file": update.get(d["file"], d["file"])} for d in data["linked"]
            ]
            box["action"] = "to_write"


def clean_libraries(linked: list[dict], libs: list[str]) -> list[dict]:
    """Drop entries from a wipmeta's linked list whose file is no longer in libs."""
    linked = [d for d in linked if d["file"] in libs]
    return linked


def get_linked_libraries(filepath: Path) -> list[dict]:
    """This asset/shot's own linked-libraries list ({file, type, name}
    dicts) -- the latest wip's if one exists, else the latest stable's."""
    asset_dir = _owner_dir(Path(filepath))
    wip = get_last_wipmeta(asset_dir)
    if wip:
        return wip.get("linked", [])
    return get_last_stable(asset_dir).get("linked", [])


# owner folder -> (.pipeline mtime, linked list, last checked -- time.monotonic())
_linked_cache: dict[str, tuple[float, list, float]] = {}


def get_linked_libraries_cached(filepath: Path) -> list[dict]:
    """get_linked_libraries() for draw(): keyed on the same .pipeline/ mtime
    as TrackingStatusCache (a new .wipmeta/.stablemeta bumps it), checked at
    most every SCANDIR_TTL."""
    folder = _owner_dir(Path(filepath))
    key = str(folder)
    now_t = time.monotonic()
    cached = _linked_cache.get(key)
    if cached and now_t - cached[2] < SCANDIR_TTL:
        return cached[1]
    mtime = TrackingStatusCache._pipeline_mtime(folder)
    if cached and cached[0] == mtime:
        _linked_cache[key] = (mtime, cached[1], now_t)
        return cached[1]
    try:
        linked = get_linked_libraries(folder)
    except Exception:
        linked = []
    _linked_cache[key] = (mtime, linked, now_t)
    return linked


# Inverse links index, target folder key -> linker folders -- built by
# ProjectScan, read by find_linked_by().
_linked_by_index: dict[str, set[str]] = {}
_linked_by_project: str | None = None
# linker folder -> (.pipeline/ mtime, set of target folder keys it links to)
_linker_targets: dict[str, tuple[float, set[str]]] = {}


def _path_key(path: Path | str) -> str:
    """Comparable form of a folder path: normpath (collapses "../" -- see
    NOTES.md on resolve_bpy_path()) + normcase (case-insensitive on
    Windows). Pure string work, no resolve()."""
    return os.path.normcase(os.path.normpath(str(path)))


def _read_link_targets(owner: Path, project_root: Path, entries: list) -> set[str]:
    """Target folder keys every .wipmeta/.stablemeta of `owner` links into.
    Thread-safe (see read_json_quiet())."""
    targets: set[str] = set()
    for meta in entries:
        if not meta.name.endswith((".wipmeta", ".stablemeta")):
            continue
        data = read_json_quiet(Path(meta.path)) or {}
        for link in data.get("linked", []):
            if link.get("file"):
                file = Path(link["file"])
                file = file if file.is_absolute() else Path(project_root) / file
                targets.add(_path_key(file.parent))
    return targets


def find_linked_by(project_root: Path, filepath: Path) -> list[Path]:
    """Every other asset/shot folder in the project with at least one link
    pointing into filepath's own folder -- matched by folder, not an exact
    version (see NOTES.md). Memory only (called by draw()): reads the index
    ProjectScan builds, and starts one -- returning [] -- if there's none
    for this project yet."""
    if _linked_by_project != str(project_root):
        ProjectScan.start(project_root)
        return []
    # A folder can hold many .wipmeta (one per version) -- the index already
    # collapses those into one set entry, so the same linking asset/shot
    # shows up once no matter how many of its versions link in.
    return sorted(
        Path(p)
        for p in _linked_by_index.get(_path_key(_owner_dir(Path(filepath))), set())
    )
