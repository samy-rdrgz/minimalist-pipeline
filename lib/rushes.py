"""Editing rushes: each shot's (and asset's) video copied into
editing/rushes/ under its own unversioned name -- sq100/sq100_sh030.mp4,
assets/ch/ch_bob.mp4 -- so the edit keeps its links while the renders
behind them change. rushes.json there says which
render each one is. Filesystem-only, no bpy: runs on a thread."""

import json
import os
import shutil
from pathlib import Path

from .core import json_get, now, retry_shared_io, write_json_atomic
from .preview import latest_asset_videos, resolve_sequence_sources

RUSHES_DIR = Path("editing") / "rushes"
RUSHES_MANIFEST = "rushes.json"
# For the editor: what each push brought in, appended; deleted by hand once
# checked in the edit. See NOTES.md, "Rushes for the edit".
RUSHES_UPDATED = "_UPDATED.txt"


def _destination(project_root: Path, mp4: Path) -> tuple[str, str] | None:
    """A render video's place in the rushes, rushes-relative, laid out like
    the snapshot's videos zip -- its owner's and render's folders left out:
    renders/sq100/sh030/v003_001/sq100_sh030.mp4 -> sq100/sq100_sh030.mp4,
    renders/assets/ch/ch_bob/v002_001/ch_bob.mp4 -> assets/ch/ch_bob.mp4 --
    and the .blend version it was rendered from (sq100_sh030_v003). None
    for anything else (a preview, an archived one)."""
    try:
        parts = mp4.relative_to(project_root / "renders").parts
    except ValueError:
        return None
    if len(parts) < 4 or "_preview" in parts or "old" in parts:
        return None
    owner, render = parts[-3], parts[-2]
    base = owner if parts[0] in ("assets", "library") else f"{parts[0]}_{owner}"
    version = f"{base}_{render.rsplit('_', 1)[0]}"
    return "/".join([*parts[:-3], parts[-1]]), version


def _read_manifest(path: Path) -> dict:
    """rushes.json's entries, {} if none or unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("rushes") or {}
    except (OSError, ValueError, AttributeError):
        return {}


def _note_updated(path: Path, changes: list[tuple], user: str) -> None:
    """Append one push's new/replaced rushes to _UPDATED.txt (its how-to
    line first when it starts a new file). Raises OSError."""
    lines = [] if path.exists() else [
        "Rushes pushed since this file was last deleted: check them in the "
        "edit, then delete this file.",
    ]
    lines += ["", f"{now()[:16].replace('T', ' ')} -- {user}:"]
    width = max(len(name) for _, name, _, _ in changes)
    for kind, name, render, previous in changes:
        was = f" (was {previous})" if previous else ""
        lines.append(f"  {kind:<8}  {name:<{width}}  {render}{was}")
    with open(path, "a", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")


def push_rushes(project_root: Path, videos: list[Path], user: str) -> dict:
    """Copy each video (a shot render's mp4) into the rushes, replacing the
    one of the same name: copied beside it, then renamed onto it -- the
    edit never sees half a file. One already pushed from the same render
    (rushes.json: same source, size and date) is left alone. A replace
    refused (the file open in the editing software) is reported, the old
    one kept. rushes.json records, per rush, its source, render folder and
    the .blend version it was rendered from; _UPDATED.txt, what came in.
    -> {"copied": [names], "unchanged": int, "failed": [(name, reason)]}"""
    project_root = Path(project_root)
    rushes = project_root / RUSHES_DIR
    manifest_path = rushes / RUSHES_MANIFEST
    manifest = _read_manifest(manifest_path)
    result = {"copied": [], "unchanged": 0, "failed": []}
    changes = []  # (new / replaced, name, render, previous render)
    for mp4 in videos:
        mp4 = Path(mp4)
        where = _destination(project_root, mp4)
        if where is None:
            continue
        name, version = where
        try:
            stat = mp4.stat()
        except OSError as e:
            result["failed"].append((name, f"source unreadable: {e}"))
            continue
        source = mp4.relative_to(project_root).as_posix()
        dest = rushes / name
        known = manifest.get(name) or {}
        if (
            dest.exists()
            and known.get("source") == source
            and known.get("size") == stat.st_size
            and known.get("mtime") == stat.st_mtime
        ):
            result["unchanged"] += 1
            continue
        tmp = dest.with_name(f".{dest.name}.tmp")
        existed = dest.exists()
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(mp4, tmp)
            retry_shared_io(os.replace, tmp, dest, attempts=10, delay=0.2)
        except PermissionError:
            result["failed"].append(
                (name, "access refused (file open elsewhere, or no write permission?)")
            )
            continue
        except OSError as e:
            result["failed"].append((name, str(e)))
            continue
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        changes.append(
            (
                "replaced" if existed else "new",
                name,
                mp4.parent.name,
                known.get("render") if existed else None,
            )
        )
        manifest[name] = {
            "source": source,
            "render": mp4.parent.name,  # v003-stable_001
            # The .blend it was rendered from: the folder minus its increment.
            "version": version,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "pushed_at": now(),
            "pushed_by": user,
        }
        result["copied"].append(name)
    if result["copied"]:
        try:
            rushes.mkdir(parents=True, exist_ok=True)
            write_json_atomic(manifest_path, {"rushes": dict(sorted(manifest.items()))})
        except OSError as e:
            result["failed"].append((RUSHES_MANIFEST, str(e)))
        try:
            _note_updated(rushes / RUSHES_UPDATED, changes, user)
        except OSError as e:
            result["failed"].append((RUSHES_UPDATED, str(e)))
    return result


def push_sequence_rushes(
    project_root: Path, sequences: list[str], assets: bool, config: dict, user: str
) -> dict:
    """push_rushes() for every shot's latest video of these sequences (the
    ones Preview sequence takes) and, with assets, every asset/library's.
    Also -> "empty": what had none, "dropped": the older ones left out
    (resolve_sequence_sources())."""
    videos, empty, dropped = [], [], []
    for sequence in sequences:
        sources = resolve_sequence_sources(
            sequence, Path(project_root), config, dropped
        )
        if not sources:
            empty.append(sequence)
        videos += [mp4 for _label, mp4 in sources]
    if assets:
        asset_videos = latest_asset_videos(
            Path(project_root), json_get(config, "naming.version.prefix", "v")
        )
        if not asset_videos:
            empty.append("assets/libraries")
        videos += asset_videos
    return push_rushes(project_root, videos, user) | {
        "empty": empty,
        "dropped": dropped,
    }
