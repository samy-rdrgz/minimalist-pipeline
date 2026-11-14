"""Migrate a project's data to the one form 1.2 reads: what older addons
wrote, completed once with the deductions their readers made each time --
so the readers know a single form (see NOTES.md, "Migration 1.2: one form
of data"). Run from Edit project > Maintenance, once per project, every
machine updated first. Every file is backed up before it's rewritten,
under backup/migration-<date>/ at the project's root, at its own relative
path: a migration checked is cleaned by deleting that one folder.

plan_migration() reads (pure os/json: thread-safe), apply_migration()
writes (main thread: locked_json()). What each step completes:
- tracking.json: an entry's single "department" -> "departments" (1.1.0).
- .stablemeta: "departments_started" (validated at any stable or worked
  before it); "departments_worked" and the validations it carried
  ("approvals_carried", 1.1.9); "linked" one entry per project file.
- .wipmeta: "linked" one entry per project file.
- render_history.json: a finished render's "output_path", "source_file",
  "shot_override" (1.0.11, from its folder) and "frame_range_rendered"
  (from its images' numbers)."""

import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from .core import locked_json, now, parse_iso, read_json_quiet
from .preview import render_root
from .snapshot import _folder_frames, _owner_shots
from .tracking import (
    _CLOCK_MARGIN_SECONDS,
    _DATA_ROOTS,
    _is_under,
    _path_key,
    _pipeline_entries,
    _stablemeta_of,
    _walk_owner_dirs,
    _worked_between,
    compact_linked,
)

# This migration's name, in the config's "data_migrations" once run.
MIGRATION = "1.2"
BACKUP_DIRNAME = "backup"


def migration_done(config: dict) -> bool:
    """Whether this project's data has been migrated (or never needed it:
    a project created by this version)."""
    return MIGRATION in ((config or {}).get("data_migrations") or {})


def migration_record(user: str, files: int = 0) -> dict:
    """The config's data_migrations entry for this migration."""
    return {MIGRATION: {"at": now(), "by": user, "files": files}}


def plan_migration(root: Path, v_prefix: str = "v") -> dict:
    """What migrating root would rewrite, read only: {"files": [{"path",
    "data", "changes": [str]}], "owners": folders read, "counts": {change:
    files}}. Thread-safe (pure os/json)."""
    root = Path(root)
    files = []
    owners = 0
    for top in _DATA_ROOTS:
        for owner in _walk_owner_dirs(root / top):
            owners += 1
            files += _plan_owner(root, owner, top == "shots", v_prefix)
    counts: dict[str, int] = {}
    for f in files:
        for change in f["changes"]:
            counts[change] = counts.get(change, 0) + 1
    return {"files": files, "owners": owners, "counts": counts}


def apply_migration(root: Path, plan: dict) -> dict:
    """Write plan_migration()'s files, each backed up first under
    backup/migration-<date>/. -> {"written", "backup", "errors": [(path,
    why)]}. Main thread (locked_json())."""
    root = Path(root)
    stamp = now(iso=False).strftime("%Y-%m-%d_%H-%M")
    backup = root / BACKUP_DIRNAME / f"migration-{stamp}"
    written, errors = 0, []
    for f in plan["files"]:
        path = Path(f["path"])
        try:
            rel = path.relative_to(root)
            target = backup / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():  # a second run the same minute: the first copy
                shutil.copy2(path, target)
            with locked_json(path) as box:
                box["data"] = f["data"]
                box["action"] = "to_write"
            written += 1
        except Exception as e:
            errors.append((str(path), str(e)))
    return {"written": written, "backup": str(backup), "errors": errors}


# ---------------------------------------------------------------------------
# One asset/shot folder
# ---------------------------------------------------------------------------


def _plan_owner(root: Path, owner: Path, is_shot: bool, v_prefix: str) -> list[dict]:
    pipeline = owner / ".pipeline"
    entries = _pipeline_entries(owner)
    tracking = read_json_quiet(pipeline / "tracking.json") or {}
    out = []

    changed = _migrate_entries(tracking)
    if changed:
        out.append({"path": str(pipeline / "tracking.json"), "data": tracking, "changes": changed})

    stables = _read_metas(entries, ".stablemeta")
    # Computed from the files as they are, before any is changed: the
    # older readers' answers.
    stable_changes = _migrate_stables(entries, stables, tracking)
    for entry, data in stables:
        changes = stable_changes.get(entry.path, [])
        if _migrate_linked(data, root):
            changes.append("links one per file")
        if changes:
            out.append({"path": entry.path, "data": data, "changes": changes})

    for entry, data in _read_metas(entries, ".wipmeta"):
        if _migrate_linked(data, root):
            out.append({"path": entry.path, "data": data, "changes": ["links one per file"]})

    history_path = pipeline / "render_history.json"
    history = read_json_quiet(history_path) if history_path.is_file() else None
    if history:
        changed = _migrate_history(history, root, owner, is_shot, v_prefix)
        if changed:
            out.append({"path": str(history_path), "data": history, "changes": changed})
    return out


def _read_metas(entries: list, suffix: str) -> list[tuple]:
    """[(DirEntry, data)] of a .pipeline/ listing's metas of suffix."""
    out = []
    for entry in entries:
        if entry.name.endswith(suffix):
            data = read_json_quiet(Path(entry.path))
            if isinstance(data, dict):
                out.append((entry, data))
    return out


# ---------------------------------------------------------------------------
# tracking.json: an entry's departments
# ---------------------------------------------------------------------------


def _entry_departments(e: dict) -> list[str]:
    """An entry's departments as found: "departments", else its single
    "department" of before 1.1.0 (tracking.entry_departments() reads only
    the first, once migrated)."""
    if e.get("departments"):
        return list(e["departments"])
    return [e["department"]] if e.get("department") else []


def _migrate_entries(tracking: dict) -> list[str]:
    """Every entry's departments as "departments" (a list), its single
    "department" of before 1.1.0 dropped."""
    n = 0
    for e in tracking.get("entries") or []:
        if not isinstance(e, dict) or "department" not in e:
            continue
        deps = _entry_departments(e)
        del e["department"]
        if deps:
            e["departments"] = deps
        n += 1
    return ["entry departments"] if n else []


# ---------------------------------------------------------------------------
# .stablemeta: started, worked, the validations carried
# ---------------------------------------------------------------------------


def _migrate_stables(entries: list, stables: list, tracking: dict) -> dict:
    """{stablemeta path: [changes]}, each stable's data completed in place:
    departments_started, departments_worked, approvals carried."""
    by_date = sorted(
        ((d, e, data) for e, data in stables if (d := parse_iso(data.get("created_at")))),
        key=lambda x: x[0],
    )
    wipmetas = [data for _, data in _read_metas(entries, ".wipmeta")]
    # Every answer from the files as found, before writing any.
    todo = []
    for i, (date, entry, data) in enumerate(by_date):
        changes = {}
        if "departments_started" not in data:
            changes["departments_started"] = _started_at(by_date[: i + 1], wipmetas, date)
        if "approvals_carried" not in data:
            # (Never datetime.min itself: _worked_between() takes a margin off.)
            start = by_date[i - 1][0] if i else datetime.min + timedelta(days=1)
            changes["departments_worked"] = sorted(
                _worked_between(entries, start, date)
                | (_rtk_departments(tracking, start, date) if _from_stable(data) else set())
            )
            if data.get("approvals_previous"):
                changes["carried"] = _legacy_carried(entries, data, tracking)
        todo.append((entry, data, changes))
    out = {}
    for entry, data, changes in todo:
        said = []
        if "departments_started" in changes:
            data["departments_started"] = changes["departments_started"]
            said.append("stable: departments started")
        if "departments_worked" in changes:
            data["departments_worked"] = changes["departments_worked"]
            for d, roles in (changes.get("carried") or {}).items():
                for role, info in roles.items():
                    data.setdefault("approvals", {}).setdefault(d, {}).setdefault(role, info)
            data["approvals_carried"] = True
            said.append("stable: validations carried")
        if said:
            out[entry.path] = said
    return out


def _from_stable(data: dict) -> bool:
    """Made from a stable (none recorded what was worked then); unknown
    counts as one."""
    return "-stable." in (data.get("created_from") or "-stable.")


def _started_at(stables_so_far: list, wipmetas: list, date: datetime) -> list[str]:
    """Validated at a stable up to this one, or worked in a version saved
    by then: what made a department "started" (create_stablemeta())."""
    started = set()
    for _, _, data in stables_so_far:
        started |= {d for d, v in (data.get("departments_validated") or {}).items() if v}
    limit = date + timedelta(seconds=_CLOCK_MARGIN_SECONDS)
    for meta in wipmetas:
        edited = parse_iso(meta.get("edited_at"))
        if edited is None or edited > limit:
            continue
        for deps in (meta.get("departments_worked") or {}).values():
            started.update(deps or [])
    return sorted(started)


def _rtk_departments(tracking: dict, start: datetime, end: datetime) -> set[str]:
    """Departments with an RTK opened or closed after start, up to end -- a
    general one (no department) counts for each required department: what
    was worked through a stable made from a stable before 1.1.9."""
    out = set()
    for e in tracking.get("entries") or []:
        if not isinstance(e, dict) or e.get("type") != "rtk":
            continue
        dates = [d for d in (parse_iso(e.get("created_at")), parse_iso(e.get("done_at"))) if d]
        if any(start < d <= end for d in dates):
            out |= set(_entry_departments(e) or tracking.get("departments_required") or [])
    return out


def _worked_since(entries: list, start: datetime, end: datetime, tracking: dict) -> set[str]:
    """Departments worked after start, up to end, as the readers before 1.2
    worked it out: the wipmetas edited between and each stable made
    between's departments_worked; through a stable made from a stable
    before 1.1.9 (none recorded), those an RTK was opened or closed on."""
    worked = _worked_between(entries, start, end)
    blind = False
    for _, data in _read_metas(entries, ".stablemeta"):
        at = parse_iso(data.get("created_at"))
        if at is None or not start < at <= end:
            continue
        if "approvals_carried" in data:
            worked |= set(data.get("departments_worked") or [])
        elif _from_stable(data):
            blind = True
    if blind:
        worked |= _rtk_departments(tracking, start, end)
    return worked


def _legacy_carried(entries: list, stable: dict, tracking: dict) -> dict:
    """For a stable made before validations were carried (1.1.9): the last
    validations of earlier stables of its done departments not worked
    since -- what it would have carried."""
    previous = stable.get("approvals_previous") or {}
    done = {d for d, v in (stable.get("departments_validated") or {}).items() if v}
    own = stable.get("approvals") or {}
    end = parse_iso(stable.get("created_at"))
    if end is None:
        return {}
    carried: dict[str, dict] = {}
    worked_cache: dict[str, set | None] = {}
    for department, roles in previous.items():
        if department not in done:
            continue
        for role, info in roles.items():
            if role in (own.get(department) or {}):
                continue
            file = info.get("file") or ""
            if file not in worked_cache:
                start = parse_iso((_stablemeta_of(entries, file) or {}).get("created_at"))
                worked_cache[file] = (
                    None if start is None else _worked_since(entries, start, end, tracking)
                )
            worked = worked_cache[file]
            if worked is None or department in worked:
                continue
            carried.setdefault(department, {})[role] = {
                k: v for k, v in info.items() if k != "file"
            } | {"carried_from": file}
    return carried


# ---------------------------------------------------------------------------
# .stablemeta / .wipmeta: linked
# ---------------------------------------------------------------------------


def _migrate_linked(data: dict, root: Path) -> bool:
    """A meta's "linked" list as written now: one {"file"} per project
    file -- an older list had one per datablock, and Blender's own files."""
    linked = data.get("linked")
    if not isinstance(linked, list):
        return False
    key = _path_key(root)
    kept = []
    for d in compact_linked([x for x in linked if isinstance(x, dict)]):
        file = Path(d["file"])
        if _is_under(_path_key(file if file.is_absolute() else root / file), key):
            kept.append(d)
    if kept == linked:
        return False
    data["linked"] = kept
    return True


# ---------------------------------------------------------------------------
# render_history.json
# ---------------------------------------------------------------------------

# A render's frames and video are written just before its entry: its
# folder's newest file is this close to completed_at.
_FOLDER_MATCH = timedelta(minutes=30)


def _migrate_history(history: dict, root: Path, owner: Path, is_shot: bool, v_prefix: str) -> list[str]:
    """Every finished render's output_path, source_file, shot_override and
    frame_range_rendered. One from before 1.0.11 (no output_path) is
    matched to its render folder by time -- the folder no other entry names
    whose newest file was written closest to when it ended; none that
    close: left as it is, and no reader takes it for a render."""
    entries = [
        e
        for e in history.get("entries") or []
        if isinstance(e, dict) and e.get("status") == "finished"
    ]
    if not entries:
        return []
    base = render_root(root, owner)
    shots = _owner_shots(owner) if is_shot else []
    dirs = {"": base} | ({s: base.with_name(s) for s in shots} if len(shots) > 1 else {})
    named = {
        os.path.normcase(str((root / e["output_path"]).parent))
        for e in entries
        if e.get("output_path")
    }
    folders = []  # (newest file's time, shot, folder) not named by an entry
    pattern = re.compile(rf"^{re.escape(v_prefix)}\d+(?:-[a-z]+)?_\d+$")
    for shot, d in dirs.items():
        try:
            subs = [Path(x.path) for x in os.scandir(d) if x.is_dir() and pattern.match(x.name)]
        except OSError:
            continue
        for folder in subs:
            if os.path.normcase(str(folder)) in named:
                continue
            when = _newest_file(folder)
            if when is not None:
                folders.append((when, shot, folder))
    changes = set()
    for e in sorted(entries, key=lambda e: str(e.get("completed_at") or "")):
        if not e.get("output_path"):
            ended = parse_iso(e.get("completed_at"))
            match = None
            if ended is not None:
                near = [f for f in folders if abs(f[0] - ended) <= _FOLDER_MATCH]
                match = min(near, key=lambda f: abs(f[0] - ended), default=None)
            if match is None:
                continue
            folders.remove(match)
            _, shot, folder = match
            video = next(
                (x for x in sorted(os.listdir(folder)) if x.lower().endswith(".mp4")), None
            )
            # Its video, or a frame pattern: what matters is the folder.
            e["output_path"] = (folder / (video or "####")).relative_to(root).as_posix()
            e.setdefault("shot_override", shot)
            changes.add("render: folder found")
        folder = (root / e["output_path"]).parent
        if not e.get("source_file"):
            source = _source_of(owner, folder.name, root)
            if source:
                e["source_file"] = source
                changes.add("render: source file")
        if "shot_override" not in e:
            e["shot_override"] = ""
            changes.add("render: shot")
        if not e.get("frame_range_rendered"):
            frames = _folder_frames(folder)
            if frames:
                e["frame_range_rendered"] = frames
                changes.add("render: frame range")
    return sorted(changes)


def _newest_file(folder: Path) -> datetime | None:
    """When a render folder's newest file was written (its video, its last
    frame) -- the folder's own time moves when Clean old renders empties
    it. None for an empty or unreadable folder."""
    try:
        times = [x.stat().st_mtime for x in os.scandir(folder) if x.is_file()]
    except OSError:
        return None
    return datetime.fromtimestamp(max(times)) if times else None


def _source_of(owner: Path, folder: str, root: Path) -> str | None:
    """The .blend a render folder (v004-stable_002) was made from: the
    owner's file of that version (archived in old/ too), else its name as
    the owner's other files are named. Project-relative, None if the owner
    has no file to tell."""
    version = folder.rsplit("_", 1)[0]
    blends = []
    for d in (owner, owner / "old"):
        try:
            blends += [Path(x.path) for x in os.scandir(d) if x.name.lower().endswith(".blend")]
        except OSError:
            pass
    for b in blends:
        if b.stem.endswith(f"_{version}"):
            return b.relative_to(root).as_posix()
    for b in blends:
        stem, _, last = b.stem.rpartition("_")
        if stem and last:
            return (owner / f"{stem}_{version}.blend").relative_to(root).as_posix()
    return None
