"""Per-job render setup: output path, default + custom render settings, frame range."""

import re
import subprocess
from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    PipelineError,
    derive_shot_subranges,
    get_active_project_root,
    json_get,
    locked_json,
    log,
    now,
    parse_filename,
    shots_in_segment,
    to_absolute,
    to_relative,
)
from .dispatch import _active_processes as _active_processes
from .queue import mark_stage


def compute_output_path(
    project_root: Path, shot_root: Path, version_label: str, increment: bool
) -> Path:
    """Compute (and create) the output folder for a render job. version_label
    e.g. "v003". increment=True forces a new folder (_001, _002...) every
    time; False (normal dispatch) reuses the latest existing one."""
    # Relative to project_root/"shots", not project_root itself -- shot_root
    # is always .../shots/<sq>/<sh>, and every reader (lib/preview.py's
    # resolve_sequence_sources()/latest_shot_mp4(), the /old archiving in
    # PIPELINE_OT_edit_block_structure, "Open folder") expects the result
    # at renders/<sq>/<sh>/, not renders/shots/<sq>/<sh>/.
    base = project_root / "renders" / shot_root.relative_to(project_root / "shots")
    i = 1
    while True:
        dir_name = f"{version_label}_{i:03d}"
        dir_path = base / dir_name
        try:
            dir_path.mkdir(parents=True)
            return dir_path
        except FileExistsError:
            if not increment:
                return dir_path
            i += 1
        except PermissionError:
            raise PipelineError(f"Permission denied: unable to create '{dir_path}'.")
        except OSError as e:
            raise PipelineError(f"Path error: {e}")


def resolve_job_context(
    filepath: str, config: dict, shot_override: str = ""
) -> tuple[Path, str]:
    """Derive (shot_root, version_label) for compute_output_path().
    shot_override (e.g. "sh045") routes to shots/<sequence>/<shot_override>/
    instead of filepath's own folder. Raises if filepath doesn't match the
    naming convention."""
    data = parse_filename(Path(filepath).name)
    if data is None:
        raise PipelineError(
            f"'{Path(filepath).name}' doesn't match the naming convention."
        )

    file_root = Path(filepath).parent
    shot_root = file_root.parent / shot_override if shot_override else file_root

    v_prefix = json_get(config, "naming.version.prefix", "v")
    v_digits = json_get(config, "naming.version.digits", 3)
    tag = f"-{data['tag']}" if data.get("tag") else ""
    version_label = f"{v_prefix}{int(data['number']):0{v_digits}d}{tag}"

    return shot_root, version_label


def run_render_setup(job_id: str, config: dict) -> None:
    """Launch the headless setup subprocess for a queued job. Doesn't
    compute the output path itself -- see run_render_setup_entry()."""
    global _active_processes
    job_path = ConfigCache.get_path("farm_actives") / f"{job_id}.json"
    data = None

    with locked_json(job_path) as box:
        try:
            data = box["data"] or {}
            data["stage_history"].append({"stage": "setup_start", "at": now()})
            box["action"] = "to_write"

            entry = (
                Path(__file__).resolve().parent.parent
                / "templates"
                / "farm_entry_render_setup.py"
            )
            process = subprocess.Popen(
                [
                    resolve_local_binary(config),
                    "-b",
                    str(to_absolute(data["filepath"])),
                    "--python",
                    str(entry),
                    "--",
                    "--job-id",
                    job_id,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,  # captured for scan_processes() to log on failure
                text=True,
            )
            _active_processes[job_id] = [(process, "local")]

        except Exception as e:
            mark_stage(
                job_path, "setup_failed"
            )  # separate transaction, actually commits
            log("ERROR", "farm", f"Setup failed for {job_id}: {e}")


def resolve_override_range(
    overrided_range: list[str], frame_start: int = 0, frame_end: int = 0
) -> list[int]:
    """Resolve a (start, end) override pair -- each "n" (unchanged), "a<n>"
    (absolute), "s<n>"/"e<n>" (relative to start/end) -- against the scene's
    actual frame range. Falls back to the scene range on any invalid entry."""
    result = []
    for i, f in enumerate(overrided_range):
        try:
            if f == "n":
                result.append((frame_start, frame_end)[i])
            elif f.startswith("a"):
                result.append(int(f[1:]))
            elif f.startswith("s"):
                result.append(frame_start + int(f[1:]))
            elif f.startswith("e"):
                result.append(frame_end + int(f[1:]))
            else:
                result.append((frame_start, frame_end)[i])
        except Exception:
            result.append((frame_start, frame_end)[i])
    if result[0] < 0:
        log(
            "WARNING",
            "farm",
            f"Overrided start ({result[0]}) result with negative number. -> 0",
        )
        result[0] = 0
    if result[0] > result[1]:
        log(
            "WARNING",
            "farm",
            f"Overrided frames ({result}) not valid. -> cancel override",
        )
        return [frame_start, frame_end]
    return result


def run_render_setup_entry(job_id: str) -> None:
    """Entry point run inside the headless setup subprocess. If shot_override
    isn't set, checks whether this is really a multishot block and splits it
    (_split_into_shot_jobs()); otherwise resolves and writes back the output
    path and frame range."""
    job_path = ConfigCache.get_path("farm_actives") / f"{job_id}.json"
    with locked_json(job_path) as box:
        data = box["data"] or {}
        scene = bpy.context.scene
        config = ConfigCache.get()
        shot_override = data.get("shot_override", "")

        if not shot_override:
            split_into, skipped, absorbed = _split_into_shot_jobs(data, scene, config)
            if split_into:
                data["split_into"] = split_into
                data["skipped_shots"] = skipped
                data["absorbed_shots"] = absorbed
                # Informational only -- this job never renders -- but a
                # non-(0, 0) value keeps scan_processes() from treating the
                # split as a failed setup.
                data["file_frame_range"] = (scene.frame_start, scene.frame_end)
                data["resolved_frame_range"] = (scene.frame_start, scene.frame_end)
                box["action"] = "to_write"
                return

        # A child's overrided_frame_range is already absolute -- the scene
        # range below only matters for an ordinary job's "n"/"s"/"e" forms.
        frame_start, frame_end = resolve_override_range(
            data["overrided_frame_range"], scene.frame_start, scene.frame_end
        )

        project_root = get_active_project_root()
        separator = json_get(config, "naming.frame.prefix", ".")
        digits = json_get(config, "naming.frame.digits", 5)

        stem = Path(data["filepath"]).name.replace(".blend", "")
        if shot_override:
            # Swap the block's own shot segment for this job's single shot
            # in the names written to disk.
            parsed = parse_filename(Path(data["filepath"]).name)
            if parsed and parsed.get("shot"):
                shot_prefix = json_get(config, "naming.shot.prefix", "sh")
                stem = stem.replace(f"{shot_prefix}{parsed['shot']}", shot_override, 1)

        name = stem + separator + str("#" * digits)
        shot_root, version_label = resolve_job_context(
            str(to_absolute(data["filepath"], project_root)), config, shot_override
        )
        output_path = (
            compute_output_path(
                project_root, shot_root, version_label, data["increment"]
            )
            / name
        )

        v_prefix = json_get(config, "naming.version.prefix", "v")
        pattern = rf"_{re.escape(v_prefix)}\d+(-[a-z]+)?$"
        clean_name = re.sub(pattern, "", stem)

        data["output_path"] = to_relative(str(output_path), project_root)
        data["compiled_output_path"] = to_relative(
            str(output_path.parent / f"{clean_name}.mp4"), project_root
        )
        # Already resolved above -- resolving overrided_frame_range a second
        # time here would double-apply a relative override ("s10" on top of
        # an already-shifted frame_start instead of the scene's own).
        data["file_frame_range"] = (frame_start, frame_end)
        data["resolved_frame_range"] = (frame_start, frame_end)
        # fps_base handles fractional rates (e.g. 24/1.001 = 23.976...);
        # captured here (not from project config) so a shot that overrides
        # its own scene fps compiles at the fps it was actually rendered at.
        data["fps"] = round(scene.render.fps / scene.render.fps_base, 3)
        data["output_extension"] = scene.render.image_settings.file_format
        box["action"] = "to_write"


def _split_into_shot_jobs(
    data: dict, scene: "bpy.types.Scene", config: dict
) -> tuple[list[str], list[str], list[str]]:
    """If filepath is really a multishot block (per the live markers),
    submit one ordinary job per shot -- filtered to only_shots if
    restricted. Returns (split_into, skipped, absorbed): skipped is a
    promised shot with no marker, absorbed is a marker not in the name's
    own enumeration. split_into is [] if it's not actually a block."""
    from .monitor import job_request  # local: avoids a setup<->monitor import cycle

    naming = config.get("naming", {})
    parsed = parse_filename(Path(data["filepath"]).name)
    if not parsed or not naming or not parsed.get("shot"):
        return [], [], []

    promised = set(shots_in_segment(parsed["shot"]))
    if len(promised) <= 1:
        return [], [], []

    sequence_label = f"{naming['sequence']['prefix']}{parsed['sequence']}"
    subranges, absorbed_numbers = derive_shot_subranges(
        scene, sequence_label, promised, config
    )
    found = {sub["shot_number"] for sub in subranges}

    only_shots = set(data.get("only_shots") or [])
    shot_prefix = json_get(config, "naming.shot.prefix", "sh")
    shot_digits = json_get(config, "naming.shot.digits", 3)

    def label(n):
        return f"{shot_prefix}{n:0{shot_digits}d}"

    wanted = only_shots if only_shots else promised
    skipped = [label(n) for n in sorted(wanted - found)]
    absorbed = [label(n) for n in absorbed_numbers]

    if len(subranges) <= 1:
        return [], skipped, absorbed

    override = data.get("overrided_frame_range", ("n", "n"))
    split_into = []
    for sub in subranges:
        if only_shots and sub["shot_number"] not in only_shots:
            continue
        shot_label = label(sub["shot_number"])
        # Resolved to absolute now, against this shot's own sub-range.
        resolved = resolve_override_range(
            list(override), sub["frame_start"], sub["frame_end"]
        )
        try:
            job_request(
                to_absolute(data["filepath"]),
                user=data.get("user", "unknown"),
                priority=data.get("priority", 10),
                render_mode=data.get("render_mode", "auto"),
                assigned_machines=data.get("assigned_machines", []),
                increment=data.get("increment", True),
                prerender_script=data.get("prerender_script", "default"),
                overrided_frame_range=(f"a{resolved[0]}", f"a{resolved[1]}"),
                shot_override=shot_label,
            )
            split_into.append(shot_label)
        except PipelineError as e:
            log("ERROR", "farm", f"Could not split off {shot_label}: {e}")
    return split_into, skipped, absorbed


def resolve_local_binary(config: dict) -> str:
    """Inside Blender: bpy.app.binary_path if available (always the most
    reliable, it's the executable actually running). Otherwise (bare daemon,
    or an explicit override is wanted): fall back to the config."""
    try:
        import bpy

        if bpy.app.binary_path:
            return bpy.app.binary_path
    except ImportError:
        pass
    return json_get(config, "farm.local_binary_path", "")
