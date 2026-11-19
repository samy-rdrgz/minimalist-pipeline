"""Import review: a review sent back -- the .json the snapshot page's
Review makes -- read, planned and written into the project's tracking."""

import filecmp
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from .config import (
    ConfigCache,
    parse_filename,
    sanitize_name,
    shots_in_segment,
    validation_roles,
)
from .core import json_get, now, parse_iso, read_json_quiet
from .errors import PipelineError
from .schedule import parse_day
from .snapshot import (
    REVIEW_SOURCE,
    REVIEWS_DIRNAME,
    SCHEMA_VERSION,
    TEAM_REVIEW_SOURCE,
    TEAM_ROLE,
    _same_path,
    month_folder,
    render_of_note,
)
from .tracking import (
    _collect_folder,
    _status_from_raw,
    close_entry,
    create_entry,
    entry_departments,
    find_file_by_name,
    get_departments_required,
    set_department_approval,
    set_department_done,
    set_department_synced,
    set_department_assignees,
    set_departments_required,
    set_file_omit,
    tracking_json_path,
    valid_department,
    worked_since_stable,
)

def parse_review_date(value: str) -> datetime | None:
    """A review's date: a day in a common date format, or ISO. None when
    empty."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        # That day's start, local: comparable with the notes' dates.
        return datetime.combine(parse_day(value), datetime.min.time()).astimezone()
    except PipelineError:
        pass
    at = parse_iso(value)
    if at is None:
        raise PipelineError(f"Review date '{value}' not understood (use YYYY-MM-DD).")
    return at


# A review written on the snapshot page (_JS's Review): its rows, as JSON.
REVIEW_JSON_FORMAT = "minimalist-pipeline-review"


def keep_review(path: Path, snapshots: Path, plan: dict) -> Path | None:
    """A copy of an imported review, as it was sent: snapshots/reviews/
    <role>/<YYYY-MM>/ -- its role ("team", "no-role"), the month of its
    review date (else now). The same file already there is not copied
    again; another under the same name gets a number. None for a file
    already kept there (imported from reviews/). Raises OSError."""
    path = Path(path)
    reviews = Path(snapshots) / REVIEWS_DIRNAME
    if any(_same_path(parent, reviews) for parent in path.parents):
        return None
    role = TEAM_ROLE if plan.get("team") else plan.get("role") or "no-role"
    try:
        when = read_review(path)["review_date"]
    except PipelineError:
        when = None
    folder = month_folder(reviews / re.sub(r"[^\w\-]+", "_", role), when)
    target, n = folder / path.name, 1
    while target.exists():
        if filecmp.cmp(target, path, shallow=False):
            return target
        target, n = folder / f"{path.stem}_{n}{path.suffix}", n + 1
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return target


# What a review asks, one action each (the page's exportActions()):
#   validate / unvalidate  {file, department, seen}: as the review's role,
#                          seen the stable it looked at
#   rtk / note             {file, departments, text, shot, frames, render}:
#                          a line, its [sh020] [f12-40] read by the page
#   reply                  {file, to, text}: in that note's thread
#   fixed                  {file, id}: that retake done, as the reviewer
#   description            {file, old, new}: old the one exported
#   done                   {file, department, done}: that department done
#                          (or not) on the latest stable, no new version
#   still_done             {file, department, text}: its work holds, an
#                          earlier stage changed (not a validation)
#   departments            {file, add, remove}: the departments required
#   omit                   {file, state, reason}: on_hold / cancelled, ""
#                          counted again
#   assign                 {file, department, people}: who it's assigned
#                          to, all of them ([] none)
#   create                 {file (its name), kind, sequence + shot or prefix
#                          + name, description, frame_start, frame_end,
#                          departments, assignees {department: [names]}): a
#                          new shot or asset, made by the CSV
#                          batch's engine (lib/batch.py)
# See NOTES.md, "Review: typed actions".
ACTION_TYPES = (
    "validate", "unvalidate", "rtk", "note", "reply", "fixed", "description",
    "still_done", "departments", "omit", "assign", "create", "done",
)
# Changes to a file anyone may send (no role needed: none is a validation).
_FILE_CHANGES = ("done", "still_done", "departments", "omit", "assign")


def _text(value) -> str:
    return str(value if value is not None else "").strip()


def _action(raw) -> dict | None:
    """One action, its fields checked and cleaned; None for one not
    understood (left out)."""
    if not isinstance(raw, dict) or raw.get("type") not in ACTION_TYPES or not _text(raw.get("file")):
        return None
    t, a = raw["type"], {"type": raw["type"], "file": _text(raw["file"])}
    if t in ("validate", "unvalidate"):
        a.update(department=_text(raw.get("department")).lower(), seen=_text(raw.get("seen")))
        return a if a["department"] else None
    if t in ("rtk", "note"):
        frames = raw.get("frames")
        try:
            frames = (int(frames[0]), int(frames[1]) if frames[1] is not None else None) if frames else None
        except (TypeError, ValueError, IndexError):
            frames = None
        if frames and frames[1] is not None and frames[1] < frames[0]:
            frames = None
        deps = raw.get("departments") or []
        a.update(
            departments=[_text(d).lower() for d in deps if _text(d)] if isinstance(deps, list) else [],
            text=_text(raw.get("text")),
            shot=_text(raw.get("shot")) if str(raw.get("shot") or "").isdigit() else "",
            frames=frames,
            render=_text(raw.get("render")),
        )
        return a if a["text"] else None
    if t == "reply":
        a.update(to=_text(raw.get("to")), text=_text(raw.get("text")))
        return a if a["to"] and a["text"] else None
    if t == "fixed":
        a.update(id=_text(raw.get("id")))
        return a if a["id"] else None
    if t == "done":
        a.update(department=_text(raw.get("department")).lower(), done=raw.get("done") is not False)
        return a if a["department"] else None
    if t == "still_done":
        a.update(department=_text(raw.get("department")).lower(), text=_text(raw.get("text")))
        return a if a["department"] else None
    if t == "departments":
        pick = lambda k: [_text(d).lower() for d in raw.get(k) or [] if _text(d)] if isinstance(raw.get(k), list) else []  # noqa: E731
        a.update(add=pick("add"), remove=pick("remove"))
        return a if a["add"] or a["remove"] else None
    if t == "assign":
        people = raw.get("people") if isinstance(raw.get("people"), list) else []
        a.update(department=_text(raw.get("department")).lower(), people=[_text(p).lower() for p in people if _text(p)])
        return a if a["department"] else None
    if t == "omit":
        a.update(state=_text(raw.get("state")), reason=_text(raw.get("reason")))
        return a if a["state"] in ("", "on_hold", "cancelled") else None
    if t == "create":
        kind = _text(raw.get("kind"))
        deps = raw.get("departments") or []
        assignees = raw.get("assignees") if isinstance(raw.get("assignees"), dict) else {}
        a.update(
            kind=kind,
            description=_text(raw.get("description")),
            departments=[_text(d).lower() for d in deps if _text(d)] if isinstance(deps, list) else [],
            assignees={_text(d).lower(): [_text(p).lower() for p in people if _text(p)]
                       for d, people in assignees.items() if isinstance(people, list)},
        )
        if kind == "shot":
            a.update(sequence=_text(raw.get("sequence")), shot=_text(raw.get("shot")))
            for k in ("frame_start", "frame_end"):
                a[k] = int(raw[k]) if str(raw.get(k) or "").isdigit() else None
            return a if a["sequence"].isdigit() and re.fullmatch(r"\d+(-\d+)*", a["shot"]) else None
        if kind == "asset":
            a.update(prefix=_text(raw.get("prefix")).lower(), name=sanitize_name(_text(raw.get("name"))))
            return a if a["prefix"] and a["name"] != "unnamed" else None
        return None
    a.update(old=_text(raw.get("old")), new=_text(raw.get("new")))
    return a


def read_review(path: Path) -> dict:
    """{"schema_version", "author", "role", "review_date", "actions"} from
    a review downloaded from the snapshot page: {"format",
    "schema_version", "author", "role", "review_date", "actions": [...]}
    (ACTION_TYPES), each checked by _action()."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PipelineError(f"Could not read {Path(path).name}: {e}")
    if not isinstance(data, dict) or data.get("format") != REVIEW_JSON_FORMAT:
        raise PipelineError(
            f"{Path(path).name} isn't a review downloaded from a snapshot page."
        )
    schema = data.get("schema_version")
    if not isinstance(schema, int):
        raise PipelineError(f"{Path(path).name}: no schema_version.")
    _check_schema(path, schema)
    actions = [a for a in map(_action, data.get("actions") or []) if a]
    return {
        "schema_version": schema,
        "author": _text(data.get("author")),
        "role": _text(data.get("role")).lower(),
        "review_date": parse_review_date(_text(data.get("review_date"))),
        "actions": actions,
    }


def _check_schema(path: Path, schema: int) -> None:
    """Refuse a review made from another addon version's snapshot (see
    NOTES.md, "Review import: this version's reviews only")."""
    if schema > SCHEMA_VERSION:
        raise PipelineError(
            f"{Path(path).name} comes from a newer addon version (review "
            f"v{schema}); update the addon to import it."
        )
    if schema < SCHEMA_VERSION:
        raise PipelineError(
            f"{Path(path).name} comes from an older snapshot (review v{schema}): "
            "export the snapshot again and review it there."
        )


def _by_file(actions: list, *types: str) -> dict:
    """{file: [its actions of those types, in order]}."""
    out: dict = {}
    for a in actions:
        if a["type"] in types:
            out.setdefault(a["file"], []).append(a)
    return out


def _file_shots(filepath: Path) -> list[str]:
    """The shot numbers of a shot's .blend, padded ("010", "020" for a
    block); [] for an asset."""
    parsed = parse_filename(filepath.name) or {}
    if not parsed.get("shot"):
        return []
    digits = json_get(ConfigCache.get(), "naming.shot.digits", 3)
    try:
        return [f"{n:0{digits}d}" for n in shots_in_segment(parsed["shot"])]
    except ValueError:
        return []


# "note:" -- or "n:", any case -- at a reply's lines' start: a remark.
_NOTE_PREFIX = re.compile(r"^(\s*(?:\[[^\]]*\]\s*)*)(?:note|n)\s*:\s*", re.IGNORECASE)


def _reply_kind(text: str) -> tuple[str, str]:
    """A reply as it's imported: (type, text). Every line "note:" -- a
    remark, the prefix dropped; else a retake, "still to redo"."""
    lines = [line for line in text.splitlines() if line.strip()]
    if lines and all(_NOTE_PREFIX.match(line) for line in lines):
        return "note", "\n".join(_NOTE_PREFIX.sub(r"\1", line, count=1) for line in lines)
    return "rtk", text


def _review_file(name: str) -> Path | None:
    """The .blend an action's file names, None if it's gone."""
    try:
        return find_file_by_name(name if name.endswith(".blend") else f"{name}.blend")
    except PipelineError:  # unknown prefix...
        return None


def _notes_of(filepath: Path, notes: list) -> list[dict]:
    """A file's rtk / note actions as they're imported: {"text",
    "departments", "type", "shot", "frames", "key", "render"} -- its
    departments the file's (unknown dropped), its shot one of the block's
    (else back in its text as typed). The same for the confirm dialog's
    count and the import, so both tell an already imported one alike."""
    shots = _file_shots(filepath)
    prefix = json_get(ConfigCache.get(), "naming.shot.prefix", "sh")
    out = []
    for a in notes:
        departments = []
        for dep in a["departments"]:
            try:
                if valid_department(filepath, dep):
                    departments.append(dep)
            except PipelineError:
                pass
        text, shot = a["text"], None
        if a["shot"]:
            shot = next((s for s in shots if int(s) == int(a["shot"])), None)
            if shot is None:
                text = f"[{prefix}{a['shot']}] {text}"
        frames = a["frames"]
        key = _note_key(text, shot, *(frames or (None, None)), departments)
        out.append(
            {"text": text, "departments": departments, "type": a["type"], "shot": shot,
             "frames": frames, "key": key, "render": a["render"]}
        )
    return out


def review_import_plan(path: Path, review: dict | None = None) -> dict:
    """What importing a review would do, read only (its confirm dialog):
    {"role", "team", "author", "notes", "fixed", "replies", their "*_known"
    / "fixed_done" counts, "validations" (changes only), "refused":
    [(label, reason)]}. Raises PipelineError without a Role, or one that is
    neither a validation role nor "team"."""
    review = review or read_review(path)
    role = review["role"]
    roles = {r["name"] for r in validation_roles()}
    team = role == TEAM_ROLE and role not in roles
    actions = review["actions"]
    count = lambda *types: sum(a["type"] in types for a in actions)  # noqa: E731
    plan = {
        "role": role,
        # Written as the team: no role on its notes, no validation.
        "team": team,
        "author": review["author"] or "prod",
        "notes": count("rtk", "note"),
        "validations": [],
        "refused": [],
        # Retakes the reviewer marked fixed: closed under their name.
        "fixed": count("fixed"),
        # Still done, departments required, set aside.
        "changes": count(*_FILE_CHANGES),
        # New shots and assets, made after the import (create_rows()).
        "creates": count("create"),
        "replies": count("reply"),
        # What the project holds already (a review imported again), left as
        # it is: counted here as the import will tell it.
        "notes_known": 0,
        "replies_known": 0,
        "fixed_done": 0,
        "validations_known": 0,
    }
    author = plan["author"]
    for name, mine in _by_file(actions, "rtk", "note", "fixed", "reply").items():
        filepath = _review_file(name)
        if not filepath:
            continue
        notes = [a for a in mine if a["type"] in ("rtk", "note")]
        if notes:
            known = _known_notes(
                filepath, author, TEAM_REVIEW_SOURCE if team else REVIEW_SOURCE
            )
            for n in _notes_of(filepath, notes):
                plan["notes_known"] += n["key"] in known
                known.add(n["key"])
        entries = (read_json_quiet(tracking_json_path(filepath)) or {}).get("entries", [])
        by_id = {e.get("id"): e for e in entries}
        plan["fixed_done"] += sum(
            1 for a in mine if a["type"] == "fixed" and (by_id.get(a["id"]) or {}).get("done")
        )
        answered = {
            (e.get("response"), e.get("text"))
            for e in entries
            if e.get("response") and e.get("author") == author
        }
        plan["replies_known"] += sum(
            1 for a in mine if a["type"] == "reply" and (a["to"], _reply_kind(a["text"])[1]) in answered
        )
    # Anything under the role: it must be one (descriptions don't need it).
    if plan["notes"] or plan["replies"] or count("validate", "unvalidate"):
        if not role:
            raise PipelineError(
                f"{Path(path).name}: no Role chosen at the top -- pick one, then import again."
            )
        if role not in roles and not team:
            raise PipelineError(
                f"{Path(path).name}: '{role}' isn't one of this project's validation roles "
                f"({', '.join(sorted(roles)) or 'none'}), nor team."
            )
    worked_since: dict = {}
    # Done on the stable by this same review (a "done" action, applied
    # first): validated with it.
    marked = {(a["file"], a["department"]) for a in actions if a["type"] == "done" and a["done"]}
    for name, mine in _by_file(actions, "validate", "unvalidate").items():
        # The last word on a department wins.
        wanted = {a["department"]: "yes" if a["type"] == "validate" else "no" for a in mine}
        seen = next((a["seen"] for a in mine if a["seen"]), "")
        filepath = _review_file(name)
        raw = _collect_folder(filepath.parent) if filepath else None
        if not raw:
            plan["refused"] += [(f"{name}: {d}", "file not found") for d in wanted]
            continue
        status = _status_from_raw(raw)
        done_now = status.get("validated_departments", {})
        given = status.get("approvals") or {}
        current = Path((status.get("stable_info") or {}).get("file") or "").stem
        for department, choice in sorted(wanted.items()):
            label = f"{name}: {department}"
            if choice == "no" and role not in (given.get(department) or {}):
                continue  # nothing to withdraw (a retake on unvalidated work)
            if team:
                plan["refused"].append((label, "the team doesn't validate: a validation role does"))
            elif choice == "yes" and role in (given.get(department) or {}):
                plan["validations_known"] += 1  # given already: left as is
            elif department not in status.get("departments_required", []):
                plan["refused"].append((label, "department not required"))
            elif seen and current and seen != current and _worked(
                worked_since, name, filepath, seen, department
            ):
                # Not refused while untouched since: what was seen is still there.
                plan["refused"].append(
                    (label, f"{current} made since {seen}, {department} worked: to review again")
                )
            elif choice == "yes" and department not in done_now and (name, department) not in marked:
                plan["refused"].append((label, "not done (yet, or any more)"))
            else:
                plan["validations"].append(
                    {
                        "name": name,
                        "filepath": str(filepath),
                        "department": department,
                        "approved": choice == "yes",
                        "stable": f"{seen}.blend" if seen else None,
                    }
                )
    return plan


def _worked(cache: dict, name: str, filepath: Path, seen: str, department: str) -> bool:
    """Whether department was worked since the stable the review saw (or
    that stable is unknown): its validation is to review again."""
    if name not in cache:
        cache[name] = worked_since_stable(filepath.parent, seen)
    worked = cache[name]
    return worked is None or department in worked


def _known_notes(filepath: Path, author: str, source: str = REVIEW_SOURCE) -> set:
    """The notes this author's reviews (source: the prod's, or the team's)
    already brought into filepath's tracking, by _note_key()."""
    return {
        _note_key(
            e.get("text"),
            e.get("shot"),
            e.get("frame_start"),
            e.get("frame_end"),
            e.get("departments") or [],
        )
        for e in (read_json_quiet(tracking_json_path(filepath)) or {}).get("entries", [])
        if e.get("source") == source and e.get("author") == author
    }


def _note_key(text, shot, f_start, f_end, departments) -> tuple:
    """What makes an imported review line the same as one already there."""
    return (
        text,
        shot or None,
        f_start,
        f_end if f_start is not None else None,
        frozenset(d for d in departments or () if d),
    )


def import_review(path: Path, review: dict | None = None) -> dict:
    """Write a review into the project (review_import_plan() says what),
    each action by its type: the retakes marked fixed closed, the replies
    in their threads, the validations, one entry per rtk / note under its
    role. One already imported is skipped. Returns {"imported",
    "duplicates", "validated", "same_validations", "fixed",
    "already_fixed", "replies", "changed", "skipped": [(label, reason)]}.
    review: read_review()'s, already read -- the live page's actions (path
    a label then)."""
    review = review or read_review(path)
    plan = review_import_plan(path, review)
    team = plan["team"]
    role = None if team else plan["role"] or None
    # Where its notes come from: a prod review ("prod review" on them), or
    # the team's.
    source = TEAM_REVIEW_SOURCE if team else REVIEW_SOURCE
    author = review["author"] or "prod"
    date = review["review_date"]
    created_at = date.isoformat(timespec="seconds") if date else None
    review_id = hashlib.sha1(f"{now()}{Path(path).name}".encode()).hexdigest()[:5]
    actions = review["actions"]
    result = {
        "imported": 0,
        "duplicates": 0,
        "validated": 0,
        "fixed": 0,
        "replies": 0,
        # Already so, left as it is (a review imported again): retakes done
        # since, validations already given.
        "already_fixed": 0,
        # Given already: the plan left them out of its changes.
        "same_validations": plan["validations_known"],
        # Still done, departments required, set aside.
        "changed": 0,
        "skipped": list(plan["refused"]),
    }
    # Retakes marked fixed: done, as the reviewer -- one already done, or
    # gone since, left as it is.
    for name, mine in _by_file(actions, "fixed").items():
        filepath = _review_file(name)
        if not filepath:
            result["skipped"].append((f"{name}: {len(mine)} retake(s) fixed", "file not found"))
            continue
        for a in mine:
            try:
                closed = close_entry(filepath, a["id"], author)
                if closed:
                    result["fixed"] += 1
                elif closed is False:
                    result["already_fixed"] += 1
                else:
                    result["skipped"].append((f"{name}: retake fixed", "its note is gone"))
            except PipelineError as e:
                result["skipped"].append((f"{name}: retake fixed", e.message))
    # Replies: each in its entry's thread, a note under the review's role --
    # the retake it answers left open. The same reply from the same author
    # once only (an import run twice).
    for name, mine in _by_file(actions, "reply").items():
        filepath = _review_file(name)
        if not filepath:
            result["skipped"].append((f"{name}: {len(mine)} reply(ies)", "file not found"))
            continue
        entries = (read_json_quiet(tracking_json_path(filepath)) or {}).get("entries", [])
        by_id = {e.get("id"): e for e in entries}
        known = {
            (e.get("response"), e.get("text"))
            for e in entries
            if e.get("response") and e.get("author") == author
        }
        for a in mine:
            if a["to"] not in by_id:
                result["skipped"].append((f"{name}: reply {a['text'][:30]}", "its note is gone"))
                continue
            # A retake answering it is on its departments (none: the whole
            # file's); a "note:" one, a remark.
            entry_type, text = _reply_kind(a["text"])
            if (a["to"], text) in known:
                result["duplicates"] += 1
                continue
            departments = entry_departments(by_id[a["to"]]) if entry_type == "rtk" else []
            try:
                create_entry(
                    filepath,
                    text=text,
                    departments=departments,
                    author=author,
                    type=entry_type,
                    response=a["to"],
                    review_id=review_id,
                    created_at=created_at,
                    source=source,
                    role=role,
                )
                known.add((a["to"], text))
                result["replies"] += 1
            except PipelineError as e:
                result["skipped"].append((f"{name}: reply", e.message))
    # The file's own changes: still done, its departments, set aside.
    for name, mine in _by_file(actions, *_FILE_CHANGES).items():
        filepath = _review_file(name)
        if not filepath:
            result["skipped"] += [(f"{name}: {a['type'].replace('_', ' ')}", "file not found") for a in mine]
            continue
        for a in mine:
            label = f"{name}: {a['type'].replace('_', ' ')}"
            try:
                if a["type"] == "done":
                    if a["department"] not in get_departments_required(filepath):
                        result["skipped"].append((label, f"{a['department']} not required"))
                        continue
                    if not set_department_done(filepath, a["department"], a["done"]):
                        continue  # as asked already
                elif a["type"] == "still_done":
                    if a["department"] not in get_departments_required(filepath):
                        result["skipped"].append((label, f"{a['department']} not required"))
                        continue
                    set_department_synced(filepath, a["department"], author, a["text"])
                elif a["type"] == "departments":
                    if not set_departments_required(filepath, a["add"], a["remove"]):
                        continue  # as asked already
                elif a["type"] == "assign":
                    if a["department"] not in get_departments_required(filepath):
                        result["skipped"].append((label, f"{a['department']} not required"))
                        continue
                    set_department_assignees(filepath, a["department"], a["people"])
                else:
                    set_file_omit(filepath, a["state"], author, a["reason"])
                result["changed"] += 1
            except PipelineError as e:
                result["skipped"].append((label, e.message))
    for v in plan["validations"]:
        try:
            if set_department_approval(
                Path(v["filepath"]),
                department=v["department"],
                role=role,
                approved=v["approved"],
                user=author,
                stable_file=v["stable"],
            ):
                result["validated"] += 1
            else:
                result["same_validations"] += 1
        except PipelineError as e:
            result["skipped"].append((f"{v['name']}: {v['department']}", e.message))
    # One rtk / note = one entry (see NOTES.md, "Batched review input, still
    # one entry each"). The same words on another shot, frames or
    # department are another one: "[sh170] too dark", "[sh180] too dark".
    for name, mine in _by_file(actions, "rtk", "note").items():
        filepath = _review_file(name)
        if not filepath:
            result["skipped"].extend(
                (f"{name}: {a['text'][:40]}", "file not found (renamed, branched or archived?)")
                for a in mine
            )
            continue
        known = _known_notes(filepath, author, source)
        for n in _notes_of(filepath, mine):
            if n["key"] in known:
                result["duplicates"] += 1
                continue
            # The version the reviewer watched: the one its render was made
            # from (v007-stable_001 -> ..._v007-stable.blend), else the file.
            render = render_of_note(n["render"], n["shot"])
            watched = filepath
            if render:
                version = render.rsplit("_", 1)[0]
                watched = filepath.with_name(f"{filepath.stem.rsplit('_', 1)[0]}_{version}.blend")
            frames = n["frames"]
            try:
                create_entry(
                    filepath,
                    text=n["text"],
                    departments=n["departments"],
                    author=author,
                    type=n["type"],
                    shot=n["shot"],
                    f_start=frames[0] if frames else None,
                    f_end=frames[1] if frames else None,
                    review_id=review_id,
                    created_at=created_at,
                    referenced_version=str(watched),
                    render=render,
                    source=source,
                    role=role,
                )
                known.add(n["key"])
                result["imported"] += 1
            except PipelineError as e:
                result["skipped"].append((f"{name}: {n['text'][:40]}", e.message))
    return result


def review_description_changes(path: Path) -> list[dict]:
    """[{"name", "filepath", "old", "new"}] for every description action
    the prod changed (new differs from the one exported) that still
    differs from the file's current one; an empty one is no change."""
    changes, seen = [], set()
    for a in read_review(path)["actions"]:
        name, new = a["file"], a.get("new", "")
        if a["type"] != "description" or not new or name in seen:
            continue
        seen.add(name)
        if new == a["old"]:
            continue  # untouched by the prod, whatever happened since
        filepath = _review_file(name)
        if not filepath:
            continue  # reported by import_review() already
        old = ((read_json_quiet(tracking_json_path(filepath)) or {}).get("description") or "").strip()
        if new != old:
            changes.append({"name": name, "filepath": str(filepath), "old": old, "new": new})
    return changes


def create_rows(review: dict) -> dict:
    """The review's new shots and assets as the CSV batch's rows ({"asset":
    [...], "shot": [...]}, lib/batch.py): M_PIPELINE_OT_batch_create makes
    them, skipping one that exists (the same review imported twice). The
    reviewer and their role in each one's description."""
    out = {"asset": [], "shot": []}
    who = " / ".join(x for x in (review.get("author"), review.get("role")) if x)
    for a in review["actions"]:
        if a["type"] != "create":
            continue
        description = a["description"] + (f" (asked by {who})" if who else "")
        row = {"departments": ", ".join(a["departments"]), "description": description.strip()}
        if a.get("assignees"):
            row["assignees"] = a["assignees"]
        if a["kind"] == "shot":
            row.update(sequence=a["sequence"], shot=a["shot"])
            row.update({k: str(a[k]) for k in ("frame_start", "frame_end") if a[k] is not None})
        else:
            row.update(prefix=a["prefix"], name=a["name"])
        out[a["kind"]].append(row)
    return out
