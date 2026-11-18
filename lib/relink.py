"""Update links: a file's outdated links moved to their latest stables
without opening it, in a new version tagged -relink (plan 8.4).

- The source is the file's newest version, wip or stable; the new one is
  the next number, "<name>_v006-relink.blend" -- never saved over, a
  stable never touched. Not a stable itself: what links this file takes
  it once someone marks it stable (a person checks the relink broke
  nothing).
- A version someone has open to work on (a live lock) is left: relinking
  it would fork their work.
- No Blender: the source's library blocks read and the copy's paths
  written straight in the file (lib/blendfile.py), in a thread -- a scene
  of several GB in a moment (a compressed one is read whole). Before a
  library moves, the newer stable is read too: it must still hold every
  piece of data the file links from it (by name, as Blender finds linked
  data), else that link is kept and said. poll() on the live page's turn
  writes the new version's .wipmeta (its links, creation_mode "relink").
  No work session: no department worked, no work time, nothing "to redo"
  downstream. See NOTES.md, "Reading a .blend without Blender".
"""

import os
import threading
import time
from pathlib import Path

from . import blendfile
from .config import RELINK_TAG, ConfigCache, parse_filename
from .core import json_get, read_json_quiet
from .logs import log
from .tracking import (
    _meta_path,
    _outdated_links_of,
    create_wipmeta,
    open_elsewhere,
)

# owner key (its path under the project, posix) -> {"state": "running" |
# "done" | "failed", "message", "file", "at", and while running "proc",
# "request", "source", "out", "linked"}
_jobs: dict[str, dict] = {}
KEEP_SECONDS = 600  # a finished one stays said this long


def _versions(owner: Path) -> list[tuple[int, str | None, Path]]:
    """(number, tag, path) of owner's versioned .blend files."""
    out = []
    try:
        entries = list(os.scandir(owner))
    except OSError:
        return out
    for e in entries:
        if e.name.endswith(".blend"):
            parsed = parse_filename(e.name)
            if parsed:
                out.append((int(parsed["number"]), parsed.get("tag"), Path(e.path)))
    return sorted(out, key=lambda v: v[0])


def relink_plan(root: Path, owner: Path) -> dict:
    """What Update links would do for owner: {"source", "out", "mapping"
    [(old, new) absolute paths], "linked" (the new version's list, project
    -relative), "error"}. error set (and nothing to do) when it can't."""
    root, owner = Path(root), Path(owner)
    versions = _versions(owner)
    if not versions:
        return {"error": "no version of it"}
    number, tag, source = versions[-1]
    suffix = ".stablemeta" if tag == "stable" else ".wipmeta"
    meta = read_json_quiet(_meta_path(source, suffix)) or {}
    linked = [d["file"] for d in meta.get("linked") or [] if isinstance(d, dict) and d.get("file")]
    v_prefix = json_get(ConfigCache.get(), "naming.version.prefix", "v")
    outdated = dict(_outdated_links_of(root, [owner], {str(owner): linked}, v_prefix).get(str(owner)) or [])
    if not outdated:
        return {"error": "its links are up to date"}
    if source.name in open_elsewhere(owner):
        return {"error": f"{source.name} is open to work on: left as it is"}
    mapping, new_linked = [], []
    for f in linked:
        path = Path(f) if Path(f).is_absolute() else root / f
        newest = outdated.get(path.name)
        if newest:
            mapping.append((str(path), str(path.with_name(newest))))
            path = path.with_name(newest)
        try:
            new_linked.append({"file": path.relative_to(root).as_posix()})
        except ValueError:
            new_linked.append({"file": str(path)})
    digits = json_get(ConfigCache.get(), "naming.version.digits", 3)
    base = source.name.rsplit("_", 1)[0]
    out = owner / f"{base}_{v_prefix}{number + 1:0{digits}d}-{RELINK_TAG}.blend"
    return {"source": source, "out": out, "mapping": mapping, "linked": new_linked, "error": ""}


def start(root: Path, owners: list[Path]) -> dict:
    """Update links on each owner (a thread each, not waited on). Returns
    {"started": [names], "skipped": [[name, why]]}."""
    started, skipped = [], []
    for owner in owners:
        key = _key(root, owner)
        job = _jobs.get(key)
        if job and job["state"] == "running":
            skipped.append([owner.name, "already updating"])
            continue
        plan = relink_plan(root, owner)
        if plan["error"]:
            skipped.append([owner.name, plan["error"]])
            continue
        job = {
            "state": "running", "message": f"{plan['source'].name} → {plan['out'].name}",
            "file": plan["out"].stem, "at": time.monotonic(), "result": None,
            "source": plan["source"], "out": plan["out"], "linked": plan["linked"], "mapping": plan["mapping"], "root": Path(root),
        }
        job["thread"] = threading.Thread(target=_run, args=(job,), daemon=True, name="pipeline-relink")
        _jobs[key] = job
        job["thread"].start()
        log("INFO", "relink", f"Update links: {plan['source'].name} -> {plan['out'].name} ({len(plan['mapping'])} link(s))")
        started.append(owner.name)
    return {"started": started, "skipped": skipped}


def poll() -> bool:
    """The finished background Blenders read back (main thread: the new
    version's .wipmeta written here). True when a job changed state."""
    changed = False
    clock = time.monotonic()
    for key, job in list(_jobs.items()):
        if job["state"] != "running":
            if clock - job["at"] > KEEP_SECONDS:
                del _jobs[key]
                changed = True
            continue
        if job["result"] is None:
            continue
        result = job["result"]
        out = job["out"]
        if result.get("status") == "ok" and out.is_file():
            try:
                kept = {os.path.normcase(k) for k in result.get("kept") or []}
                linked = [_kept_link(d, job["mapping"], kept, job["root"]) for d in job["linked"]]
                create_wipmeta(filepath=out, original_filepath=job["source"], creation_mode="relink", linked=linked)
                job.update(state="done", message=f"{out.name}: {result.get('message', '')}")
                log("SUCCESS", "relink", f"Update links: {out.name} ({result.get('message', '')})")
            except Exception as e:
                job.update(state="failed", message=f"{out.name} saved, its .wipmeta not: {e}")
                log("WARNING", "relink", job["message"])
        else:
            why = result.get("message") or "not updated"
            job.update(state="failed", message=why)
            log("WARNING", "relink", f"Update links: {job['source'].name} not updated: {why}")
        for k in ("thread", "result", "source", "out", "linked", "mapping", "root"):
            job.pop(k, None)
        job["at"] = clock
        changed = True
    return changed


def _run(job: dict) -> None:
    """The work, in a thread: the source's libraries read, those of the
    mapping repointed (when their new stable still has what's linked from
    them), the copy written. Sets job["result"]: {"status", "message",
    "kept": [old paths left as they were]}."""
    try:
        source, out = Path(job["source"]), Path(job["out"])
        if out.exists():
            raise blendfile.BlendError(f"{out.name} exists already")
        mapping = {os.path.normcase(os.path.normpath(o)): Path(n) for o, n in job["mapping"]}
        blend = blendfile.read(source)
        paths, done, kept = {}, [], []
        has: dict[str, set] = {}
        for lib in blend.libraries:
            if not lib["direct"]:
                continue
            old = blendfile.resolve(lib["raw"], source.parent)
            new = mapping.get(os.path.normcase(os.path.normpath(str(old))))
            if new is None:
                continue
            key = os.path.normcase(str(new))
            if key not in has:
                b = blendfile.read(new)
                has[key] = b.local.union(*b.linked.values())
            missing = sorted(blend.linked.get(lib["old"], set()) - has[key])
            if missing:
                kept.append(str(old))
                shown = ", ".join(m[2:] for m in missing[:4]) + ("..." if len(missing) > 4 else "")
                done.append(f"{old.name} kept: {new.name} has no {shown}")
                continue
            if lib["raw"].startswith(b"//"):
                nb = ("//" + os.path.relpath(new, out.parent).replace("\\", "/")).encode("utf-8")
            else:
                nb = str(new).encode("utf-8")
            if len(nb) >= lib["size"]:
                kept.append(str(old))
                done.append(f"{old.name} kept: path too long")
                continue
            paths[lib["pos"]] = (lib["size"], nb)
            done.append(f"{old.name} -> {new.name}")
        if not paths:
            raise blendfile.BlendError("; ".join(done) or "none of its libraries is one of the links to update")
        blendfile.write_copy(source, out, paths)
        moved = len(paths)
        job["result"] = {"status": "ok", "message": f"{moved} link(s): " + "; ".join(done), "kept": kept}
    except Exception as e:  # said on the page, never lost in a thread
        job["result"] = {"status": "error", "message": str(e)}


def _kept_link(entry: dict, mapping: list, kept: set, root: Path) -> dict:
    """A link of the new version's list put back to its old file when the
    relink kept it (its new stable lost linked data)."""
    for old, new in mapping:
        if os.path.normcase(old) not in kept:
            continue
        try:
            if entry.get("file") == Path(new).relative_to(root).as_posix():
                return {"file": Path(old).relative_to(root).as_posix()}
        except ValueError:
            if entry.get("file") == str(new):
                return {"file": str(old)}
    return entry


def states() -> dict:
    """{owner key: {"state", "message", "file"}} for the page."""
    return {k: {x: j[x] for x in ("state", "message", "file")} for k, j in _jobs.items()}


def _key(root: Path, owner: Path) -> str:
    try:
        return Path(owner).relative_to(root).as_posix()
    except ValueError:
        return str(owner)
