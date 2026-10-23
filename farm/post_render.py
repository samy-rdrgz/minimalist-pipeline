"""Post-render pipeline stages: frame integrity check and video compilation, both via ffmpeg."""

from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    PipelineError,
    get_machine_id,
    json_get,
    locked_json,
    log,
    now,
    resolve_ffmpeg,
    run_thumbnail_jobs,
    thumbnail_jobs,
    thumbnail_size,
    to_absolute,
)
from .dispatch import popen_logged, track_local_processes

_EXTENSION_MAP = {
    "PNG": "png",
    "JPEG": "jpg",
    "JPEG2000": "jp2",
    "TARGA": "tga",
    "TARGA_RAW": "tga",
    "OPEN_EXR": "exr",
    "OPEN_EXR_MULTILAYER": "exr",
    "TIFF": "tif",
    "BMP": "bmp",
    "HDR": "hdr",
    "CINEON": "cin",
    "DPX": "dpx",
    "WEBP": "webp",
}


def refresh_shot_thumbnail(data: dict, project_root: Path) -> None:
    """Remake the shot's thumbnail from the render that just finished, in a
    detached headless Blender -- fire and forget, never blocks the monitor.
    Never raises: a missing thumbnail must not fail a good render (the
    snapshot export catches up on it)."""
    try:
        output = Path(data.get("output_path") or "")
        if not output.name:
            return
        output = output if output.is_absolute() else Path(project_root) / output
        # renders/<seq>/<shot>/<v004-stable_002>/<frame> -> renders/<seq>/<shot>
        config = ConfigCache.get()
        size = thumbnail_size(config)
        jobs = thumbnail_jobs(
            [output.parent.parent],
            json_get(config, "naming.version.prefix", "v"),
            force=True,
            size=size,
        )
        run_thumbnail_jobs(
            jobs, bpy.app.binary_path, resolve_ffmpeg(), size=size, wait=False
        )
    except Exception as e:
        log("WARNING", "farm", f"Thumbnail not refreshed for {data.get('job_id')}: {e}")


def checks_images(job_path: Path):
    """Launch an ffmpeg pass over the rendered frame sequence to detect corrupted frames."""
    try:
        with locked_json(to_absolute(job_path)) as box:
            data = box["data"] or {}
            ffmpeg_bin = resolve_ffmpeg()
            if ffmpeg_bin:
                path = str(to_absolute(Path(data["output_path"])))
                cmd = [
                    ffmpeg_bin,
                    "-hide_banner",
                    "-nostats",
                    # Every line tagged with its level, and a showinfo line
                    # per decoded frame; decoding single-threaded, an error
                    # lands right before its frame's line, which names the
                    # corrupted frames (queue.corrupted_frames()). The
                    # "level" flag needs ffmpeg 4.3+.
                    "-loglevel",
                    "level+info",
                    "-threads",
                    "1",
                    "-start_number",
                    str(data["resolved_frame_range"][0]),
                    "-i",
                    f"{path.split('#')[0]}%0{data['output_path'].count('#')}d.{_EXTENSION_MAP.get(data['output_extension'], 'png')}",
                    "-vf",
                    "showinfo",
                    "-f",
                    "null",
                    "-",
                ]

                data["stage_history"].append(
                    {"stage": "checks_images_start", "at": now()}
                )
                box["action"] = "to_write"

                # Read back by scan_processes() (corrupted_frames()). A
                # file, never a PIPE: a long sequence would fill it and
                # hang ffmpeg for good (see popen_logged()).
                proc = [
                    (
                        popen_logged(
                            cmd, data["job_id"], "checks_images", merge_stdout=False
                        ),
                        "local",
                    )
                ]
                track_local_processes(data, proc)
            else:
                data["stage_history"].append(
                    {"stage": "checks_images_failed", "at": now()}
                )
                box["action"] = "to_write"
                raise PipelineError("FFMPEG is not installed")
    except Exception as e:
        from .queue import mark_stage

        mark_stage(
            job_path, "checks_images_failed"
        )  # separate transaction, actually commits
        log("ERROR", "farm", f"Checks images failed for {job_path.stem!s} {e}")


def resolve_ffmpeg_preset(preset_name: str | None) -> dict:
    """Load an ffmpeg compilation preset by name, falling back to default.json."""
    name = preset_name or "default"
    presets_dir = ConfigCache.get_path("ffmpeg_presets")
    path = presets_dir / f"{name}.json"
    if not path.exists():
        path = presets_dir / "default.json"
    with locked_json(path) as box:
        return box["data"] or {}


def _ffmpeg_preset_to_args(preset: dict) -> list[str]:
    """Convert a preset dict (codec/preset/crf/pix_fmt/extra_args) into ffmpeg CLI flags."""
    args = []
    for key in ("codec", "preset", "crf", "pix_fmt"):
        if key in preset:
            flag = "-c:v" if key == "codec" else f"-{key}"
            args += [flag, str(preset[key])]
    args += preset.get("extra_args", [])
    return args


def compilation(*, project_root: Path, job_path: Path, compilation_settings: str):
    """Launch ffmpeg to compile the rendered frame sequence into a video file.

    Keyword-only: project_root and job_path are both Path, a positional call
    risks silently swapping them."""
    try:
        with locked_json(job_path) as box:
            data = box["data"] or {}
            # data["fps"]: the render's actual scene fps, captured at setup
            # time (run_render_setup_entry, farm/setup.py) -- falls back to
            # the project default only for a job that never reached that
            # stage with this field (e.g. queued before this was added).
            framerate = data.get("fps") or json_get(
                ConfigCache.get(), "default_fps", "30"
            )
            ffmpeg_bin = resolve_ffmpeg()
            if ffmpeg_bin is not None:
                abs_path = to_absolute(data["output_path"], project_root)
                cmd = (
                    [
                        ffmpeg_bin,
                        "-y",
                        "-r",
                        str(framerate),
                        "-start_number",
                        str(data["resolved_frame_range"][0]),
                        "-i",
                        f"{str(abs_path).split('#')[0]}%0{data['output_path'].count('#')}d.{_EXTENSION_MAP.get(data['output_extension'], 'png')}",
                    ]
                    + list(
                        _ffmpeg_preset_to_args(
                            resolve_ffmpeg_preset(compilation_settings)
                        )
                    )
                    + [
                        to_absolute(
                            data.get("compiled_output_path", str(project_root)),
                            project_root,
                        )
                    ]
                )
                proc = [
                    (
                        popen_logged(cmd, data["job_id"], "compilation"),
                        "local",
                    )
                ]
                data["stage_history"].append(
                    {"stage": "compilation_start", "at": now()}
                )
                box["action"] = "to_write"
                track_local_processes(data, proc)

            else:
                data["stage_history"].append(
                    {"stage": "compilation_failed", "at": now()}
                )
                box["action"] = "to_write"
                raise PipelineError("FFMPEG is not installed")
    except Exception as e:
        from .queue import mark_stage

        mark_stage(
            job_path, "compilation_failed"
        )  # separate transaction, actually commits
        log("ERROR", "farm", f"Compilation failed for {job_path.stem!s} {e}")


def build_concat_command(
    inputs: list[Path],
    output: Path,
    config: dict,
    compilation_settings: str,
    ffmpeg_bin: str,
) -> list[str]:
    """ffmpeg command concatenating inputs into output via the concat filter
    (re-encodes each to the project's resolution/fps), not the concat
    demuxer's -c copy. ffmpeg_bin: resolved by the caller (resolve_ffmpeg()),
    not re-resolved here -- there'd be no single place left asserting it was
    actually found."""
    res = json_get(config, "resolution", {"x": 1920, "y": 1080})
    width, height = int(res.get("x", 1920)), int(res.get("y", 1080))
    fps = json_get(config, "default_fps", 30)

    cmd = [ffmpeg_bin, "-y"]
    for p in inputs:
        cmd += ["-i", str(p)]

    parts = [
        f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}]"
        for i in range(len(inputs))
    ]
    parts.append(
        "".join(f"[v{i}]" for i in range(len(inputs)))
        + f"concat=n={len(inputs)}:v=1:a=0[outv]"
    )

    cmd += ["-filter_complex", ";".join(parts), "-map", "[outv]"]
    cmd += _ffmpeg_preset_to_args(resolve_ffmpeg_preset(compilation_settings))
    cmd += [str(output)]
    return cmd


def preview_command(data: dict, project_root: Path, ffmpeg_bin: str) -> list[str]:
    """ffmpeg command concatenating a preview job's sources -- on the farm
    host (run_preview_compile()) or on a worker (execute_compile_request()),
    each with its own ffmpeg and project root. Creates the output's folder."""
    inputs = [to_absolute(src, project_root) for _label, src in data["sources"]]
    output = to_absolute(data["output_path"], project_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    return build_concat_command(
        inputs,
        output,
        ConfigCache.get(),
        data.get("compilation_settings", "default"),
        ffmpeg_bin,
    )


def ffmpeg_worker(idle: dict) -> str | None:
    """An idle worker (idle_machines()) with ffmpeg to compile a preview on,
    never this machine's own -- here, the host runs it itself."""
    me = get_machine_id()
    return next((u for u, w in idle.items() if u != me and w.get("ffmpeg")), None)


def send_preview_compile(job_path: Path, uuid: str, idle: dict) -> bool:
    """Send a queued preview's compile to worker uuid: a compile request, the
    job at preview_start on it (compile_machine), the machine taken out of
    idle. The request first: one left without its job written is dropped by
    the worker (_still_mine()). True if sent."""
    with locked_json(job_path) as box:
        data = box["data"] or {}
        history = data.get("stage_history") or []
        if not history or history[-1]["stage"] != "preview_queued":
            return False
        from .workers import compile_request  # local: workers -> loop -> here

        compile_request(data["job_id"], uuid)
        idle_worker = idle.pop(uuid, None) or {}
        data["compile_machine"] = uuid
        history.append({"stage": "preview_start", "at": now(), "machine": uuid})
        box["action"] = "to_write"
    log(
        "INFO",
        "farm",
        f"Preview {data['filepath']}: compiling on "
        f"{idle_worker.get('machine') or uuid[:8]}.",
    )
    return True


def check_remote_compile(job_path: Path, data: dict) -> None:
    """A preview compiling on a worker (compile_machine): back to
    preview_queued -- sent out again next tick, to a worker or here -- once
    that machine is gone, or no longer on it (stopped, restarted). Its end
    is the worker's to write (_end_compile()). The request before the
    worker file, as _on_this_render(): a worker takes it under its own
    file's lock, unreadable (None) meanwhile."""
    from .queue import _read_worker, _worker_gone, resume_interrupted_stage
    from .workers import compile_request_path

    uuid, job_id = data["compile_machine"], data["job_id"]
    request = compile_request_path(job_id, uuid)
    waiting = request.exists()
    worker = _read_worker(uuid)
    if worker is None:
        return  # can't tell this tick
    if waiting:
        if not _worker_gone(worker):
            return  # not taken up yet
        request.unlink(missing_ok=True)
    elif (
        not _worker_gone(worker)
        and worker.get("status") == "compile"
        and worker.get("current_job_id") == job_id
    ):
        return
    with locked_json(job_path) as box:
        data = box["data"] or {}
        history = data.get("stage_history") or []
        if (
            not history
            or history[-1]["stage"] != "preview_start"
            or data.get("compile_machine") != uuid
        ):
            return  # ended meanwhile
        name = worker.get("machine") or uuid[:8]
        if resume_interrupted_stage(data, f"lost on {name}"):
            box["action"] = "to_write"


def run_preview_compile(job_id: str, project_root: Path) -> None:
    """Launch ffmpeg to concat a preview job's resolved sources, here."""
    job_path = ConfigCache.get_path("farm_actives") / f"{job_id}.json"
    try:
        with locked_json(job_path) as box:
            data = box["data"] or {}
            ffmpeg_bin = resolve_ffmpeg()
            if not ffmpeg_bin:
                data["stage_history"].append({"stage": "preview_failed", "at": now()})
                box["action"] = "to_write"
                raise PipelineError("FFMPEG is not installed")

            cmd = preview_command(data, project_root, ffmpeg_bin)
            proc = [
                (
                    popen_logged(cmd, data["job_id"], "preview"),
                    "local",
                )
            ]
            data["stage_history"].append({"stage": "preview_start", "at": now()})
            box["action"] = "to_write"
            track_local_processes(data, proc)

    except Exception as e:
        from .queue import mark_stage

        mark_stage(job_path, "preview_failed")  # separate transaction, actually commits
        log("ERROR", "farm", f"Preview compile failed for {job_id}: {e}")
