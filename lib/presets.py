"""Creation presets: user-editable asset collection script + built-in shot
scaffolding. Asset preset is an external .py in config/, loaded fresh from
disk every call (never via sys.modules, so edits apply live); a broken one
falls back to a single collection, never blocks creation. Shot scaffolding
(camera + CAM/SET/ASSETS) isn't user-scriptable -- fixed, baked into the addon."""

import importlib.util
import re
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


def install_department_presets(departments, presets_dir: Path | None = None) -> list[str]:
    """A render preset per department with none (no preset's name gives it,
    lib/monitoring/status.py preset_department()): <department>_default.py from the
    bundled template, its renders that department's. Never overwrites.
    presets_dir: the project's config/presets (the active one's by
    default). Returns the files made. See NOTES.md, "Renders by department"."""
    from .monitoring.status import preset_department

    presets_dir = Path(presets_dir) if presets_dir else ConfigCache.get_path("presets")
    try:
        existing = [p.stem for p in presets_dir.glob("*.py") if p.name != "asset_file_preset.py"]
    except OSError:
        existing = []
    template = (Path(__file__).resolve().parent.parent / "templates" / "render_preset_default.py").read_text(encoding="utf-8")
    made = []
    for d in dict.fromkeys(str(d).strip().lower() for d in departments if str(d).strip()):
        if any(preset_department(name, [d]) == d for name in existing):
            continue
        dest = presets_dir / f"{d}_default.py"
        try:
            presets_dir.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_text(template.replace("{department}", d), encoding="utf-8")
                made.append(dest.name)
        except OSError as e:
            log("WARNING", "preset_install", f"Render preset {dest.name} not made: {e}")
    if made:
        log("INFO", "preset_install", f"Render presets made: {', '.join(made)}")
    return made


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
    """One collection named name under the scene's: the asset preset's
    fallback."""
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
    reuses an existing camera/collection/marker by name instead of
    duplicating it, and removes any other marker on a shot's frame (see
    NOTES.md)."""
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
    placed = []  # this call's own markers, one per shot
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
        placed.append(marker)

        # Any other marker already on that frame -- a new shot built from
        # another shot's file (no clean scene), a shot dropped by Edit block
        # structure: two markers on one frame break the per-shot split.
        for other in [
            m for m in scene.timeline_markers if m.frame == frame and m not in placed
        ]:
            log(
                "INFO",
                "shot_scene",
                f"Marker {other.name} removed: frame {frame} is {cam_name}'s",
            )
            scene.timeline_markers.remove(other)

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
    next promised one's marker begins, the last at scene.frame_end -- a
    shot's marker after its first going on with the range it's in. Returns
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

    # A shot's camera bound again further on (its next shot's camera gone,
    # its marker now on this one): the same shot going on, not a second
    # range of it -- the split asked for two jobs of one shot.
    kept, seen = [], set()
    for frame, n in found:
        if n in promised and n not in seen:
            kept.append((frame, n))
            seen.add(n)
    absorbed = sorted({n for _frame, n in found if n not in promised})

    ranges = []
    for i, (frame, shot_number) in enumerate(kept):
        frame_end = kept[i + 1][0] - 1 if i + 1 < len(kept) else scene.frame_end
        ranges.append(
            {"shot_number": shot_number, "frame_start": frame, "frame_end": frame_end}
        )
    return ranges, absorbed


# ---------------------------------------------------------------------------
# Render presets: their name gives their renders' department, so renaming
# one updates everything that cites it. See NOTES.md, "Rename preset".
# ---------------------------------------------------------------------------

_PRESET_NAME = re.compile(r"[A-Za-z0-9][\w\-]*")


def presets_without_department(presets_dir: Path, departments) -> list[str]:
    """The render presets (.py, under presets_dir) whose name gives no
    department: their renders have none."""
    from .monitoring.status import preset_department

    try:
        names = sorted(p.stem for p in Path(presets_dir).glob("*.py") if p.name != "asset_file_preset.py")
    except OSError:
        return []
    return [n for n in names if not preset_department(n, departments)]


def farm_jobs_waiting(root: Path) -> int:
    """Jobs in the project's farm -- sent, queued, rendering, failed but
    not archived: a job's file is named after its preset, a rename would
    lose it."""
    queue = Path(root) / "config" / ".farm" / "queue"
    n = 0
    for sub in ("incomings", "actives", "requests"):
        try:
            n += sum(1 for p in (queue / sub).iterdir() if p.suffix == ".json")
        except OSError:
            pass
    return n


def preset_rename_problem(root: Path, old: str, new: str) -> str:
    """Why old can't be renamed new ("" if it can)."""
    presets = Path(root) / "config" / "presets"
    if not old or not (presets / f"{old}.py").is_file():
        return f"No preset {old!r}."
    if not _PRESET_NAME.fullmatch(new or ""):
        return "A name of letters, digits, _ and - only."
    if new == old:
        return "Same name."
    if (presets / f"{new}.py").exists() or new == "asset_file_preset":
        return f"{new}.py already exists."
    jobs = farm_jobs_waiting(root)
    if jobs:
        return f"{jobs} job(s) in the farm: rename once it's empty (a job is found by its preset's name)."
    return ""


def rename_preset(root: Path, old: str, new: str, departments, old_renders: bool = False) -> dict:
    """Rename config/presets/<old>.py <new>.py and every place that cites
    it: the config's farm.default_prerender_script, each render_history.json
    entry's prerender_script, preset_pace.json's keys. old_renders: the
    renders it made with no department get the one the new name gives
    (entry and DEPARTMENT_FILE) -- right only if the preset always served
    that department. Raises PipelineError (preset_rename_problem()).
    Returns {"histories", "renders", "departments", "pace", "default"}."""
    from .config import get_config_filepath
    from .core import locked_json
    from .preview import DEPARTMENT_FILE
    from .monitoring.status import preset_department
    from .monitoring.tracking import _DATA_ROOTS, _walk_owner_dirs

    root = Path(root)
    problem = preset_rename_problem(root, old, new)
    if problem:
        raise PipelineError(problem, "WARNING")
    presets = root / "config" / "presets"
    (presets / f"{old}.py").rename(presets / f"{new}.py")
    out = {"histories": 0, "renders": 0, "departments": 0, "pace": False, "default": False}
    dep = preset_department(new, departments)

    with locked_json(get_config_filepath(root)) as box:
        farm = (box["data"] or {}).get("farm") or {}
        if farm.get("default_prerender_script") == old:
            farm["default_prerender_script"] = new
            box["action"] = "to_write"
            out["default"] = True

    for top in _DATA_ROOTS:
        for owner in _walk_owner_dirs(root / top):
            path = owner / ".pipeline" / "render_history.json"
            if not path.is_file():
                continue
            with locked_json(path) as box:
                entries = [e for e in (box["data"] or {}).get("entries") or [] if isinstance(e, dict)]
                mine = [e for e in entries if e.get("prerender_script") == old]
                for e in mine:
                    e["prerender_script"] = new
                    if old_renders and dep and not e.get("department"):
                        e["department"] = dep
                        out["departments"] += 1
                        if e.get("status") == "finished" and e.get("output_path"):
                            marker = (root / e["output_path"]).parent / DEPARTMENT_FILE
                            try:
                                if marker.parent.is_dir() and not marker.exists():
                                    marker.write_text(dep, encoding="utf-8")
                            except OSError as err:
                                log("WARNING", "preset_rename", f"{marker}: not written: {err}")
                if mine:
                    box["action"] = "to_write"
                    out["histories"] += 1
                    out["renders"] += len(mine)

    pace = root / "config" / ".farm" / "preset_pace.json"
    if pace.is_file():
        with locked_json(pace) as box:
            data = box["data"] or {}
            for key in ("presets", "averages"):
                part = data.get(key)
                if isinstance(part, dict) and old in part:
                    moved = part.pop(old)
                    if isinstance(moved, list) and isinstance(part.get(new), list):
                        moved = part[new] + moved
                    part.setdefault(new, moved)
                    box["action"] = "to_write"
                    out["pace"] = True
    log(
        "INFO",
        "preset_rename",
        f"Render preset {old} renamed {new}: {out['renders']} render(s) in {out['histories']} file(s)"
        + (f", {out['departments']} given the department {dep}" if out["departments"] else ""),
    )
    return out
