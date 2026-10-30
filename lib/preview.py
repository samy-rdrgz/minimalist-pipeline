"""Preview compilation providers: resolve which shots' mp4s go into a block
or sequence preview -- filesystem-only, no bpy needed."""

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .config import ConfigCache, json_get, parse_filename, shots_in_segment
from .tracking import ARCHIVE_DIRNAME


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


def latest_render_dir(shot_dir: Path, v_prefix: str = "v") -> Path | None:
    """The shot's most recent render increment folder (v004-stable_002...),
    read from the folder names (not mtime). None if never rendered.
    Pure os: thread-safe."""
    pattern = re.compile(
        rf"^{re.escape(v_prefix)}(?P<num>\d+)(?:-[a-z]+)?_(?P<inc>\d+)$"
    )
    candidates = []
    try:
        for d in Path(shot_dir).iterdir():
            if d.is_dir() and (m := pattern.match(d.name)):
                candidates.append((int(m["num"]), int(m["inc"]), d))
    except OSError:
        return None
    return max(candidates)[2] if candidates else None


def latest_shot_mp4(
    project_root: Path, sequence_label: str, shot_label: str, config: dict | None = None
) -> Path | None:
    """The shot's most recently rendered mp4, read from the increment
    folder's own name (not mtime). None if never rendered, or no mp4 yet."""
    config = config if config is not None else ConfigCache.get()
    latest = latest_render_dir(
        project_root / "renders" / sequence_label / shot_label,
        json_get(config, "naming.version.prefix", "v"),
    )
    return _first_mp4(latest)


def _first_mp4(render_dir: Path | None) -> Path | None:
    """The mp4 in an increment folder, None if none (or no folder)."""
    if render_dir is None:
        return None
    mp4s = sorted(render_dir.glob("*.mp4"))
    return mp4s[0] if mp4s else None


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
        if mp4 := _first_mp4(latest_render_dir(d, v_prefix)):
            out.append((numbers, d.name, mp4))
    return out


def _newest_cover(rendered: list, dropped: list | None) -> list[tuple[str, Path]]:
    """(label, mp4) by shot number, one video per shot: the most recent one
    wins where a block rendered whole and its shots' own renders overlap.
    One left out with shots no other video covers goes into dropped (when
    given) as (label, labels of the newer ones) -- see NOTES.md, "A block
    rendered whole"."""

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
        if (mp4 := _first_mp4(latest_render_dir(d, v_prefix)))
    ]


# Past this width the browsers' hardware decoders refuse a video (8192 on
# most PCs and iPads; a panoramic render goes past it): the snapshot gets a
# scaled-down copy, renders/ keeps the full one for the edit.
MAX_VIDEO_WIDTH = 8192
_VIDEO_SIZE = re.compile(r"Video: .*?(\d{2,5})x(\d{2,5})")


def _video_width(mp4: Path, ffmpeg: str) -> int | None:
    """The video's width, read from ffmpeg's own report; None if unread."""
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(mp4)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
            stdin=subprocess.DEVNULL,
        ).stderr
    except (OSError, subprocess.SubprocessError):
        return None
    m = _VIDEO_SIZE.search(out)
    return int(m[1]) if m else None


def _snapshot_copy(mp4: Path, dst: Path, ffmpeg: str | None) -> bool:
    """mp4 written to dst as the snapshot plays it: as is, or scaled down
    to MAX_VIDEO_WIDTH when wider (H.265, hvc1 -- needs ffmpeg; without
    it, as is). dst keeps mp4's modification time either way: what
    copy_videos() tells a video already there by. True when scaled."""
    width = _video_width(mp4, ffmpeg) if ffmpeg else None
    scaled = bool(width and width > MAX_VIDEO_WIDTH)
    if scaled:
        subprocess.run(
            [
                ffmpeg, "-v", "error", "-y", "-i", str(mp4),
                "-vf", f"scale={MAX_VIDEO_WIDTH}:-2",
                "-c:v", "libx265", "-preset", "fast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-tag:v", "hvc1", "-c:a", "copy",
                "-movflags", "+faststart", "-f", "mp4", str(dst),
            ],
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )
    else:
        shutil.copyfile(mp4, dst)
    st = mp4.stat()
    os.utime(dst, (st.st_atime, st.st_mtime))
    return scaled


def zip_videos(
    videos: list[tuple[Path, str]], zip_path: Path, ffmpeg: str | None = None
) -> int:
    """Videos [(mp4, name)] into zip_path under their names
    (lib/snapshot.py snapshot_videos()), each as _snapshot_copy() writes
    it. Stored, not compressed: an mp4 already is. Written beside then
    renamed, never left half-written. Returns how many."""
    zip_path = Path(zip_path)
    if not videos:
        return 0
    tmp = zip_path.with_name(f"{zip_path.name}.tmp")
    with tempfile.TemporaryDirectory(prefix="pipeline_videos_") as scratch:
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
                for mp4, name in videos:
                    one = Path(scratch, "video.mp4")
                    if _snapshot_copy(mp4, one, ffmpeg):
                        z.write(one, name)
                    else:
                        z.write(mp4, name)
                    one.unlink(missing_ok=True)
            os.replace(tmp, zip_path)
        finally:
            if tmp.exists():
                tmp.unlink()
    return len(videos)


def copy_videos(
    videos: list[tuple[Path, str]], folder: Path, ffmpeg: str | None = None
) -> tuple[int, int, int]:
    """Videos [(mp4, name)] into folder under their names (_snapshot_copy():
    scaled down past MAX_VIDEO_WIDTH), only those not there yet or changed
    since (modification time) -- a folder kept from one snapshot to the
    next copies only what's new. Each one written beside then renamed.
    Returns (copied, already there, of the copied the ones scaled down)."""
    folder = Path(folder)
    copied = kept = scaled = 0
    for mp4, name in videos:
        dst = folder / name
        try:
            if int(mp4.stat().st_mtime) == int(dst.stat().st_mtime):
                kept += 1
                continue
        except OSError:
            pass
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(f"{dst.stem}.tmp.mp4")
        try:
            scaled += _snapshot_copy(mp4, tmp, ffmpeg)
            os.replace(tmp, dst)
        finally:
            if tmp.exists():
                tmp.unlink()
        copied += 1
    return copied, kept, scaled


def videos_in(folder: Path) -> list[str]:
    """The videos already in a snapshot videos folder, by their names
    (sq100/sh030/v002_001/sq100_sh030.mp4): what earlier exports copied there
    counts too. [] without the folder."""
    folder = Path(folder)
    out = []
    for dirpath, _dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(".mp4") and not f.lower().endswith(".tmp.mp4"):
                out.append(Path(dirpath, f).relative_to(folder).as_posix())
    return sorted(out)

