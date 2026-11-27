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
  ("approvals_carried", 1.1.9); "linked" one entry per project file;
  "departments_validated" renamed "departments_done" (2.0: it has meant
  Done since 1.1.2, validations being "approvals"), the old name kept
  beside it for 1.x builds (lib/monitoring/legacy.py).
- .wipmeta: "linked" one entry per project file; each session with its
  date (1.2: {"departments", "saved_at", "by"}), under "sessions" (2.0),
  the old name "departments_worked" kept beside it for 1.x builds
  (lib/monitoring/legacy.py).
- render_history.json: a finished render's "output_path", "source_file",
  "shot_override" (1.0.11, from its folder) and "frame_range_rendered"
  (from its images' numbers).
- all four: every date and time with its offset (1.2), the local time of
  the machine migrating.
- config/presets: the files loose in it moved into their folder (2.0): a
  render preset into render_shots/ or render_assets/ (its department's
  kind), asset_file_preset.py into creation/; a .json render preset (a
  flat map of scene paths, read no more) rewritten as the .py doing the
  same; a department with no render preset of its kind given its
  <department>_default.py (1.2: renders by department, see NOTES.md,
  "Renders by department")."""

import json
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from .monitoring import legacy
from .core import EARLIEST, file_time, locked_json, now, parse_iso, read_json_quiet, time_key
from .preview import render_root
from .monitoring.snapshot import _folder_frames, _owner_shots
from .monitoring.tracking import (
    _CLOCK_MARGIN_SECONDS,
    _DATA_ROOTS,
    _is_under,
    _path_key,
    _pipeline_entries,
    _stablemeta_of,
    _unique_entry_id,
    _walk_owner_dirs,
    _worked_between,
    compact_linked,
    worked_sessions,
)

# This migration's name, in the config's "data_migrations" once run.
# "2.0": a project migrated by a 2.0 build before departments_done ("1.2")
# is offered it again -- every step finds what's already done and skips it.
# "2.1": the progress log's files by state (Breakdown), every day before
# rebuilt -- a project migrated by 2.0 offered it again for them.
MIGRATION = "2.1"
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
    history: list = []  # every folder's metas as migrated: the progress rebuilt
    for top in _DATA_ROOTS:
        for owner in _walk_owner_dirs(root / top):
            owners += 1
            files += _plan_owner(root, owner, top == "shots", v_prefix, history)
    counts: dict[str, int] = {}
    for f in files:
        for change in f["changes"]:
            counts[change] = counts.get(change, 0) + 1
    presets = _plan_presets(root)
    loose = presets.pop("loose")
    if presets["move"]:
        counts["presets: into their folders"] = len(presets["move"])
    if presets["json"]:
        counts["render presets: .json to .py"] = len(presets["json"])
    if presets["shot_departments"] or presets["asset_departments"]:
        counts["render presets: one per department"] = len(presets["shot_departments"]) + len(presets["asset_departments"])
    from .monitoring import progress_log

    missing = _progress_days_missing(root, history)
    if missing:
        counts["progress: days rebuilt"] = missing
    # Not "activity_until": the mornings write it too, for their last 30 days at most.
    activity = not progress_log.read(root).get("activity_rebuilt") and bool(history)
    if activity:
        counts["activity: rebuilt"] = 1
    return {"files": files, "owners": owners, "counts": counts, "presets": presets, "loose_presets": loose,
            "progress": history if missing or activity else [], "progress_missing": missing, "activity": activity}


def _progress_days_missing(root: Path, history: list) -> int:
    """How many days before today the progress log doesn't hold, from the
    project's first change (progress_log.rebuild() writes them)."""
    from .monitoring import progress_log

    first = min(
        (d for _k, _o, tracking, stables, wips in history for d in progress_log._change_days(tracking, stables, wips)),
        default=None,
    )
    if first is None:
        return 0
    today = datetime.now().date()
    logged = progress_log.days(root)
    day, n = datetime.fromisoformat(first).date(), 0
    while day < today:
        # Missing, or logged before 2.1 without its files by state (Breakdown).
        n += not progress_log.has_states(logged.get(day.isoformat()))
        day += timedelta(days=1)
    return n


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
                # Written since the preview read it (a note, a save, another
                # machine): left as it is, not overwritten with the data
                # read before -- the migration runs again for it.
                if f.get("mtime") is not None and _mtime(path) != f["mtime"]:
                    errors.append((str(path), "changed since the preview: run Migrate old data again"))
                    continue
                box["data"] = f["data"]
                box["action"] = "to_write"
            written += 1
        except Exception as e:
            errors.append((str(path), str(e)))
    written += _apply_presets(root, plan.get("presets") or {}, backup, errors)
    rebuilt = 0
    if plan.get("progress"):
        # Last: the files above as written. The one place every meta is read.
        from .monitoring import progress_log

        try:
            config = read_json_quiet(root / "config" / "project_config.json") or {}
            if plan.get("progress_missing", True):
                rebuilt = progress_log.rebuild(root, plan["progress"], config)
            if plan.get("activity", True):
                progress_log.rebuild_activity(root, plan["progress"])
        except Exception as e:
            errors.append((str(progress_log.path_of(root)), str(e)))
    return {"written": written, "backup": str(backup), "errors": errors, "progress_days": rebuilt}


# ---------------------------------------------------------------------------
# Render presets: Python only, one per department
# ---------------------------------------------------------------------------


def _plan_presets(root: Path) -> dict:
    """What config/presets/ needs -- read only:
    "move": [[from, to]], the files still loose in presets/ (before 2.0)
    into their folder: a render preset into render_shots/ or render_assets/
    (lib/presets.py preset_kind()), asset_file_preset.py into creation/ --
    one whose name is already there left where it is;
    "json": [[from, to]], the .json render presets rewritten as the .py
    in their folder; "shot_departments" / "asset_departments": the
    departments with no preset of their kind; "loose": the presets whose
    name gives no department."""
    from .monitoring.status import preset_department
    from .presets import ASSET_PRESET, CREATION_DIR, RENDER_DIRS, SHOT_PRESET, preset_kind, render_presets

    folder = root / "config" / "presets"
    try:
        names = sorted(p for p in folder.iterdir() if p.is_file())
    except OSError:
        names = []
    config = read_json_quiet(root / "config" / "project_config.json") or {}

    def listed(key):
        return list(dict.fromkeys(str(d).strip().lower() for d in config.get(key) or [] if str(d).strip()))

    shots, assets = listed("shots_departments"), listed("assets_departments")
    assigned = ((config.get("farm") or {}).get("department_presets")) or {}
    assigned = {str(d).lower(): p for d, p in assigned.items()}

    # Each render preset's kind once migrated: its folder's, else the one it goes in.
    kinds: dict[str, str] = {}
    for kind, sub in RENDER_DIRS.items():
        for name in render_presets(root, kind):
            if (folder / sub / f"{name}.py").is_file():
                kinds.setdefault(name, kind)
    move, jsons = [], []
    for p in names:
        if p.name in (ASSET_PRESET, SHOT_PRESET):
            dest = folder / CREATION_DIR / p.name
        elif p.suffix in (".py", ".json"):
            kind = kinds.setdefault(p.stem, preset_kind(p.stem, shots, assets, assigned))
            dest = folder / RENDER_DIRS[kind] / f"{p.stem}.py"
            if p.suffix == ".json":
                jsons.append([str(p), str(dest)])
                continue
        else:
            continue
        if not dest.exists():
            move.append([str(p), str(dest)])

    def missing(departments, kind):
        have = [n for n, k in kinds.items() if k == kind]
        return [d for d in departments if not any(preset_department(n, [d]) == d for n in have)]

    # Said, not changed: Edit project's Rename preset gives them one.
    loose = sorted(n for n in kinds if not preset_department(n, [*shots, *assets]))
    return {"move": move, "json": jsons, "shot_departments": missing(shots, "shot"),
            "asset_departments": missing(assets, "asset"), "loose": loose}


def _preset_py(overrides: dict, name: str) -> str:
    """A .json preset's flat map ({"render.engine": "CYCLES"}) as the .py
    doing the same."""
    lines = [
        f'"""Render preset {name}: rewritten from its .json by the 1.2 migration."""',
        "",
        "",
        "def override(scene, job_data):",
    ]
    for key, value in overrides.items():
        *path, attr = str(key).split(".")
        target = ".".join(["scene", *path])
        lines.append(f"    {target}.{attr} = {value!r}")
    if len(lines) == 4:
        lines.append("    pass")
    return "\n".join(lines) + "\n"


def _apply_presets(root: Path, presets: dict, backup: Path, errors: list) -> int:
    """_plan_presets()'s changes: the loose files moved into their folder
    (each backed up first); each .json backed up, rewritten as the .py in
    its folder (a .py of its name already there won: the .json only
    removed), then removed; the departments' default presets, in their
    kind's folder. Returns files written."""
    from .presets import install_department_presets, render_preset_path

    def backed_up(path: Path) -> None:
        target = backup / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(path, target)

    written = 0
    for src, dest in presets.get("move") or []:
        src, dest = Path(src), Path(dest)
        try:
            if dest.exists():
                raise FileExistsError(f"{dest.relative_to(root)} already there: left where it is")
            backed_up(src)
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)
            written += 1
        except Exception as e:
            errors.append((str(src), str(e)))
    for src, dest in presets.get("json") or []:
        path, py = Path(src), Path(dest)
        try:
            backed_up(path)
            if render_preset_path(path.stem, root) is None:
                overrides = read_json_quiet(path)
                if not isinstance(overrides, dict):
                    raise ValueError("unreadable")
                py.parent.mkdir(parents=True, exist_ok=True)
                py.write_text(_preset_py(overrides, path.stem), encoding="utf-8")
                written += 1
            path.unlink()
        except Exception as e:
            errors.append((src, str(e)))
    if presets.get("shot_departments") or presets.get("asset_departments"):
        written += len(install_department_presets(presets.get("shot_departments"), presets.get("asset_departments"), root))
    return written


# ---------------------------------------------------------------------------
# One asset/shot folder
# ---------------------------------------------------------------------------


def _plan_owner(root: Path, owner: Path, is_shot: bool, v_prefix: str, history: list | None = None) -> list[dict]:
    pipeline = owner / ".pipeline"
    entries = _pipeline_entries(owner)
    tracking = read_json_quiet(pipeline / "tracking.json") or {}
    found = []  # (path, data, changes): every file read, changed or not

    found.append((str(pipeline / "tracking.json"), tracking, _migrate_entries(tracking) + _migrate_ids(tracking)))

    stables = _read_metas(entries, ".stablemeta")
    # Computed from the files as they are, before any is changed: the
    # older readers' answers.
    stable_changes = _migrate_stables(entries, stables, tracking)
    for entry, data in stables:
        changes = stable_changes.get(entry.path, [])
        if _migrate_linked(data, root):
            changes.append("links one per file")
        if _migrate_done(data):
            changes.append("stable: departments_done")
        found.append((entry.path, data, changes))

    wips = _read_metas(entries, ".wipmeta")
    if history is not None:
        # The same dicts: migrated below, in memory, before the progress is rebuilt.
        history.append(("shot" if is_shot else "asset", str(owner), tracking, [d for _, d in stables], [d for _, d in wips]))
    for entry, data in wips:
        changes = ["links one per file"] if _migrate_linked(data, root) else []
        if _migrate_sessions(data):
            changes.append("sessions with their date, named sessions")
        found.append((entry.path, data, changes))

    history_path = pipeline / "render_history.json"
    renders = read_json_quiet(history_path) if history_path.is_file() else None
    if renders:
        found.append((str(history_path), renders, _migrate_history(renders, root, owner, is_shot, v_prefix)))

    out = []
    for path, data, changes in found:
        if not data:
            continue
        # Last: the steps above read the dates as found.
        if _migrate_dates(data):
            changes = [*changes, "dates with their offset"]
        if changes:
            out.append({"path": path, "data": data, "changes": changes, "mtime": _mtime(path)})
    return out


def _mtime(path) -> int | None:
    """A file's modification time (ns), None when it can't be read: what
    apply_migration() compares, the file changed since it was read."""
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


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
# .wipmeta: each session's date
# ---------------------------------------------------------------------------


def _migrate_sessions(data: dict) -> bool:
    """Each session as written now, {"departments", "saved_at", "by"}: a
    bare list (before 1.2) dated by the file's edited_at / edited_by -- the
    only date it had; under "sessions" (2.0), "departments_worked" kept
    beside it, equal (legacy.wip_written())."""
    if not isinstance(data.get("departments_worked"), dict) and not isinstance(data.get("sessions"), dict):
        return False
    before = (data.get("sessions"), data.get("departments_worked"))
    before = json.dumps(before, sort_keys=True)
    sessions = legacy.wip_read(data).get("sessions")
    if not isinstance(sessions, dict):
        return False
    changed = False
    for key, entry in sessions.items():
        if isinstance(entry, list):
            sessions[key] = {
                "departments": entry,
                "saved_at": data.get("edited_at"),
                "by": data.get("edited_by"),
            }
            changed = True
    legacy.wip_written(data)
    return changed or json.dumps((data.get("sessions"), data.get("departments_worked")), sort_keys=True) != before


# ---------------------------------------------------------------------------
# Dates: their offset
# ---------------------------------------------------------------------------

# A date and time without an offset, as now() wrote them before 1.2. Never a
# day alone (a schedule's, a review's): no hour to place.
_NAIVE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$")


def _migrate_dates(data) -> int:
    """Every date and time without an offset in data, at any depth, given
    this machine's -- the local time its readers took it for (written in
    another time zone, it was already read so). How many changed."""
    n = 0
    items = data.items() if isinstance(data, dict) else enumerate(data) if isinstance(data, list) else ()
    for key, value in list(items):
        if isinstance(value, (dict, list)):
            n += _migrate_dates(value)
        elif isinstance(value, str) and _NAIVE_TIME.match(value):
            try:
                at = datetime.fromisoformat(value).astimezone()
            except (ValueError, OverflowError, OSError):
                continue
            data[key] = at.isoformat(timespec="microseconds" if at.microsecond else "seconds")
            n += 1
    return n


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


def _migrate_ids(tracking: dict) -> list[str]:
    """An id found twice made unique (notes written by older versions, the
    same words at the same second): the first keeps it -- its replies point
    to it --, the others get one of their own. The page's Fixed and Reply
    find a note by its id."""
    entries = [e for e in tracking.get("entries") or [] if isinstance(e, dict)]
    taken, seen, n = {e.get("id") for e in entries}, set(), 0
    for i, e in enumerate(entries):
        old = e.get("id")
        if not old:
            continue
        if old in seen:
            e["id"] = _unique_entry_id(f"{old}#{i}{e.get('created_at', '')}", taken)
            taken.add(e["id"])
            n += 1
        seen.add(old)
    return ["entry ids made unique"] if n else []


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
            # (Never EARLIEST itself: _worked_between() takes a margin off.)
            start = by_date[i - 1][0] if i else EARLIEST + timedelta(days=1)
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


def _done_of(data: dict) -> dict:
    """A stable's done departments, read as found: departments_done, or
    departments_validated before 2.0 (the same thing, its older name)."""
    done = data.get("departments_done")
    if not isinstance(done, dict):
        done = data.get("departments_validated")
    return done if isinstance(done, dict) else {}


def _migrate_done(data: dict) -> bool:
    """departments_validated renamed departments_done (2.0), the old name
    kept beside it, equal, while 1.x builds may read the project
    (lib/monitoring/legacy.py). Both there and differing: a 1.x wrote it last, its
    values win (legacy.stable_read()). False when nothing changes."""
    if "departments_validated" not in data:
        return False
    before = (data.get("departments_done"), data.get("departments_validated"))
    legacy.stable_written(legacy.stable_read(data))
    return (data.get("departments_done"), data.get("departments_validated")) != before


def _from_stable(data: dict) -> bool:
    """Made from a stable (none recorded what was worked then); unknown
    counts as one."""
    return "-stable." in (data.get("created_from") or "-stable.")


def _started_at(stables_so_far: list, wipmetas: list, date: datetime) -> list[str]:
    """Validated at a stable up to this one, or worked in a version saved
    by then: what made a department "started" (create_stablemeta())."""
    started = set()
    for _, _, data in stables_so_far:
        started |= {d for d, v in _done_of(data).items() if v}
    limit = date + timedelta(seconds=_CLOCK_MARGIN_SECONDS)
    for meta in wipmetas:
        for session in worked_sessions(meta):
            saved = parse_iso(session.get("saved_at"))
            if saved is not None and saved <= limit:
                started.update(session.get("departments") or [])
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
    done = {d for d, v in _done_of(stable).items() if v}
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
    for e in sorted(entries, key=lambda e: time_key(e.get("completed_at"))):
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
    return file_time(max(times)) if times else None


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
