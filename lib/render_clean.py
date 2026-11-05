"""Clean old renders: which render folders to lighten, from what the
project knows -- each folder's render history, its last renders, the renders
its open notes and "to check" name, the farm's jobs in progress -- never
from folder names alone (a shot made again starts at v001 next to the old
file's v008). Pure os/json: the scan and the clean run on a thread
(operators/render_clean_ops.py). See NOTES.md, "Clean old renders"."""

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from .core import read_json_quiet
from .preview import is_video, render_root
from .snapshot import _FRAME_FILE, _owner_shots, read_render_state, read_snapshot_raw


# Left in a folder lightened to its video: when it was rendered, as its
# frames said -- the video's own date moves (a remux, a copy).
RENDERED_AT = ".rendered_at"


def _increment_re(v_prefix: str):
    return re.compile(rf"^{re.escape(v_prefix)}\d+(?:-[a-z]+)?_\d+$")


def _timestamp(value) -> float | None:
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return None


def _folder_content(folder: Path) -> dict:
    """A render folder's images (its frames) and the rest: {"images":
    [(path, bytes)], "image_bytes", "other_bytes", "image_time" (newest
    frame's mtime), "video_time", "rendered_at" (RENDERED_AT)}. One
    listing of the folder, one of ld/."""
    images, image_bytes, other_bytes = [], 0, 0
    image_time = video_time = rendered_at = None
    try:
        with os.scandir(folder) as it:
            entries = list(it)
    except OSError:
        entries = []
    for e in entries:
        try:
            if e.is_dir():  # ld/ (the light copy), anything else: kept with the video
                other_bytes += _tree_bytes(Path(e.path))
                continue
            st = e.stat()
        except OSError:
            continue
        if e.name == RENDERED_AT:
            try:
                rendered_at = float(Path(e.path).read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pass
            continue
        if _FRAME_FILE.search(e.name):
            images.append((e.path, st.st_size))
            image_bytes += st.st_size
            image_time = max(image_time or 0, st.st_mtime)
        else:
            other_bytes += st.st_size
            if is_video(e.name):
                video_time = max(video_time or 0, st.st_mtime)
    return {
        "images": images,
        "image_bytes": image_bytes,
        "other_bytes": other_bytes,
        "image_time": image_time,
        "video_time": video_time,
        "rendered_at": rendered_at,
    }


def _tree_bytes(folder: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(folder):
        for f in files:
            try:
                total += os.stat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total


def _active_outputs(root: Path, farm_actives: Path | None) -> set[str]:
    """The render folders the farm's jobs in progress write to."""
    out = set()
    if not farm_actives:
        return out
    try:
        jobs = [e.path for e in os.scandir(farm_actives) if e.name.endswith(".json")]
    except OSError:
        return out
    for path in jobs:
        output = (read_json_quiet(Path(path)) or {}).get("output_path")
        if output:
            out.add(os.path.normcase(str((Path(root) / output).parent)))
    return out


def _key(path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def plan_render_clean(
    root: Path,
    keep: int,
    images_only: bool,
    kinds: tuple = ("shot", "asset"),
    sequence: str = "",
    v_prefix: str = "v",
    farm_actives: Path | None = None,
) -> dict:
    """What a clean would do. Per shot (a block's each, and the block
    rendered whole) or asset render folder: its renders ordered by when they
    were made -- the history's completed_at, else its newest frame, else
    the date left when lightened, else its video --, the keep newest kept, and
    always its last render, a render an open note or "to check" names, one
    the farm is writing. A previous file's renders (made before this one's
    created_at, not in its history) count for nothing: all lightened, or
    all deleted but the newest when the shot has no render of its own. The rest:
    deleted whole, or (images_only) only their frames, the videos and ld/
    kept. {"candidates": [{"group", "owner", "shot_dir", "folder", "path",
    "bytes", "images"}], "kept": n, "bytes": total, "groups": {group:
    [folders, bytes]}}."""
    root = Path(root)
    increment = _increment_re(v_prefix)
    active = _active_outputs(root, farm_actives)
    candidates, kept = [], 0
    for kind, owner, raw, _ in read_snapshot_raw(root):
        tracking = raw["tracking"]
        if kind not in kinds or tracking.get("archived"):
            continue
        if sequence and kind == "shot" and owner.parent.name != sequence:
            continue
        group = owner.parent.name if kind == "shot" else "/".join(
            owner.relative_to(root).parts[:-1]
        )
        protected = set(active)
        # Its last renders: kept -- unless one turns out to be a previous
        # file's (below), the fallback by folder name finding it.
        last = {
            _key(r["path"])
            for r in read_render_state(root, kind, owner, v_prefix)
            if r.get("path")
        }
        for info in (tracking.get("to_check") or {}).values():
            if info.get("render"):
                protected.add(_key(root / info["render"]))
        # An open note's render, by its folder name, in each of the folder's
        # shots (a note's shot is a number, its folder a label: both kept).
        noted = {
            e["render"]
            for e in tracking.get("entries") or []
            if e.get("render") and e.get("done") is False
        }
        history = read_json_quiet(owner / ".pipeline" / "render_history.json") or {}
        finished_at = {}
        for e in history.get("entries") or []:
            if isinstance(e, dict) and e.get("output_path") and e.get("status") == "finished":
                when = _timestamp(e.get("completed_at"))
                if when is not None:
                    finished_at[_key((root / e["output_path"]).parent)] = when
        # Made before this file existed: a previous file of the same shot
        # (deleted and made again, a block split...) -- not one of its
        # renders, whatever its number.
        created = _timestamp(tracking.get("created_at"))
        base = render_root(root, owner)
        shot_dirs = {base}
        if kind == "shot":
            shot_dirs |= {base.with_name(s) for s in _owner_shots(owner)}
        for shot_dir in sorted(shot_dirs):
            try:
                folders = [
                    Path(e.path)
                    for e in os.scandir(shot_dir)
                    if e.is_dir() and increment.match(e.name)
                ]
            except OSError:
                continue
            rows = []
            for folder in folders:
                content = _folder_content(folder)
                when = (
                    finished_at.get(_key(folder))
                    or content["image_time"]
                    or content["rendered_at"]
                    or content["video_time"]
                    or os.stat(folder).st_mtime
                )
                rows.append((when, folder, content))
            rows.sort(key=lambda r: r[0], reverse=True)
            own = [
                r for r in rows
                if _key(r[1]) in finished_at or created is None or r[0] >= created
            ]
            previous = [r for r in rows if r not in own]
            keeping = {_key(r[1]) for r in own[:keep]}
            keeping |= {_key(r[1]) for r in own if _key(r[1]) in last}
            if previous and not own and not images_only:
                # Deleting: a shot's only video left, even a previous file's.
                keeping.add(_key(previous[0][1]))
            for when, folder, content in rows:
                if (
                    _key(folder) in keeping
                    or _key(folder) in protected
                    or folder.name in noted
                ):
                    kept += 1
                    continue
                size = content["image_bytes"] if images_only else (
                    content["image_bytes"] + content["other_bytes"]
                )
                if images_only and not content["images"]:
                    continue  # already light: only its video left
                candidates.append(
                    {
                        "group": group,
                        "owner": owner.name,
                        "shot_dir": shot_dir.name,
                        "folder": folder.name,
                        "path": str(folder),
                        "bytes": size,
                        "images": [p for p, _ in content["images"]],
                        "when": when,
                        "previous": _key(folder) not in {_key(r[1]) for r in own},
                    }
                )
    groups: dict = {}
    for c in candidates:
        g = groups.setdefault(c["group"], [0, 0])
        g[0] += 1
        g[1] += c["bytes"]
    return {
        "candidates": candidates,
        "kept": kept,
        "bytes": sum(c["bytes"] for c in candidates),
        "groups": dict(sorted(groups.items())),
        "images_only": images_only,
    }


def apply_render_clean(plan: dict) -> dict:
    """Do what plan_render_clean() planned: each folder deleted, or its
    frames only. {"done": folders, "bytes": freed, "errors": [(path,
    message)]} -- one failure never stops the others."""
    done, freed, errors = 0, 0, []
    for c in plan["candidates"]:
        try:
            if plan["images_only"]:
                # Its date first: once its frames are gone, nothing else
                # tells it (_folder_content()).
                Path(c["path"], RENDERED_AT).write_text(str(c["when"]), encoding="utf-8")
                for path in c["images"]:
                    try:
                        os.remove(path)
                    except FileNotFoundError:
                        pass
            else:
                shutil.rmtree(c["path"])
            done += 1
            freed += c["bytes"]
        except OSError as e:
            errors.append((c["path"], str(e)))
    return {"done": done, "bytes": freed, "errors": errors}


def human_bytes(n: float) -> str:
    """340 MB, 1.2 GB..."""
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
