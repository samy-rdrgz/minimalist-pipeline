"""Preview compilation providers: resolve which shots' mp4s go into a block
or sequence preview -- filesystem-only, no bpy needed."""

import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from .config import ConfigCache, json_get, parse_filename, shots_in_segment
from .monitoring.tracking import ARCHIVE_DIRNAME


def render_root(project_root: Path, owner_dir: Path) -> Path:
    """Render folder of an asset/shot folder: renders/<seq>/<shot> for a
    shot (no "shots/" level -- every shot reader expects it there),
    renders/assets/<prefix>/<asset> (or library/...) for the rest. Pure
    path work, no disk."""
    project_root, owner_dir = Path(project_root), Path(owner_dir)
    try:
        return project_root / "renders" / owner_dir.relative_to(project_root / "shots")
    except ValueError:
        return project_root / "renders" / owner_dir.relative_to(project_root)


# A render's department (its preset's), written in its folder when the farm
# finishes it: main_render_dir() ranks by it without reading the history.
DEPARTMENT_FILE = ".department"


def render_department(folder: Path) -> str:
    """The department a render folder was made for (DEPARTMENT_FILE), ""
    for none -- one from before 1.2, a preset naming none."""
    try:
        return (Path(folder) / DEPARTMENT_FILE).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return ""


def main_render_dir(shot_dir: Path, v_prefix: str = "v", stages: dict | None = None) -> Path | None:
    """The shot's main render increment folder (v004-stable_002...): of its
    highest stage's department (stages {department: stage}; the project's
    for its kind by default), a render with a department before one with
    none, then the highest version and increment -- read from the folder
    names, not mtime. None if never rendered. Pure os: thread-safe. See
    NOTES.md, "Renders by department"."""
    pattern = re.compile(
        rf"^{re.escape(v_prefix)}(?P<num>\d+)(?:-[a-z]+)?_(?P<inc>\d+)$"
    )
    if stages is None:
        stages = _stages_for(Path(shot_dir))
    candidates = []
    try:
        for d in Path(shot_dir).iterdir():
            if d.is_dir() and (m := pattern.match(d.name)):
                dep = render_department(d)
                candidates.append((bool(dep), stages.get(dep, 0), int(m["num"]), int(m["inc"]), d))
    except OSError:
        return None
    return max(candidates)[4] if candidates else None


def _stages_for(render_dir: Path) -> dict:
    """The project's stages for a render folder's kind (under renders/assets
    or renders/library: the assets'), {} when it can't tell."""
    try:
        from .monitoring.status import project_stages

        kind = "assets" if {"assets", "library"} & set(render_dir.parts) else "shots"
        return project_stages(ConfigCache.get(), kind)
    except Exception:
        return {}


# A render's compiled video: mp4 by default, the ffmpeg preset's
# "extension" otherwise (a ProRes .mov for the edit...).
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".m4v")


def is_video(name: str) -> bool:
    """A compiled video's file name (VIDEO_EXTS), never a temporary one."""
    name = name.lower()
    return name.endswith(VIDEO_EXTS) and ".tmp." not in name


def _first_mp4(render_dir: Path | None) -> Path | None:
    """The video in an increment folder (an mp4, or the preset's other
    extension -- VIDEO_EXTS), None if none (or no folder)."""
    if render_dir is None:
        return None
    try:
        videos = sorted(f for f in Path(render_dir).iterdir() if is_video(f.name) and f.is_file())
    except OSError:
        return None
    return videos[0] if videos else None


def _rendered_segments(
    sequence_dir: Path, shots: list[int] | None, config: dict
) -> list[tuple[list[int], str, Path]]:
    """(shot numbers, folder name, latest mp4) of every rendered folder of a
    sequence -- a shot's (sh030) or a block rendered whole (sh030-040-050)
    -- only those within shots when given. Pure os: thread-safe."""
    shot_prefix = json_get(config, "naming.shot.prefix", "sh")
    v_prefix = json_get(config, "naming.version.prefix", "v")
    pattern = re.compile(rf"^{re.escape(shot_prefix)}(?P<seg>\d+(?:-\d+)*)$")
    out = []
    try:
        folders = [d for d in sequence_dir.iterdir() if d.is_dir()]
    except OSError:
        return []
    for d in folders:
        if not (m := pattern.match(d.name)):
            continue
        numbers = shots_in_segment(m["seg"])
        if shots is not None and not set(numbers) <= set(shots):
            continue
        if mp4 := _first_mp4(main_render_dir(d, v_prefix)):
            out.append((numbers, d.name, mp4))
    return out


def _newest_cover(rendered: list, dropped: list | None) -> list[tuple[str, Path]]:
    """(label, mp4) by shot number, one video per shot: the most recent one
    wins where a block rendered whole and its shots' own renders overlap.
    One left out with shots no other video covers goes into dropped (when
    given) as (label, labels of the newer ones) -- see NOTES.md,
    "Preview compile (§1.6)"."""

    def mtime(mp4: Path) -> float:
        try:
            return mp4.stat().st_mtime
        except OSError:
            return 0.0

    covered, kept, lost = {}, [], []
    for numbers, label, mp4 in sorted(rendered, key=lambda r: -mtime(r[2])):
        if any(n in covered for n in numbers):
            lost.append((numbers, label))
            continue
        kept.append((numbers, label, mp4))
        covered.update(dict.fromkeys(numbers, label))
    if dropped is not None:
        for numbers, label in sorted(lost):
            if any(n not in covered for n in numbers):
                newer = sorted({covered[n] for n in numbers if n in covered})
                dropped.append((label, newer))
    return [(label, mp4) for _, label, mp4 in sorted(kept)]


def resolve_block_sources(
    filepath: Path,
    project_root: Path,
    config: dict | None = None,
    dropped: list | None = None,
) -> list[tuple[str, Path]]:
    """(label, mp4) pairs for filepath's own block, in shot order: its
    shots' renders and its own whole one, the newest where they overlap
    (_newest_cover(), dropped likewise)."""
    config = config if config is not None else ConfigCache.get()
    parsed = parse_filename(Path(filepath).name)
    naming = config.get("naming", {})
    if not parsed or not parsed.get("shot") or not naming:
        return []
    sequence_label = f"{naming['sequence']['prefix']}{parsed['sequence']}"
    rendered = _rendered_segments(
        project_root / "renders" / sequence_label,
        shots_in_segment(parsed["shot"]),
        config,
    )
    return _newest_cover(rendered, dropped)


def resolve_sequence_sources(
    sequence_label: str,
    project_root: Path,
    config: dict | None = None,
    dropped: list | None = None,
) -> list[tuple[str, Path]]:
    """(label, mp4) pairs for every shot ever rendered in the sequence
    ("sq030"), in shot order: shots' own renders and blocks rendered whole
    (sh030-040-050), the newest where they overlap (_newest_cover(),
    dropped likewise)."""
    config = config if config is not None else ConfigCache.get()
    rendered = _rendered_segments(project_root / "renders" / sequence_label, None, config)
    return _newest_cover(rendered, dropped)


def _asset_render_dirs(base: Path, v_prefix: str, depth: int = 4) -> list[Path]:
    """Asset/library render folders under base (renders/assets...): the
    ones holding render increment folders, found without descending into
    those (thousands of frames each). old/ (archived) and _preview/ skipped."""
    increment = re.compile(rf"^{re.escape(v_prefix)}\d+(?:-[a-z]+)?_\d+$")
    try:
        subdirs = [d for d in Path(base).iterdir() if d.is_dir()]
    except OSError:
        return []
    if any(increment.match(d.name) for d in subdirs):
        return [Path(base)]
    if depth <= 0:
        return []
    out = []
    for d in sorted(subdirs):
        if d.name not in (ARCHIVE_DIRNAME, "_preview"):
            out += _asset_render_dirs(d, v_prefix, depth - 1)
    return out


def latest_asset_videos(project_root: Path, v_prefix: str = "v") -> list[Path]:
    """Every asset/library's latest video (renders/assets/..., renders/
    library/...; old/ skipped), the ones with one."""
    renders = Path(project_root) / "renders"
    return [
        mp4
        for top in ("assets", "library")
        for d in _asset_render_dirs(renders / top, v_prefix)
        if (mp4 := _first_mp4(main_render_dir(d, v_prefix)))
    ]


# Past this width the browsers' hardware decoders refuse a video (8192 on
# most PCs and iPads; a panoramic render goes past it). A video they can't
# play gets a light copy beside it, in its render folder's ld/ -- made by
# the farm's compilation, else by Export snapshot (ensure_ld()) --: what
# the snapshot plays and carries, the full one kept for the edit.
MAX_VIDEO_WIDTH = 8192
LD_DIR = "ld"
# The light copy: H.265 in mp4 tagged hvc1 -- what browsers, Safari and
# iPad included, play up to MAX_VIDEO_WIDTH.
LD_ARGS = [
    "-c:v", "libx265", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p",
    "-tag:v", "hvc1", "-movflags", "+faststart",
]
# Every video carries a sound track (phase 5b): the render's mixdown
# (lib/sound.py), else silence -- a sequence preview puts them end to end,
# a track missing in one would leave it out of all. At this rate, AAC in
# an mp4 (the light copy's, the browsers'), PCM in a .mov (the edit's).
AUDIO_RATE = 48000
AAC_ARGS = ["-c:a", "aac", "-b:a", "192k"]
# The light copy's size: MAX_VIDEO_WIDTH wide at most, even (H.265 in
# yuv420p takes no odd size -- a 3361 px wide render), its height to match.
LD_SCALE = f"scale='min({MAX_VIDEO_WIDTH},trunc(iw/2)*2)':-2"
# ffmpeg -i's video stream line: its codec, its tag (hev1...), its size.
_VIDEO_STREAM = re.compile(r"Video: (\w+)[^\n]*?(?:\((\w{4}) /[^\n]*?)?, (\d{1,5})x(\d{1,5})")
# Its sound stream's codec, and the file's duration.
_AUDIO_STREAM = re.compile(r"Stream #[^\n]*?Audio: (\w+)")
_DURATION = re.compile(r"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)")


def ld_path(video: Path) -> Path:
    """Where a render video's light copy goes: <render folder>/ld/<name>.mp4."""
    video = Path(video)
    return video.parent / LD_DIR / f"{video.stem}.mp4"


def browser_codec(codec: str) -> bool:
    """A codec browsers play (H.264, H.265), from an ffmpeg codec or
    encoder name -- libx265, hevc_nvenc, h264..."""
    codec = codec.lower()
    return any(k in codec for k in ("264", "265", "hevc", "avc"))


def _report(path: Path | str, ffmpeg: str, timeout: float) -> str | None:
    """ffmpeg's own report on a file (no ffprobe needed); None if unread."""
    try:
        return subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(path)],
            check=False,  # no output file: ffmpeg always "fails" here
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        ).stderr
    except (OSError, subprocess.SubprocessError):
        return None


def _video_of(report: str | None) -> tuple[str, str, int, int] | None:
    m = _VIDEO_STREAM.search(report or "")
    return (m[1], m[2] or "", int(m[3]), int(m[4])) if m else None


def video_info(path: Path | str, ffmpeg: str, timeout: float = 60) -> tuple[str, str, int, int] | None:
    """(codec, tag, width, height) of a video's or an image's stream, read
    from ffmpeg's own report; None if unread."""
    return _video_of(_report(path, ffmpeg, timeout))


def media_info(path: Path | str, ffmpeg: str, timeout: float = 60) -> dict | None:
    """A video's streams: {"video": video_info()'s tuple or None, "audio":
    its sound's codec ("" without one), "duration": seconds or None}. None
    if unread."""
    report = _report(path, ffmpeg, timeout)
    if report is None:
        return None
    audio = _AUDIO_STREAM.search(report)
    d = _DURATION.search(report)
    return {
        "video": _video_of(report),
        "audio": audio[1] if audio else "",
        "duration": int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3]) if d else None,
    }


# Videos read once and found playable as they are, by (path, modification
# time): the next export doesn't ask ffmpeg again.
_PLAYABLE: set = set()


def ensure_ld(video: Path, ffmpeg: str) -> Path | None:
    """The video's light copy (ld_path()), made now if the video needs one
    and it's missing or older: too wide, a codec browsers don't play, or
    playable but not as it is -- in a .mov, H.265 tagged hev1, a sound
    other than AAC (then put in an mp4, the picture not re-encoded). Its
    sound goes with it. None when the video plays as is, or can't be read. Raises subprocess.CalledProcessError
    / OSError if making it fails."""
    video, ld = Path(video), ld_path(video)
    try:
        if ld.stat().st_mtime >= video.stat().st_mtime:
            return ld
    except OSError:
        pass
    try:
        key = (str(video), video.stat().st_mtime)
    except OSError:
        return None
    if key in _PLAYABLE:
        return None
    media = media_info(video, ffmpeg)
    info = media and media["video"]
    if info is None:
        return None
    codec, tag, width, _ = info
    # Its sound kept: AAC copied as it is, anything else (a .mov's PCM)
    # made AAC -- an mp4's sound browsers play.
    audio = media["audio"]
    sound = ["-map", "0:a:0?", *(["-c:a", "copy"] if audio == "aac" else AAC_ARGS)]
    if width > MAX_VIDEO_WIDTH or not browser_codec(codec):
        args = ["-map", "0:v:0", "-vf", LD_SCALE, *LD_ARGS, *sound]
    elif video.suffix.lower() != ".mp4" or (codec == "hevc" and tag != "hvc1") or audio not in ("", "aac"):
        # Playable as such, but not in a .mov / .mkv, tagged hev1, or a
        # sound browsers don't play: put in an mp4, the picture as it is.
        tag_args = ["-tag:v", "hvc1"] if codec == "hevc" else []
        args = ["-map", "0:v:0", "-c:v", "copy", *tag_args, *sound, "-movflags", "+faststart"]
    else:
        _PLAYABLE.add(key)
        return None
    ld.parent.mkdir(exist_ok=True)
    tmp = ld.with_name(f"{ld.stem}.tmp.mp4")
    try:
        subprocess.run(
            [ffmpeg, "-v", "error", "-y", "-i", str(video), *args, "-f", "mp4", str(tmp)],
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )
        os.replace(tmp, ld)
    finally:
        if tmp.exists():
            tmp.unlink()
    return ld


def browser_video(render_dir: Path | None) -> Path | None:
    """The video a browser plays for a render: its light copy if it has
    one, else its own mp4. None without either."""
    if render_dir is None:
        return None
    return _first_mp4(Path(render_dir) / LD_DIR) or _first_mp4(render_dir)


def zip_videos(videos: list[tuple[Path, str]], zip_path: Path) -> int:
    """Videos [(mp4, name)] into zip_path under their names
    (lib/monitoring/snapshot.py snapshot_videos()). Stored, not compressed: an mp4
    already is. Written beside then renamed, never left half-written.
    Returns how many."""
    zip_path = Path(zip_path)
    if not videos:
        return 0
    tmp = zip_path.with_name(f"{zip_path.name}.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
            for mp4, name in videos:
                z.write(mp4, name)
        os.replace(tmp, zip_path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return len(videos)


def copy_videos(videos: list[tuple[Path, str]], folder: Path) -> tuple[int, int]:
    """Videos [(mp4, name)] into folder under their names, only those not
    there yet or changed since (size, modification time) -- a folder kept
    from one snapshot to the next copies only what's new. Each one written
    beside then renamed. Returns (copied, already there)."""
    folder = Path(folder)
    copied = kept = 0
    for mp4, name in videos:
        dst = folder / name
        try:
            src_stat, dst_stat = mp4.stat(), dst.stat()
            if src_stat.st_size == dst_stat.st_size and int(
                src_stat.st_mtime
            ) == int(dst_stat.st_mtime):
                kept += 1
                continue
        except OSError:
            pass
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(f"{dst.stem}.tmp.mp4")
        try:
            shutil.copy2(mp4, tmp)
            os.replace(tmp, dst)
        finally:
            if tmp.exists():
                tmp.unlink()
        copied += 1
    return copied, kept


def videos_in(folder: Path) -> list[str]:
    """The videos already in a snapshot videos folder, by their names
    (sq100/sh030/v002_001/sq100_sh030.mp4): what earlier exports copied there
    counts too. [] without the folder."""
    folder = Path(folder)
    out = []
    for dirpath, _dirs, files in os.walk(folder):
        for f in files:
            if is_video(f):
                out.append(Path(dirpath, f).relative_to(folder).as_posix())
    return sorted(out)

