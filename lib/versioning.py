"""Versioning: increment, save_as."""

import os
from pathlib import Path

import bpy

from .config import ConfigCache, get_active_project_root, parse_filename
from .core import cached_scandir, json_get
from .errors import PipelineError
from .logs import log


def get_version_number(filepath: str = "") -> int | None:
    """Extract version number from current (or given) blend filename."""
    fp = filepath or bpy.data.filepath
    if not fp:
        return None
    parsed = parse_filename(Path(fp).name)
    if not parsed:
        return None
    return int(parsed["number"])


def get_last_version_number(filepath: str = "", cached: bool = False) -> int:
    """Scan sibling blend files and return highest version number, or -1.
    cached=True (draw() only) lists through cached_scandir(); anything that
    picks a filename to write must not -- see NOTES.md, "Next version
    number: never from a cached listing"."""
    fp = Path(filepath or bpy.data.filepath)

    parsed = parse_filename(fp.name)
    if not parsed:
        return -1

    versions = []
    if "sequence" in parsed.keys() and "shot" in parsed.keys():
        pattern = ConfigCache.get_shot_regex()
    elif "prefix" in parsed.keys() and "name" in parsed.keys():
        pattern = ConfigCache.get_asset_regex()
    else:
        return -1

    if cached:
        entries = cached_scandir(fp.parent)  # missing folder: [] -> -1 below
    else:
        try:
            entries = list(os.scandir(fp.parent))
        except OSError:
            entries = []
    for f in entries:
        if not f.name.endswith(".blend"):
            continue
        m = pattern.match(f.name)
        if "sequence" in parsed and "shot" in parsed:  # Shot: match sequence + shot nb
            if (
                m
                and m.group("sequence") == parsed["sequence"]
                and m.group("shot") == parsed["shot"]
            ):
                versions.append(int(m.group("number")))
        elif (
            "prefix" in parsed
            and "name" in parsed
            and m
            and m.group("prefix") == parsed["prefix"]
            and m.group("name") == parsed["name"]
        ):
            versions.append(int(m.group("number")))

    return max(versions, default=-1)


def save_as(tag: str | None = None) -> str | None:
    """Save current file as next incremented version. Returns new filepath."""
    current = Path(bpy.data.filepath)
    if not str(current):
        raise PipelineError("No file currently open.")

    project_root = get_active_project_root()
    if not project_root or not str(current).lower().startswith(
        str(project_root).lower()
    ):
        raise PipelineError("File is not inside the active project.")

    config = ConfigCache.get()

    parsed = parse_filename(current.name)
    if not parsed:
        raise PipelineError("File doesn't match naming convention.")

    v_digits = json_get(config, "naming.version.digits", 3)
    v_prefix = json_get(config, "naming.version.prefix", "v")
    next_v = get_last_version_number() + 1

    name, _ = Path(bpy.data.filepath).name.rsplit("_", 1)
    if tag:
        new_name = f"{name}_{v_prefix}{next_v:0{v_digits}d}-{tag}.blend"
    else:
        new_name = f"{name}_{v_prefix}{next_v:0{v_digits}d}.blend"
    new_path = current.parent / new_name

    try:
        bpy.ops.wm.save_as_mainfile(filepath=str(new_path), copy=False)
        log("SUCCESS", "save_asset", f"{current.name} -> {new_name}")
        return str(new_path)
    except Exception as e:
        raise PipelineError(f"Save failed: {e}")
