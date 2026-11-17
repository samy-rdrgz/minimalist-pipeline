"""Update links: a file's outdated links moved to their latest stables
without opening it, in a new version tagged -updatelink (plan 8.4).

- The source is the file's newest version, wip or stable; the new one is
  the next number, "<name>_v006-updatelink.blend" -- never saved over, a
  stable never touched. Not a stable itself: what links this file takes
  it once someone marks it stable (a person checks the relink broke
  nothing).
- A version someone has open to work on (a live lock) is left: relinking
  it would fork their work.
- Done in a disposable background Blender (templates/relink_entry.py,
  --factory-startup: none of the addon's handlers there -- no session, no
  lock, no auto-version), this Blender never waits for it: poll() on its
  timer reads the result, then writes the new version's .wipmeta (its
  links, creation_mode "relink"). No work session: no department worked,
  no work time, nothing "to redo" downstream.
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from .config import RELINK_TAG, ConfigCache, parse_filename
from .core import blender_command, json_get, read_json_quiet
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
    """Update links on each owner (a background Blender each, not waited
    on). Returns {"started": [names], "skipped": [[name, why]]}."""
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
        fd, tmp = tempfile.mkstemp(suffix=".json", prefix="pipeline_relink_")
        request = Path(tmp)
        with open(fd, "w", encoding="utf-8") as f:
            json.dump({"out": str(plan["out"]), "mapping": plan["mapping"]}, f)
        try:
            proc = subprocess.Popen(
                blender_command("relink_entry.py", [request], blend=plan["source"], factory=True),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            request.unlink(missing_ok=True)
            skipped.append([owner.name, f"Blender not started: {e}"])
            continue
        _jobs[key] = {
            "state": "running", "message": f"{plan['source'].name} → {plan['out'].name}",
            "file": plan["out"].stem, "at": time.monotonic(), "proc": proc, "request": request,
            "source": plan["source"], "out": plan["out"], "linked": plan["linked"],
        }
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
        if job["proc"].poll() is None:
            continue
        result = read_json_quiet(job["request"]) or {}
        job["request"].unlink(missing_ok=True)
        out = job["out"]
        if result.get("status") == "ok" and out.is_file():
            try:
                create_wipmeta(filepath=out, original_filepath=job["source"], creation_mode="relink", linked=job["linked"])
                job.update(state="done", message=f"{out.name}: {result.get('message', '')}")
                log("SUCCESS", "relink", f"Update links: {out.name} ({result.get('message', '')})")
            except Exception as e:
                job.update(state="failed", message=f"{out.name} saved, its .wipmeta not: {e}")
                log("WARNING", "relink", job["message"])
        else:
            why = result.get("message") or f"Blender exited with {job['proc'].returncode}"
            job.update(state="failed", message=why)
            log("WARNING", "relink", f"Update links: {job['source'].name} not updated: {why}")
        for k in ("proc", "request", "source", "out", "linked"):
            job.pop(k, None)
        job["at"] = clock
        changed = True
    return changed


def states() -> dict:
    """{owner key: {"state", "message", "file"}} for the page."""
    return {k: {x: j[x] for x in ("state", "message", "file")} for k, j in _jobs.items()}


def _key(root: Path, owner: Path) -> str:
    try:
        return Path(owner).relative_to(root).as_posix()
    except ValueError:
        return str(owner)
