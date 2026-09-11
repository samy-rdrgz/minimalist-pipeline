"""Post-render pipeline stages: frame integrity check and video compilation, both via ffmpeg."""

import subprocess
from pathlib import Path

from ..lib import (
    ConfigCache,
    PipelineError,
    json_get,
    locked_json,
    log,
    now,
    resolve_ffmpeg,
    to_absolute,
)
from .dispatch import _active_processes as _active_processes

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


def checks_images(job_path: Path):
    """Launch an ffmpeg pass over the rendered frame sequence to detect corrupted frames."""
    try:
        global _active_processes
        with locked_json(to_absolute(job_path)) as box:
            data = box["data"] or {}
            ffmpeg_bin = resolve_ffmpeg()
            if ffmpeg_bin:
                path = str(to_absolute(Path(data["output_path"])))
                cmd = [
                    ffmpeg_bin,
                    "-v",
                    "error",
                    "-start_number",
                    str(data["resolved_frame_range"][0]),
                    "-i",
                    f"{path.split('#')[0]}%0{data['output_path'].count('#')}d.{_EXTENSION_MAP.get(data['output_extension'], 'png')}",
                    "-f",
                    "null",
                    "-",
                ]

                data["stage_history"].append(
                    {"stage": "checks_images_start", "at": now()}
                )
                box["action"] = "to_write"

                proc = [
                    (
                        subprocess.Popen(
                            cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            text=True,
                        ),
                        "local",
                    )
                ]
                _active_processes[data["job_id"]] = proc
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
        global _active_processes
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
                        subprocess.Popen(
                            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        ),
                        "local",
                    )
                ]
                data["stage_history"].append(
                    {"stage": "compilation_start", "at": now()}
                )
                box["action"] = "to_write"
                _active_processes[data["job_id"]] = proc

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


def run_preview_compile(job_id: str, project_root: Path) -> None:
    """Launch ffmpeg to concat a preview job's resolved sources."""
    global _active_processes
    job_path = ConfigCache.get_path("farm_actives") / f"{job_id}.json"
    try:
        with locked_json(job_path) as box:
            data = box["data"] or {}
            ffmpeg_bin = resolve_ffmpeg()
            if not ffmpeg_bin:
                data["stage_history"].append({"stage": "preview_failed", "at": now()})
                box["action"] = "to_write"
                raise PipelineError("FFMPEG is not installed")

            config = ConfigCache.get()
            inputs = [to_absolute(src, project_root) for _label, src in data["sources"]]
            output = to_absolute(data["output_path"], project_root)
            output.parent.mkdir(parents=True, exist_ok=True)

            cmd = build_concat_command(
                inputs,
                output,
                config,
                data.get("compilation_settings", "default"),
                ffmpeg_bin,
            )
            proc = [
                (
                    subprocess.Popen(
                        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    ),
                    "local",
                )
            ]
            data["stage_history"].append({"stage": "preview_start", "at": now()})
            box["action"] = "to_write"
            _active_processes[data["job_id"]] = proc

    except Exception as e:
        from .queue import mark_stage

        mark_stage(job_path, "preview_failed")  # separate transaction, actually commits
        log("ERROR", "farm", f"Preview compile failed for {job_id}: {e}")
