"""Asset/shot file creation, shared by the interactive operators and the
headless batch entry script. Only what's common to both: folder/version
resolution, scaffolding, save, tracking init -- never a bpy.ops call that
only makes sense interactively (those stay in the operators)."""

from pathlib import Path

import bpy

from .config import (
    DEFAULT_ASSET_DEPARTMENTS,
    DEFAULT_SHOT_DEPARTMENTS,
    ConfigCache,
    format_shot_segment,
    json_get,
    prefix_to_parent_folder,
    sanitize_name,
)
from .errors import PipelineError
from .presets import apply_asset_preset, build_shot_scene
from .tracking import create_tracking, create_wipmeta

# Default per-shot spacing for a multi-shot block with no frame_end/
# frame_duration -- also shot_ops.py's own "add row" default.
DEFAULT_MULTISHOT_STEP = 20


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
    shot_count: int = 1,
    config: dict | None = None,
) -> list[int]:
    """Loose frame_start/frame_end/frame_duration -> a create_shot_file()
    timeline. frame_start defaults to config's default_frame_start;
    frame_end takes precedence over frame_duration. shot_count > 1 spreads
    shots evenly across [frame_start, end], never past an explicit
    frame_end -- see NOTES.md, "CSV batch: multi-shot rows"."""
    config = config if config is not None else ConfigCache.get()
    start = (
        frame_start
        if frame_start is not None
        else json_get(config, "default_frame_start", 1001)
    )
    if frame_end is not None:
        end = frame_end
    elif frame_duration is not None:
        end = start + frame_duration - 1
    elif shot_count > 1:
        end = start + DEFAULT_MULTISHOT_STEP * shot_count
    else:
        return [start]

    if shot_count <= 1:
        return [start, end]

    # Step from the actual span, not the constant -- see NOTES.md.
    step = max(1, (end - start) // shot_count)
    return [start + i * step for i in range(shot_count)] + [end]


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
