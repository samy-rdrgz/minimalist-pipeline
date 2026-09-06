"""Creation presets: user-editable asset collection script + built-in shot
scaffolding. Asset preset is an external .py in config/, loaded fresh from
disk every call (never via sys.modules, so edits apply live); a broken one
falls back to a single collection, never blocks creation. Shot scaffolding
(camera + CAM/SET/ASSETS) isn't user-scriptable -- fixed, baked into the addon."""

import importlib.util
import shutil
from pathlib import Path

import bpy

from .config import ConfigCache, format_camera_name, parse_camera_name
from .core import json_get
from .errors import PipelineError
from .logs import log

# ---------------------------------------------------------------------------
# Asset preset: external, user-editable script
# ---------------------------------------------------------------------------


def default_preset_source() -> Path:
    """Path to the addon-bundled default preset script."""
    addon_root = Path(__file__).resolve().parent.parent  # lib/ -> addon root
    return addon_root / "templates" / "asset_file_preset.py"


def install_default_preset():
    """Copy the bundled default preset into a fresh project's config/ folder.
    Never overwrites an existing (possibly user-edited) preset."""
    dest = ConfigCache.get_path("asset_preset_file")
    if dest.exists():
        return
    src = default_preset_source()
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)
        log("INFO", "preset_install", f"Default asset preset installed: {dest}")
    except Exception as e:
        log("WARNING", "preset_install", f"Failed to install default preset: {e}")


def install_default_ffmpeg_preset() -> None:
    """Copy the bundled default ffmpeg preset into a fresh project's
    config/ffmpeg_presets/ folder. Never overwrites an existing
    (possibly user-edited) preset."""
    dest = ConfigCache.get_path("ffmpeg_presets") / "default.json"
    if dest.exists():
        return
    src = (
        Path(__file__).resolve().parent.parent
        / "templates"
        / "ffmpeg_preset_default.json"
    )
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)
        log("INFO", "preset_install", f"Default ffmpeg preset installed: {dest}")
    except Exception as e:
        log(
            "WARNING", "preset_install", f"Failed to install default ffmpeg preset: {e}"
        )


def load_preset_module():
    """Load the project's preset script fresh from disk every call.

    Deliberately bypasses sys.modules: a cached import would silently ignore
    edits made to the file in the current Blender session.
    """
    path = ConfigCache.get_path("asset_preset_file")
    if not path.exists():
        raise PipelineError(f"Preset script not found: {path}")

    spec = importlib.util.spec_from_file_location("pipeline_asset_preset", path)
    if spec is None or spec.loader is None:
        raise PipelineError(f"Could not load preset spec: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_asset_preset(prefix: str, name: str):
    """Run the project's asset preset against the current scene. Never
    raises: any failure (missing file, syntax/runtime error, missing
    build_collections()) falls back to a single collection and logs a
    warning -- a broken preset must never block the asset file's creation."""
    try:
        module = load_preset_module()
        module.build_collections(prefix, name)
    except Exception as e:
        log("WARNING", "asset_preset", f"Preset failed, using fallback: {e}")
        _fallback_single_collection(f"{prefix}_{name}")


def _fallback_single_collection(name: str):
    root = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(root)
    return root


# ---------------------------------------------------------------------------
# Shot scaffolding: fixed behavior, not user-scriptable in v1
# ---------------------------------------------------------------------------


def build_shot_scene(
    sequence_label: str, shot_numbers: list[int], timeline: list[int], config: dict
):
    """Apply project resolution/fps; ensure one camera + timeline marker per
    shot, all sharing a single CAM/SET/ASSETS collection set. Idempotent --
    reuses an existing camera/collection/marker by name instead of adding a
    duplicate, since PIPELINE_OT_edit_block_structure reruns this against
    the very scene a previous enumeration already scaffolded (Save As,
    unless "Start with a new clean scene" is ticked)."""
    scene = bpy.context.scene

    res = json_get(config, "resolution", {"x": 1920, "y": 1080})
    scene.render.resolution_x = int(res.get("x", 1920))
    scene.render.resolution_y = int(res.get("y", 1080))
    scene.render.fps = int(json_get(config, "default_fps", 30))

    cam_col = scene.collection.children.get("CAM")
    if cam_col is None:
        cam_col = bpy.data.collections.new("CAM")
        scene.collection.children.link(cam_col)
    for col_name in ("SET", "ASSETS"):
        if scene.collection.children.get(col_name) is None:
            scene.collection.children.link(bpy.data.collections.new(col_name))

    first_cam = None
    for i, shot_number in enumerate(shot_numbers):
        cam_name = format_camera_name(sequence_label, shot_number, config)
        # timeline[i] is this shot's own start frame; clamped defensively
        # if a caller ever passes a short timeline.
        frame = timeline[i] if i < len(timeline) else timeline[-1]

        cam_obj = bpy.data.objects.get(cam_name)
        if cam_obj is None or cam_obj.type != "CAMERA":
            cam_obj = bpy.data.objects.new(cam_name, bpy.data.cameras.new(cam_name))
        if cam_obj.name not in cam_col.objects:
            cam_col.objects.link(cam_obj)

        marker = next((m for m in scene.timeline_markers if m.camera == cam_obj), None)
        if marker is None:
            marker = scene.timeline_markers.new(cam_name, frame=frame)
            marker.camera = cam_obj
        else:
            marker.frame = frame

        if first_cam is None:
            first_cam = cam_obj

    scene.camera = first_cam
    return first_cam


def derive_shot_subranges(
    scene: "bpy.types.Scene",
    sequence_label: str,
    promised: set[int],
    config: dict | None = None,
) -> tuple[list[dict], list[int]]:
    """Live shot sub-ranges from scene.timeline_markers: each ends where the
    next promised one's marker begins, the last at scene.frame_end. Returns
    (ranges, absorbed) -- absorbed is shot numbers found on the timeline but
    not in `promised`, merged into the preceding range instead."""
    config = config if config is not None else ConfigCache.get()
    found = []
    for marker in scene.timeline_markers:
        if not marker.camera:
            continue
        shot_number = parse_camera_name(marker.camera.name, sequence_label, config)
        if shot_number is not None:
            found.append((marker.frame, shot_number))
    found.sort(key=lambda x: x[0])

    kept = [(frame, n) for frame, n in found if n in promised]
    absorbed = sorted({n for _frame, n in found if n not in promised})

    ranges = []
    for i, (frame, shot_number) in enumerate(kept):
        frame_end = kept[i + 1][0] - 1 if i + 1 < len(kept) else scene.frame_end
        ranges.append(
            {"shot_number": shot_number, "frame_start": frame, "frame_end": frame_end}
        )
    return ranges, absorbed
