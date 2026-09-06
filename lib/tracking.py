"""Per-asset tracking: notes/todos, wip/stable meta history, department status."""

import hashlib
import json
import os
from datetime import datetime
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
    to_relative,
)
from .core import get_machine_id, json_get, locked_json, now, read_csv, resolve_bpy_path
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


class TrackingStatusCache:
    """Cache of computed department/tracking status per asset folder, invalidated
    when .pipeline/ (or its tracking.json) changes on disk."""

    _cache: dict[str, tuple[float, dict]] = {}

    @classmethod
    def get(cls, filepath: str, force_reload: bool = False) -> dict:
        """Return the tracking status dict for the asset owning filepath, or
        {} if it can't be computed (missing tracking.json, locked file...).
        Never raises: read by draw()/enum-items callbacks on every redraw,
        with no way to catch or report an error."""
        fp = Path(filepath)
        # Normalize the key to the asset folder, consistent whether we're
        # passed a .blend file or the folder directly
        key = str(fp.parent if fp.is_file() else fp)
        mtime = cls._pipeline_mtime(fp)

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
        the last stable, by scanning .wipmeta files newer than it."""
        asset_dir = filepath.parent if filepath.is_file() else filepath
        tracking_file = asset_dir / ".pipeline" / "tracking.json"

        if not tracking_file.exists():
            raise PipelineError(f"Tracking file not found: {tracking_file}")

        with locked_json(tracking_file, read_only=True) as box:
            global_data = box["data"] or {}

        # Reference point: latest stable
        last_stable = get_last_stable(asset_dir)
        stable_date_str = last_stable.get("created_at")
        stable_date = (
            datetime.fromisoformat(stable_date_str) if stable_date_str else datetime.min
        )

        # Departments validated at the latest stable
        validated_departments = {
            d: v for d, v in last_stable.get("departments_validated", {}).items() if v
        }

        # Departments worked on since the latest stable, via .wipmeta files
        # newer than stable_date
        worked_departments: dict[str, list[dict]] = {}

        if filepath.is_file():
            wipmeta_path = asset_dir / ".pipeline" / f"{_meta_stem(filepath)}.wipmeta"
            with locked_json(wipmeta_path, read_only=True) as box:
                data = box["data"] or {}
                wipmetas = [data]
        else:
            wipmetas = []
            for p in (asset_dir / ".pipeline").glob("*.wipmeta"):
                with locked_json(p, read_only=True) as box:
                    data = box["data"] or {}
                    if data:
                        wipmetas.append(data)

        for meta in wipmetas:
            meta_date_str = meta.get("edited_at", "")
            if not meta_date_str:
                continue
            meta_date = datetime.fromisoformat(meta_date_str)
            if meta_date <= stable_date:
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

    @staticmethod
    def _pipeline_mtime(filepath: Path) -> float:
        """Latest mtime of .pipeline/ and its tracking.json, used as the cache key."""
        pipeline_dir = (
            filepath.parent if filepath.is_file() else filepath
        ) / ".pipeline"
        if not pipeline_dir.exists():
            return 0.0
        tracking = pipeline_dir / "tracking.json"
        return max(
            os.stat(pipeline_dir).st_mtime,
            os.stat(tracking).st_mtime if tracking.exists() else 0.0,
        )

    @classmethod
    def get_all(
        cls, project_root: Path, force_reload: bool = False
    ) -> list[tuple[str, dict]]:
        """Return (asset_dir, status) for every tracked asset in the project,
        refreshing whatever is missing or stale."""
        if force_reload:
            cls._cache.clear()

        # Walks every tracking.json, filling in whatever is missing or stale
        for tracking_file in project_root.rglob(".pipeline/tracking.json"):
            asset_dir = tracking_file.parent.parent
            key = str(asset_dir)
            mtime = cls._pipeline_mtime(asset_dir)
            if key not in cls._cache or cls._cache[key][0] != mtime:
                try:
                    status = cls._scan_and_compute(asset_dir)
                    cls._cache[key] = (mtime, status)
                except Exception as e:
                    log(
                        "WARNING",
                        "tracking",
                        f"Could not compute tracking for {asset_dir}: {e}",
                    )

        # Archived blocks filtered here, not at scan time.
        return [
            (key, data)
            for key, (_, data) in cls._cache.items()
            if not data.get("archived")
        ]


class WorkTimeCache:
    """Total logged work time (session_end duration, everyone summed) per
    asset/shot folder -- total only, never per-person (see design.md).
    Rebuilt in one pass over sessions_log.jsonl on its mtime change."""

    _cache: dict[str, float] = {}
    _mtime: float = -1.0

    @classmethod
    def get(cls, folder) -> float:
        """Total seconds for folder, across every version and everyone --
        live log plus rotated archives/sessions_log_*.jsonl (see NOTES.md).
        0.0 if unreadable. Never raises: read by draw()."""
        log_path = ConfigCache.get_path("sessions_log_file")
        try:
            mtime = log_path.stat().st_mtime
        except OSError:
            mtime = -1.0  # still worth checking archives, not just 0.0
        if mtime != cls._mtime:
            archived = ConfigCache.get_path("logs_archives").glob("sessions_log_*.jsonl")
            cls._cache = cls._scan([log_path, *archived])
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
    try:
        path = filepath.parent / ".pipeline" / "tracking.json"
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
        path = (
            (filepath.parent if filepath.is_file() else filepath)
            / ".pipeline"
            / "tracking.json"
        )
        with locked_json(path, read_only=True) as box:
            data = box["data"] or {}
        return data.get("departments_required")
    except Exception as e:
        raise PipelineError(f"Error during reading tracking file : {e}")


def get_last_wipmeta(filepath: Path) -> dict | None:
    """Return last wipmeta file content of the pointing asset folder."""
    path = (filepath.parent if filepath.is_file() else filepath) / ".pipeline"
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
        path = filepath.parent / ".pipeline" / (_meta_stem(filepath) + ".wipmeta")
        path.parent.mkdir(parents=True, exist_ok=True)
        with locked_json(path) as box:
            box["data"] = data
            box["action"] = "to_write"
    except Exception as e:
        raise PipelineError(f"Error during creating meta file : {e}")


def wipmeta_touch(filepath: Path):
    """Stamp this version's .wipmeta with who/when it was last saved --
    edited_at/edited_by only, doesn't touch departments_worked or linked.
    Called from save_post_handler on every save, so PIPELINE_OT_auto_version
    can tell a same-day re-open by a different user from the file's own
    author. Never raises: handler-called, same rule as check_library_update()."""
    path = filepath.parent / ".pipeline" / (_meta_stem(filepath) + ".wipmeta")
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
    path = filepath.parent / ".pipeline" / (_meta_stem(filepath) + ".wipmeta")
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
    untouched file never claims work that wasn't done."""
    path = filepath.parent / ".pipeline" / (_meta_stem(filepath) + ".wipmeta")
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
    list. No-op, doesn't raise, if filepath has no .wipmeta -- linking into
    an open -stable file is legal (Blender doesn't block it in memory, only
    Save is guarded), and a -stable file has nothing to track it in; same
    rule as wipmeta_touch()."""
    path = filepath.parent / ".pipeline" / (_meta_stem(filepath) + ".wipmeta")
    if not path.exists():
        return
    else:
        with locked_json(path) as box:
            data = box["data"] or {}
            data["linked"] = data.get("linked", []) + link
            box["action"] = "to_write"


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
        original_stem = _meta_stem(original_filepath)
        original_name = (
            f"{original_stem}.wipmeta"
            if not "-stable.blend" in original_filepath.name
            else f"{original_stem}.stablemeta"
        )
        with locked_json(
            original_filepath.parent / ".pipeline" / original_name, read_only=True
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
        path = filepath.parent / ".pipeline" / (_meta_stem(filepath) + ".stablemeta")
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
    asset_dir = filepath.parent if filepath.is_file() else filepath
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


def get_last_stable(filepath: Path) -> dict:
    """Return last stablemeta file content of the pointing asset folder."""
    path = (filepath.parent if filepath.is_file() else filepath) / ".pipeline"
    stables = []
    for p in path.glob("*.stablemeta"):
        try:
            with locked_json(p, read_only=True) as box:
                data = box["data"]
                if data:
                    stables.append(data)
        except PipelineError:
            continue

    if stables:
        stables = sorted(stables, key=lambda x: x["created_at"], reverse=True)
        return stables[0]
    else:
        return {
            "created_at": datetime.min.isoformat(),
            "departments_validated": {},
            "conflict_warning": False,
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
        path = (
            (filepath.parent if filepath.is_file() else filepath)
            / ".pipeline"
            / "tracking.json"
        )
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
        old_path = (
            (from_filepath.parent if from_filepath.is_file() else from_filepath)
            / ".pipeline"
            / "tracking.json"
        )
        with locked_json(old_path, read_only=True) as box:
            old_entries = (box["data"] or {}).get("entries", [])
        if not old_entries:
            return
        new_path = (
            (to_filepath.parent if to_filepath.is_file() else to_filepath)
            / ".pipeline"
            / "tracking.json"
        )
        with locked_json(new_path) as box:
            data = box["data"] or {}
            data["entries"] = data.get("entries", []) + old_entries
            box["action"] = "to_write"
    except Exception as e:
        raise PipelineError(f"Error copying entries: {e}")


def is_block_archived(shot_dir: Path) -> bool:
    """Whether shot_dir's tracking.json is archived. False if missing or
    unreadable."""
    tracking_file = shot_dir / ".pipeline" / "tracking.json"
    if not tracking_file.exists():
        return False
    try:
        with locked_json(tracking_file, read_only=True) as box:
            return bool((box["data"] or {}).get("archived"))
    except Exception:
        return False


def list_active_blocks(
    project_root: Path, sequence_label: str | None = None
) -> list[Path]:
    """Every shot/block folder under shots/ (optionally one sequence) that
    isn't archived."""
    shots_dir = project_root / "shots"
    if not shots_dir.is_dir():
        return []
    sequences = (
        [shots_dir / sequence_label] if sequence_label else sorted(shots_dir.iterdir())
    )
    out = []
    for sq_dir in sequences:
        if not sq_dir.is_dir():
            continue
        for sh_dir in sorted(sq_dir.iterdir()):
            if (
                sh_dir.is_dir()
                and sh_dir.name != ARCHIVE_DIRNAME
                and not is_block_archived(sh_dir)
            ):
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
):
    """Append a note/todo/rtk entry to the owning asset's tracking.json.
    text/department/author/type are keyword-only: all plain strings, a
    positional call risks silently swapping department and author.
    shot: free-text tag (e.g. "045"), not validated against anything."""
    try:
        print(f"Creating entry {type} for {filepath} : {text} ({department})")
        path = (
            (filepath.parent if filepath.is_file() else filepath)
            / ".pipeline"
            / "tracking.json"
        )
        with locked_json(path) as box:
            data = box["data"] or {}

            nw = now()
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
        path = (
            (filepath.parent if filepath.is_file() else filepath)
            / ".pipeline"
            / "tracking.json"
        )
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
        path = (
            (filepath.parent if filepath.is_file() else filepath)
            / ".pipeline"
            / "tracking.json"
        )
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
        path = (
            (filepath.parent if filepath.is_file() else filepath)
            / ".pipeline"
            / "tracking.json"
        )
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


def valid_csv(row: dict) -> bool:
    """Whether a CSV row has the required 'text' and 'filename' columns."""
    return "text" in row and "filename" in row


def upload_csv(filepath: Path, user: str) -> tuple[int, int]:
    """Bulk-create entries from a CSV: one row -> one create_entry() call. A
    failing row (unknown file, bad department...) is logged and skipped, the
    rest continues. Returns (imported_count, total_rows) -- a partial
    import is not raised as an error."""
    data = read_csv(filepath)
    if data and not valid_csv(data[0]):
        raise PipelineError(
            "CSV header seems to miss 'text' and/or 'filename' to identify columns"
        )
    count = 0
    for row in data:
        try:
            keys = row.keys()
            select_filepath = find_file_by_name(row["filename"])
            if not select_filepath:
                log("WARNING", "csv_import", f"CSV row {row}, filename unknow.")

            department = valid_department(select_filepath, row["department"])
            create_entry(
                select_filepath,
                text=row["text"],
                department=department,
                author=row["author"] if "authors" in keys else user,
                type=row["type"]
                if "type" in keys and row["type"] in ["note", "todo", "rtk"]
                else "note",
                shot=row.get("shot") or None,
            )
            count += 1
        except Exception as e:
            log("WARNING", "csv_import", f"CSV row {row} can't be imported : {e}")
    return count, len(data)


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
            message="\n".join([f"{old.filepath} -> {new}" for old, new in update]),
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
        bpy.ops.pipeline.action_popup("INVOKE_DEFAULT")


def get_last_file_stable(filepath: Path) -> Path | None:
    """Return the highest-numbered *-stable.blend in the owning asset folder, or None."""
    path = filepath.parent if filepath.is_file() else filepath
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
    path = filepath.parent / ".pipeline" / (_meta_stem(filepath) + ".wipmeta")
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
