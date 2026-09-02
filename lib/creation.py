"""Asset/shot file creation, shared by the interactive operators and the
headless batch entry script. Only what's common to both: folder/version
resolution, scaffolding, save, tracking init -- never a bpy.ops call that
only makes sense interactively (those stay in the operators)."""

from pathlib import Path

import bpy

from .config import (
    ConfigCache,
    format_shot_segment,
    json_get,
    prefix_to_parent_folder,
    sanitize_name,
)
from .errors import PipelineError
from .presets import apply_asset_preset, build_shot_scene
from .tracking import create_tracking, create_wipmeta

# Fallback department lists, used whenever a caller doesn't provide its own
# (interactive dialogs default to every configured department instead --
# these are only hit when config itself doesn't define assets_departments/
# shots_departments, or from the CSV batch importer when a row's
# 'departments' column is empty). Centralized here rather than duplicated at
# each call site.
DEFAULT_ASSET_DEPARTMENTS = ["modeling", "rigging", "texturing"]
DEFAULT_SHOT_DEPARTMENTS = ["layout", "animation", "lighting", "render"]


def create_asset_file(
    project_root: Path,
    *,
    prefix: str,
    name: str,
    departments: list[str] | None = None,
    description: str = "",
) -> Path:
    """Build one new asset file: folder, preset collections, save, tracking
    init. departments defaults to the project's configured assets_departments
    if not given (matches the interactive dialog's own default)."""
    config = ConfigCache.get()
    name = sanitize_name(name)
    if not name or name == "unnamed":
        raise PipelineError("Asset name is required.")

    if departments is None:
        departments = json_get(config, "assets_departments", DEFAULT_ASSET_DEPARTMENTS)

    parent_folder = prefix_to_parent_folder(prefix, config)
    dest_dir = project_root / parent_folder / prefix / f"{prefix}_{name}"

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise PipelineError(f"Failed to create folder: {e}")

    v_digits = int(json_get(config, "naming.version.digits", 3))
    next_v = 1
    pattern = ConfigCache.get_asset_regex()
    for f in dest_dir.iterdir():
        m = pattern.match(f.name)
        if m:
            next_v = max(next_v, int(m.group("number")) + 1)

    file_name = f"{prefix}_{name}_v{next_v:0{v_digits}d}.blend"
    dest_path = dest_dir / file_name

    try:
        apply_asset_preset(prefix, name)
        bpy.ops.wm.save_as_mainfile(filepath=str(dest_path), copy=False)
        create_tracking(dest_path, list(departments), description=description)
        create_wipmeta(
            filepath=dest_path, original_filepath=None, creation_mode="creation"
        )
    except PipelineError:
        raise
    except Exception as e:
        raise PipelineError(f"Save failed: {e}")

    return dest_path


def resolve_timeline(
    *,
    frame_start: int | None = None,
    frame_end: int | None = None,
    frame_duration: int | None = None,
    config: dict | None = None,
) -> list[int]:
    """Loose frame_start/frame_end/frame_duration -> a create_shot_file()
    timeline. frame_start defaults to config's default_frame_start;
    frame_end takes precedence over frame_duration."""
    config = config if config is not None else ConfigCache.get()
    start = (
        frame_start
        if frame_start is not None
        else json_get(config, "default_frame_start", 1001)
    )
    if frame_end is not None:
        return [start, frame_end]
    if frame_duration is not None:
        return [start, start + frame_duration - 1]
    return [start]


def create_shot_file(
    project_root: Path,
    *,
    sequence_number: int,
    shot_number: int | list[int],
    departments: list[str] | None = None,
    description: str = "",
    timeline: list[int] | None = None,
    start_version: int | None = None,
) -> Path:
    """Build one new shot (or block) file: folder, camera/marker scaffolding,
    frame range, save, tracking init. shot_number: int or list[int].
    timeline: [start_0, ..., end], defaults to [default_frame_start].
    start_version: floor for the new version number."""
    config = ConfigCache.get()
    naming = config.get("naming", {})
    if not naming:
        raise PipelineError("Project config is missing or invalid.")

    if departments is None:
        departments = json_get(config, "shots_departments", DEFAULT_SHOT_DEPARTMENTS)

    shot_numbers = shot_number if isinstance(shot_number, list) else [shot_number]
    if not shot_numbers:
        # An empty list silently produces a shot with no number in its name
        # (format_shot_segment([]) == "") and no camera/marker at all
        # (build_shot_scene() loops over shot_numbers) -- catch it here too,
        # not just in the operator's own UI-level check, so any other
        # caller can't hit the same silent corruption.
        raise PipelineError("No shot number given -- at least one shot is required.")
    timeline = timeline or [json_get(config, "default_frame_start", 1001)]

    sq = f"{naming['sequence']['prefix']}{sequence_number:0{naming['sequence']['digits']}d}"
    sh = f"{naming['shot']['prefix']}{format_shot_segment(shot_numbers, config)}"

    dest_dir = project_root / "shots" / sq / sh
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise PipelineError(f"Failed to create folder: {e}")

    next_v = start_version or 1
    pattern = ConfigCache.get_shot_regex()
    for f in dest_dir.iterdir():
        m = pattern.match(f.name)
        if m:
            next_v = max(next_v, int(m.group("number")) + 1)

    file_name = f"{sq}_{sh}_{naming['version']['prefix']}{next_v:0{naming['version']['digits']}d}.blend"
    dest_path = dest_dir / file_name

    try:
        build_shot_scene(sq, shot_numbers, timeline, config)
        scene = bpy.context.scene
        scene.frame_start = timeline[0]
        if len(timeline) > 1:
            scene.frame_end = timeline[-1]

        bpy.ops.wm.save_as_mainfile(filepath=str(dest_path), copy=False)
        create_tracking(dest_path, list(departments), description=description)
        create_wipmeta(
            filepath=dest_path, original_filepath=None, creation_mode="creation"
        )
    except PipelineError:
        raise
    except Exception as e:
        raise PipelineError(f"Save failed: {e}")

    return dest_path
