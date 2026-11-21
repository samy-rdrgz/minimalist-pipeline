"""A review's import undone: what it changed, written beside the review
kept in snapshots/reviews/ as <review>.revert.json, then put back on
demand (Project settings > Maintenance > Revert a review...).

Not one undo per action type: the files an import may touch -- each named
file's tracking.json and .stablemeta -- read before and after it, and what
differs written down, so whatever an action does (a validation dropped
with its done, an assignee replaced...) comes back as it was:
- "entries" (tracking.json's): the ids added (to delete), the entries
  removed (to put back, whole), the entries changed (before / after);
- "keys": any other value, by its path in the file ("departments_done",
  "rig"), before / after (a key absent: no "before" / no "after").

Put back only where nothing changed since: an entry added and since
edited, answered or closed, a value someone changed again -- left as it
is, named in the result. The files a review created (its "create"
actions) are listed, never deleted. The live page's changes have their
own undo (the page's Take back): no .revert.json for them.

Pure os/json reads; the writes under locked_json() (main thread)."""

from __future__ import annotations

import json
from pathlib import Path

from ..config import get_active_project_root
from ..core import locked_json, now, read_json_quiet
from ..errors import PipelineError
from ..formats import KEY as FORMAT_KEY
from .tracking import tracking_json_path

SUFFIX = ".revert.json"
_ENTRIES = "entries"


def _files_of(review: dict) -> list[Path]:
    """The project files an import of review may write: each named file's
    tracking.json and .stablemeta (the latest and the older ones)."""
    from .review_import import _review_file

    out, seen = [], set()
    for name in dict.fromkeys(a["file"] for a in review.get("actions") or []):
        blend = _review_file(name)
        if not blend:
            continue
        tracking = tracking_json_path(blend)
        folder = tracking.parent
        for p in [tracking, *sorted(folder.glob("*.stablemeta"))] if folder.is_dir() else [tracking]:
            if str(p) not in seen:
                seen.add(str(p))
                out.append(p)
    return out


def state_before(review: dict) -> dict[str, object]:
    """The files review's import may change, as they are now: {path: data}
    (None for a file not there)."""
    return {str(p): read_json_quiet(p) for p in _files_of(review)}


def _diff_keys(before, after, path: list, out: list) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for k in dict.fromkeys([*before, *after]):
            if not path and k in (_ENTRIES, FORMAT_KEY):
                continue
            b, a = before.get(k, _ABSENT), after.get(k, _ABSENT)
            if b != a:
                _diff_keys(b, a, [*path, k], out)
        return
    change = {"path": path}
    if before is not _ABSENT:
        change["before"] = before
    if after is not _ABSENT:
        change["after"] = after
    out.append(change)


class _Absent:
    pass


_ABSENT = _Absent()


def _diff_entries(before: list, after: list) -> dict:
    b = {e.get("id"): e for e in before if isinstance(e, dict)}
    a = {e.get("id"): e for e in after if isinstance(e, dict)}
    out = {
        "added": [a[i] for i in a if i not in b],
        "removed": [b[i] for i in b if i not in a],
        "changed": [{"before": b[i], "after": a[i]} for i in a if i in b and a[i] != b[i]],
    }
    return {k: v for k, v in out.items() if v}


def changes_since(before: dict[str, object]) -> list[dict]:
    """What changed in the files state_before() read: one change per file,
    {"file", "entries", "keys"}; [] if nothing."""
    out = []
    for path, old in before.items():
        new = read_json_quiet(path)
        if new == old:
            continue
        old_d, new_d = old if isinstance(old, dict) else {}, new if isinstance(new, dict) else {}
        keys: list = []
        _diff_keys(old_d, new_d, [], keys)
        entries = _diff_entries(old_d.get(_ENTRIES) or [], new_d.get(_ENTRIES) or [])
        if keys or entries:
            out.append({"file": path, "entries": entries, "keys": keys})
    return out


def _relative(path: str, root: Path | None) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix() if root else path
    except ValueError:
        return path


def write_revert(beside: Path, review: dict, changes: list[dict]) -> Path | None:
    """<beside's name>.revert.json beside it: the review's changes, to undo.
    A number added when one is there already (a review imported twice).
    None, nothing written, when it changed nothing. Raises OSError."""
    created = [a["file"] for a in review.get("actions") or [] if a.get("type") == "create"]
    if not changes and not created:
        return None
    root = get_active_project_root()
    data = {
        FORMAT_KEY: "2.0.0",
        "review": Path(beside).name,
        "author": review.get("author") or "",
        "role": review.get("role") or "",
        "imported_at": now(),
        "created": created,
        "changes": [{**c, "file": _relative(c["file"], root)} for c in changes],
    }
    beside = Path(beside)
    target, n = beside.with_name(beside.stem + SUFFIX), 2
    while target.exists():
        target, n = beside.with_name(f"{beside.stem}_{n}{SUFFIX}"), n + 1
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def revert_files(snapshots: Path) -> list[Path]:
    """Every .revert.json under snapshots/reviews/, the latest import first."""
    from .snapshot import REVIEWS_DIRNAME

    found = list((Path(snapshots) / REVIEWS_DIRNAME).rglob("*" + SUFFIX))
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def read_revert(path: Path) -> dict:
    data = read_json_quiet(path)
    if not isinstance(data, dict) or not isinstance(data.get("changes"), list):
        raise PipelineError(f"{Path(path).name}: not a review's undo.")
    return data


def summary(data: dict) -> dict:
    """{"entries_added", "entries_removed", "entries_changed", "values",
    "files", "created"}: what an undo would put back."""
    s = {"entries_added": 0, "entries_removed": 0, "entries_changed": 0, "values": 0, "files": 0}
    for c in data.get("changes") or []:
        s["files"] += 1
        e = c.get("entries") or {}
        s["entries_added"] += len(e.get("added") or [])
        s["entries_removed"] += len(e.get("removed") or [])
        s["entries_changed"] += len(e.get("changed") or [])
        s["values"] += len(c.get("keys") or [])
    s["created"] = list(data.get("created") or [])
    return s


def _get(d, path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return _ABSENT
        d = d[k]
    return d


def _set(d: dict, path: list, change: dict) -> None:
    for k in path[:-1]:
        if not isinstance(d.get(k), dict):
            d[k] = {}
        d = d[k]
    if "before" in change:
        d[path[-1]] = change["before"]
    else:
        d.pop(path[-1], None)


def _label(path: str) -> str:
    p = Path(path)
    return f"{p.parent.parent.name}/{p.name}"


def apply_revert(path: Path, user: str) -> dict:
    """Put back what the review's import changed, where nothing changed
    since. Returns {"put_back", "skipped": [(label, reason)], "created"}.
    The .revert.json then says it was reverted (by, at, what was left)."""
    data = read_revert(path)
    if data.get("reverted"):
        raise PipelineError(f"{data.get('review')}: already reverted ({data['reverted'].get('at', '')[:16]}).")
    root = get_active_project_root()
    done, skipped = 0, []
    for c in data["changes"]:
        target = Path(c["file"])
        if not target.is_absolute() and root:
            target = Path(root) / target
        where = _label(str(target))
        try:
            with locked_json(target) as box:
                cur = box["data"] if isinstance(box["data"], dict) else {}
                n = 0
                for k in c.get("keys") or []:
                    now_v = _get(cur, k["path"])
                    want = k["after"] if "after" in k else _ABSENT
                    if now_v != want:
                        skipped.append((f"{where}: {' > '.join(map(str, k['path']))}", "changed again since"))
                        continue
                    _set(cur, k["path"], k)
                    n += 1
                e = c.get("entries") or {}
                if e:
                    entries = list(cur.get(_ENTRIES) or [])
                    by_id = {x.get("id"): x for x in entries if isinstance(x, dict)}
                    added_ids = {x.get("id") for x in e.get("added") or []}
                    drop = set()
                    for x in e.get("added") or []:
                        i = x.get("id")
                        if i not in by_id:
                            continue  # gone already
                        if by_id[i] != x:
                            skipped.append((f"{where}: {(x.get('text') or i)[:40]}", "edited, answered or closed since"))
                            continue
                        if any(y.get("response") == i and y.get("id") not in added_ids for y in entries):
                            skipped.append((f"{where}: {(x.get('text') or i)[:40]}", "someone replied to it since"))
                            continue
                        drop.add(i)
                    entries = [x for x in entries if x.get("id") not in drop]
                    n += len(drop)
                    for ch in e.get("changed") or []:
                        i = ch["after"].get("id")
                        for j, x in enumerate(entries):
                            if x.get("id") == i:
                                if x == ch["after"]:
                                    entries[j] = ch["before"]
                                    n += 1
                                else:
                                    skipped.append((f"{where}: {(x.get('text') or i)[:40]}", "changed again since"))
                                break
                    have = {x.get("id") for x in entries}
                    for x in e.get("removed") or []:
                        if x.get("id") not in have:
                            entries.append(x)
                            n += 1
                    cur[_ENTRIES] = entries
                if n:
                    box["data"], box["action"] = cur, "to_write"
                done += n
        except PipelineError as err:
            skipped.append((where, err.message))
    data["reverted"] = {"at": now(), "by": user, "put_back": done, "skipped": [list(s) for s in skipped]}
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"put_back": done, "skipped": skipped, "created": list(data.get("created") or [])}
