"""Post-render pipeline stages: frame integrity check and video compilation, both via ffmpeg."""

from pathlib import Path

import bpy

from ..lib import (
    AAC_ARGS,
    AUDIO_RATE,
    LD_ARGS,
    LD_SCALE,
    MAX_VIDEO_WIDTH,
    ConfigCache,
    PipelineError,
    browser_codec,
    get_machine_id,
    json_get,
    ld_path,
    locked_json,
    log,
    resolve_ffmpeg,
    run_thumbnail_jobs,
    thumbnail_jobs,
    thumbnail_size,
    to_absolute,
)
from ..lib.preview import media_info, video_info
from .dispatch import popen_logged, track_local_processes
from .stages import add_stage, mark_stage

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

                add_stage(data, "checks_images_start")
                box["action"] = "to_write"

                # Read back by scan_processes() (corrupted_frames()). A
                # file, never a PIPE: a long sequence would fill it and
                # hang ffmpeg for good (see popen_logged()).
                proc = [
                    (
                        popen_logged(
                            cmd,
                            data["job_id"],
                            "checks_images",
                            merge_stdout=False,
                            progress=True,
                        ),
                        "local",
                    )
                ]
                track_local_processes(data, proc)
            else:
                add_stage(data, "checks_images_failed")
                box["action"] = "to_write"
                raise PipelineError("FFMPEG is not installed")
    except Exception as e:

        mark_stage(
            job_path, "checks_images_failed"
        )  # separate transaction, actually commits
        log("ERROR", "farm", f"Checks images failed for {job_path.stem!s} {e}")


# Edit project's Video choice: the compiled video's format, for the edit.
# "preset": config/presets/ffmpeg_presets/default.json as written there (a
# project from before the choice keeps it). Whatever the format, the page
# plays an mp4: a light copy (ld/) is made in the same ffmpeg pass when the
# video itself isn't one a browser plays (_ld_args()).
VIDEO_FORMATS = {
    # H.264, a key frame every 12 and no B-frame: smooth to scrub in an
    # editing timeline (H.265 isn't), light, played as is by the page.
    "mp4": {"codec": "libx264", "preset": "medium", "crf": 18, "pix_fmt": "yuv420p",
            "extra_args": ["-g", "12", "-bf", "0", "-movflags", "+faststart"]},
    # ProRes 422 LT: what editing software reads best (DaVinci Resolve's free
    # version on Linux reads no H.264 / H.265 at all); ~100 Mb/s in 1080p.
    "prores_lt": {"codec": "prores_ks", "pix_fmt": "yuv422p10le", "extension": "mov",
                  "extra_args": ["-profile:v", "1", "-vendor", "apl0"]},
}


def video_format(config: dict | None = None) -> str:
    """The project's Video choice: "mp4", "prores_lt" or "preset"."""
    config = ConfigCache.get() if config is None else config
    fmt = json_get(config or {}, "video.format", "preset")
    return fmt if fmt in VIDEO_FORMATS or fmt == "preset" else "preset"


def resolve_ffmpeg_preset(preset_name: str | None) -> dict:
    """The compilation's ffmpeg preset: the project's Video format, unless
    it says "preset" or a preset is named -- then that preset file, falling
    back to default.json."""
    name = preset_name or "default"
    fmt = video_format()
    if name == "default" and fmt in VIDEO_FORMATS:
        return dict(VIDEO_FORMATS[fmt])
    presets_dir = ConfigCache.get_path("ffmpeg_presets")
    path = presets_dir / f"{name}.json"
    if not path.exists():
        path = presets_dir / "default.json"
    # Read only: a preset is read here, never written -- no lock to take.
    with locked_json(path, read_only=True) as box:
        return box["data"] or {}


def _ffmpeg_preset_to_args(preset: dict) -> list[str]:
    """Convert a preset dict (codec/preset/crf/pix_fmt/extra_args) into ffmpeg CLI flags."""
    args = []
    for key in ("codec", "preset", "crf", "pix_fmt"):
        if key in preset:
            flag = "-c:v" if key == "codec" else f"-{key}"
            args += [flag, str(preset[key])]
    extra = list(preset.get("extra_args", []))
    # HEVC in an mp4: ffmpeg tags it hev1, which Safari, iPhone and iPad
    # (and QuickTime) refuse to play -- hvc1 plays everywhere.
    codec = str(preset.get("codec", "")).lower()
    if ("265" in codec or "hevc" in codec) and not any(
        a.startswith("-tag") for a in extra
    ):
        extra += ["-tag:v", "hvc1"]
    return args + extra


# 4:2:0 and 4:2:2 -- yuv420p, the default preset's, H.264 and H.265's
# usual -- take even sizes only: a render 3361 px wide failed to compile
# ("Picture width must be an integer multiple of the specified chroma
# subsampling"). One more column (row), a copy of the last one: nothing of
# the render lost, nothing resampled. See NOTES.md, "Odd sizes: one more
# column for the compilation".
_EVEN_PAD = "pad=ceil(iw/2)*2:ceil(ih/2)*2"  # size unread: black, never a failure
def _frame_size(frame: str, ffmpeg_bin: str) -> tuple[int, int] | None:
    """(width, height) of one rendered frame; None if unread."""
    info = video_info(frame, ffmpeg_bin, timeout=30)
    return info[2:] if info else None


def _even_filter(size: tuple[int, int] | None) -> str:
    """The filter making the video's size even: a column (row) more, the
    last one copied (fillborders' smear) -- "" when already even. In RGB
    first (16 bits: a 16-bit PNG keeps its depth): padded in the JPGs'
    yuvj420p, the render's own last column came out black too. Size
    unread: _EVEN_PAD, black, which does nothing on an even size."""
    if not size:
        return _EVEN_PAD
    w, h = size
    right, bottom = w % 2, h % 2
    if not (right or bottom):
        return ""
    return (
        f"format=gbrp16le,pad={w + right}:{h + bottom}:0:0,"
        f"fillborders=right={right}:bottom={bottom}:mode=smear"
    )


def _even_size(preset: dict, args: list[str], size) -> list[str]:
    """args (_ffmpeg_preset_to_args()'s) with _even_filter(size) as the
    video's last filter -- after the preset's own -vf, if it has one --
    unless its pix_fmt keeps every pixel's colour (4:4:4, RGB, grey), which
    takes any size. The compilation's only: a concat's filter_complex
    already pads to the project's resolution."""
    pix = str(preset.get("pix_fmt") or "").lower()
    even = _even_filter(size)
    if not even or any(k in pix for k in ("444", "rgb", "gbr", "gray")):
        return list(args)
    args = list(args)
    for flag in ("-vf", "-filter:v"):
        if flag in args[:-1]:
            i = args.index(flag) + 1
            args[i] = f"{args[i]},{even}"
            return args
    return ["-vf", even, *args]


def _ld_args(width, preset: dict, video: Path, sound: list[str] = ()) -> list[str]:
    """The compilation's second output, a light copy browsers can play
    (lib/preview.py ld_path()), when the video itself won't: wider than
    MAX_VIDEO_WIDTH, a codec they don't play (ProRes, DNxHR...), or not an
    mp4. [] when it plays as is -- a light copy left from before, now
    stale, removed. sound: the video's maps and audio filter (_sound()),
    its codec here AAC."""
    ld = ld_path(video)
    if (
        (width or 0) <= MAX_VIDEO_WIDTH
        and browser_codec(str(preset.get("codec", "libx264")))
        and video.suffix.lower() == ".mp4"
    ):
        ld.unlink(missing_ok=True)
        return []
    ld.parent.mkdir(parents=True, exist_ok=True)
    audio = [*sound, *AAC_ARGS] if sound else []
    return ["-vf", LD_SCALE, *LD_ARGS, *audio, str(ld)]


# A shot rendered without sound: silence, as long as its frames.
SILENCE = f"anullsrc=r={AUDIO_RATE}:cl=stereo"


def audio_codec_args(preset: dict, ext: str) -> list[str]:
    """The video's sound codec: the preset's "audio_args" if it has some
    (["-an"]: none), PCM in a .mov (the edit's -- DaVinci Resolve's free
    version on Linux reads no AAC), Opus in a .webm, else AAC."""
    if "audio_args" in preset:
        return [str(a) for a in preset["audio_args"]]
    ext = ext.lower().lstrip(".")
    if ext == "mov":
        return ["-c:a", "pcm_s16le"]
    if ext == "webm":
        return ["-c:a", "libopus", "-b:a", "160k"]
    return list(AAC_ARGS)


def _sound(frames: int, fps) -> list[str]:
    """An output's maps and audio filter: the picture (input 0), the sound
    (input 1) at AUDIO_RATE, padded with silence or cut to the sample to
    last as the frames do -- a mixdown a little short or long (fps, range)
    never shifts the next shot of a preview."""
    samples = round(int(frames) * AUDIO_RATE / float(fps))
    return ["-map", "0:v:0", "-map", "1:a:0",
            "-af", f"aresample={AUDIO_RATE},apad,atrim=end_sample={samples}"]


def compile_command(
    *, ffmpeg_bin: str, frames_pattern: str, first: int, last: int, fps,
    preset: dict, video: Path, width=None, size=None, audio: Path | None = None,
    sound: bool = True,
) -> list[str]:
    """The compilation's ffmpeg command: frames first..last at fps into
    video, its sound -- audio (the render's mixdown) if it's a file, else
    silence; none at all with sound False (submitted without) -- and its
    light copy if it needs one, in one pass."""
    if audio is not None and Path(audio).is_file():
        sound_in = ["-i", str(audio)]
    else:
        sound_in = ["-f", "lavfi", "-i", SILENCE]
    codec = audio_codec_args(preset, video.suffix) if sound else ["-an"]
    sound = [] if "-an" in codec else _sound(last - first + 1, fps)
    return (
        [ffmpeg_bin, "-y", "-r", str(fps), "-start_number", str(first), "-i", frames_pattern]
        + (sound_in if sound else [])
        + _even_size(preset, _ffmpeg_preset_to_args(preset), size)
        + (sound + codec if sound else codec)
        + [str(video)]
        # Same pass: the light copy, if the video needs one.
        + _ld_args(width, preset, video, sound)
    )


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
                preset = resolve_ffmpeg_preset(compilation_settings)
                video = Path(
                    to_absolute(
                        data.get("compiled_output_path", str(project_root)),
                        project_root,
                    )
                )
                # The preset's container ("extension": "mov"...), mp4 if
                # none: the video's name follows, written back to the job.
                ext = str(preset.get("extension") or "mp4").lstrip(".").lower()
                if video.suffix.lower() != f".{ext}":
                    video = video.with_suffix(f".{ext}")
                    stem = data["compiled_output_path"].rsplit(".", 1)[0]
                    data["compiled_output_path"] = f"{stem}.{ext}"
                first = data["resolved_frame_range"][0]
                prefix = str(abs_path).split("#")[0]
                digits = data["output_path"].count("#")
                extension = _EXTENSION_MAP.get(data["output_extension"], "png")
                # Its real size, not the job's: odd, one column (row) more.
                size = _frame_size(
                    f"{prefix}{int(first):0{digits}d}.{extension}", ffmpeg_bin
                )
                audio = data.get("audio_path")
                cmd = compile_command(
                    ffmpeg_bin=ffmpeg_bin,
                    frames_pattern=f"{prefix}%0{digits}d.{extension}",
                    first=int(first),
                    last=int(data["resolved_frame_range"][1]),
                    fps=framerate,
                    preset=preset,
                    video=video,
                    width=data.get("width"),
                    size=size,
                    audio=to_absolute(audio, project_root) if audio else None,
                    sound=data.get("sound", True),
                )
                proc = [
                    (
                        popen_logged(
                            cmd, data["job_id"], "compilation", progress=True
                        ),
                        "local",
                    )
                ]
                add_stage(data, "compilation_start")
                box["action"] = "to_write"
                track_local_processes(data, proc)

            else:
                add_stage(data, "compilation_failed")
                box["action"] = "to_write"
                raise PipelineError("FFMPEG is not installed")
    except Exception as e:

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
    actually found. The sound follows: each input's own, silence for one
    without (rendered before the sound, or its preset's "-an") -- read
    here, one ffmpeg report per input."""
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
    for i, p in enumerate(inputs):
        parts.append(f"{_concat_sound(i, media_info(p, ffmpeg_bin, timeout=30))}[a{i}]")
    parts.append(
        "".join(f"[v{i}][a{i}]" for i in range(len(inputs)))
        + f"concat=n={len(inputs)}:v=1:a=1[outv][outa]"
    )

    cmd += ["-filter_complex", ";".join(parts), "-map", "[outv]", "-map", "[outa]"]
    # A sequence preview is for watching (the page, the player): an mp4 a
    # browser plays -- a ProRes preset (Video: MOV) wouldn't even go in one.
    preset = resolve_ffmpeg_preset(compilation_settings)
    if not browser_codec(str(preset.get("codec", ""))) or str(preset.get("extension") or "mp4").lower() != "mp4":
        preset = VIDEO_FORMATS["mp4"]
    cmd += _ffmpeg_preset_to_args(preset) + AAC_ARGS
    cmd += [str(output)]
    return cmd


def _concat_sound(i: int, media: dict | None) -> str:
    """Input i's sound for the concat filter: its own, or silence. Cut to
    the input's duration rounded down (ffmpeg reports it to the
    hundredth): never longer than its picture -- the next shot's would
    start late -- the filter itself filling a sound shorter with silence
    (all but the last input)."""
    duration = (media or {}).get("duration")
    cut = f",atrim=duration={int(duration * 100) / 100:.2f}" if duration else ""
    norm = f"aresample={AUDIO_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo"
    if media and media.get("audio"):
        return f"[{i}:a:0]{norm}{cut}"
    return f"{SILENCE},{norm}{cut or ',atrim=duration=0.04'}"


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
        add_stage(data, "preview_start", machine=uuid)
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
    from .workers import COMPILE, request_path

    uuid, job_id = data["compile_machine"], data["job_id"]
    request = request_path(COMPILE, job_id, uuid)
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
                add_stage(data, "preview_failed")
                box["action"] = "to_write"
                raise PipelineError("FFMPEG is not installed")

            cmd = preview_command(data, project_root, ffmpeg_bin)
            proc = [
                (
                    popen_logged(cmd, data["job_id"], "preview", progress=True),
                    "local",
                )
            ]
            add_stage(data, "preview_start")
            box["action"] = "to_write"
            track_local_processes(data, proc)

    except Exception as e:

        mark_stage(job_path, "preview_failed")  # separate transaction, actually commits
        log("ERROR", "farm", f"Preview compile failed for {job_id}: {e}")
