"""Thumbnails: one small JPEG per asset/shot render folder, made from the
middle frame of its latest render, in a disposable headless Blender (see
NOTES.md, "Thumbnails"). Everything here but the launch is pure os:
thread-safe."""

import json
import os
import struct
import subprocess
import tempfile
from pathlib import Path

from .core import json_get
from .preview import latest_render_dir, render_root

# Longest side, any aspect ratio (a 9:16 render gives 135x240) -- the
# project's "thumbnails.size" (Edit project), this when it has none.
THUMB_SIZE = 240
THUMB_QUALITY = 70

_FRAME_EXTS = {
    ".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".tga", ".bmp",
    ".webp", ".dpx", ".cin", ".hdr", ".jp2",
}  # fmt: skip

_ENTRY = Path(__file__).resolve().parent.parent / "templates" / "make_thumbnails.py"


def thumbnail_size(config: dict) -> int:
    """The project's thumbnail size (longest side, px), kept sane."""
    try:
        size = int(json_get(config, "thumbnails.size", THUMB_SIZE))
    except (TypeError, ValueError):
        return THUMB_SIZE
    return max(32, min(2048, size))


def jpeg_size(path: Path) -> tuple[int, int] | None:
    """(width, height) from a JPEG's header (its SOF segment), or None.
    Reads the first 64 KB only."""
    try:
        with open(path, "rb") as f:
            data = f.read(65536)
    except OSError:
        return None
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    try:
        while i + 9 < len(data):
            if data[i] != 0xFF:
                return None
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            (length,) = struct.unpack(">H", data[i + 2 : i + 4])
            # SOF0..SOF15, minus DHT (C4), JPG (C8) and DAC (CC)
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return w, h
            i += 2 + length
    except struct.error:
        return None
    return None


def thumbnail_path(render_dir: Path) -> Path:
    """Named after the file's base name: renders/sq030/sh040/
    sq030_sh040_thumbnail.jpg (a shot folder is only "sh040"),
    renders/assets/ch/ch_bob/ch_bob_thumbnail.jpg (an asset folder already
    carries its prefix)."""
    d = Path(render_dir)
    name = d.name if d.name.startswith(f"{d.parent.name}_") else f"{d.parent.name}_{d.name}"
    return d / f"{name}_thumbnail.jpg"


def owner_render_dir(project_root: Path, owner: Path) -> Path:
    """Render folder whose thumbnail stands for an asset/shot folder (see
    render_root()) -- a block's first shot (sh010-020-040 -> sh010). Pure
    path work, no disk."""
    project_root, owner = Path(project_root), Path(owner)
    d = render_root(project_root, owner)
    if owner.parent.parent == project_root / "shots":
        return d.with_name(d.name.split("-", 1)[0])
    return d


def owner_shot_render_dirs(project_root: Path, owner: Path) -> list[tuple[str, Path]]:
    """[(shot label, render folder)] for each shot of a block, in its order
    (sh010-020-040 -> sh010, sh020, sh040), [] for a lone shot or an
    asset -- owner_render_dir() stands for those. Pure path work."""
    project_root, owner = Path(project_root), Path(owner)
    if owner.parent.parent != project_root / "shots" or "-" not in owner.name:
        return []
    d = render_root(project_root, owner)
    first, *rest = d.name.split("-")
    prefix = first.rstrip("0123456789")
    labels = [first] + [f"{prefix}{n}" for n in rest]
    return [(label, d.with_name(label)) for label in labels]


def source_frame(shot_render_dir: Path, v_prefix: str = "v") -> Path | None:
    """Middle frame of the shot's latest render (the first is often a
    hold), skipping empty files -- the placeholders of a render before
    1.1.0, which may still be the latest."""
    latest = latest_render_dir(shot_render_dir, v_prefix)
    if latest is None:
        return None
    try:
        frames = sorted(
            e.path
            for e in os.scandir(latest)
            if os.path.splitext(e.name)[1].lower() in _FRAME_EXTS
            and e.stat().st_size > 0
        )
    except OSError:
        return None
    return Path(frames[(len(frames) - 1) // 2]) if frames else None


def exr_layer(path: Path) -> str | None:
    """Layer name of an EXR's first layered channel ("ViewLayer.Combined"
    for "ViewLayer.Combined.R"), preferring a Combined one -- what ffmpeg's
    -layer needs to read a multilayer EXR. None for a plain RGB(A) EXR or
    an unreadable header. Reads the header only."""
    try:
        with open(path, "rb") as f:
            data = f.read(65536)
        if data[:4] != b"\x76\x2f\x31\x01":
            return None
        i, channels = 8, []
        while data[i] != 0:
            end = data.index(b"\0", i)
            name = data[i:end]
            i = data.index(b"\0", end + 1) + 1
            typ = data[end + 1 : i - 1]
            (size,) = struct.unpack("<i", data[i : i + 4])
            value = data[i + 4 : i + 4 + size]
            i += 4 + size
            if name == b"channels" and typ == b"chlist":
                j = 0
                while value[j] != 0:
                    k = value.index(b"\0", j)
                    channels.append(value[j:k].decode("utf-8", "replace"))
                    j = k + 1 + 16  # pixel type, linear, reserved, sampling
                break
    except (OSError, ValueError, IndexError, struct.error):
        return None
    layers = [c.rsplit(".", 1)[0] for c in channels if "." in c]
    if not layers:
        return None
    combined = [lay for lay in layers if lay.endswith("Combined")]
    return (combined or layers)[0]


def thumbnail_jobs(
    shot_render_dirs,
    v_prefix: str = "v",
    force: bool = False,
    size: int = THUMB_SIZE,
) -> list[dict]:
    """{"src", "dst", "layer"} for every shot whose thumbnail is missing,
    older than its source frame, or not at `size` -- the project setting
    changed; a thumbnail's longest side is always exactly the size it was
    made at (all of them with force)."""
    jobs = []
    for shot_dir in shot_render_dirs:
        src = source_frame(shot_dir, v_prefix)
        if src is None:
            continue
        dst = thumbnail_path(shot_dir)
        if not force:
            try:
                if os.stat(dst).st_mtime >= os.stat(src).st_mtime and max(
                    jpeg_size(dst) or (0, 0)
                ) == size:
                    continue
            except OSError:
                pass  # no thumbnail yet
        jobs.append(
            {
                "src": str(src),
                "dst": str(dst),
                "layer": exr_layer(src) if src.suffix.lower() == ".exr" else None,
            }
        )
    return jobs


def run_thumbnail_jobs(
    jobs: list[dict],
    blender_bin: str,
    ffmpeg_bin: str | None = None,
    *,
    size: int = THUMB_SIZE,
    wait: bool = True,
    timeout: float = 900,
) -> dict[str, str]:
    """Make every thumbnail of `jobs` in one headless Blender. wait: block
    (a thread's job) and return {dst: "ok" | why not}; otherwise fire and
    forget (the farm), returns {}. ffmpeg_bin: fallback for what Blender
    can't load (a multilayer EXR)."""
    if not jobs:
        return {}
    fd, tmp = tempfile.mkstemp(suffix=".json", prefix="pipeline_thumbs_")
    request = Path(tmp)
    with open(fd, "w", encoding="utf-8") as f:
        json.dump(
            {
                "jobs": jobs,
                "size": size,
                "quality": THUMB_QUALITY,
                "ffmpeg": ffmpeg_bin,
                "detach": not wait,
            },
            f,
        )
    cmd = [
        blender_bin,
        "-b",
        "--factory-startup",
        "--python",
        str(_ENTRY),
        "--",
        str(request),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    if not wait:
        return {}
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
    try:
        results = json.loads(request.read_text(encoding="utf-8")).get("results")
    except (OSError, ValueError):
        results = None
    finally:
        request.unlink(missing_ok=True)
    if not isinstance(results, dict):
        return {j["dst"]: "thumbnail process failed" for j in jobs}
    return results
