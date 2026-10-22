# templates/make_thumbnails.py
"""Headless entry point making thumbnails (see lib/thumbnails.py):
load a frame, shrink it, save it as JPEG. Plain bpy, no addon needed --
runs with --factory-startup. Whatever Blender can't load (a multilayer EXR)
goes through ffmpeg when the request names one."""

import json
import os
import subprocess
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
request_path = Path(argv[0])
request = json.loads(request_path.read_text(encoding="utf-8"))
size = request["size"]  # longest side, whatever the aspect ratio
ffmpeg = request.get("ffmpeg")

scene = bpy.context.scene
settings = scene.render.image_settings
settings.file_format = "JPEG"
settings.quality = request["quality"]
settings.color_mode = "RGB"


def _replace(tmp: str, dst: str) -> None:
    """os.replace(tmp, dst) -- atomic: a snapshot reading the thumbnail never
    sees half a file --, retried while Windows refuses it (a reader has dst
    open)."""
    for _ in range(5):
        try:
            os.replace(tmp, dst)
            return
        except PermissionError:  # Windows, a reader has it open
            import time

            time.sleep(0.1)
    os.replace(tmp, dst)


def _with_blender(src: str, tmp: str) -> None:
    """Thumbnail of src into tmp with Blender: scaled, through the view
    transform a float image needs. Raises on what it can't read."""
    img = bpy.data.images.load(src)
    try:
        w, h = img.size
        if not w or not h:
            raise ValueError("Blender can't read it (multilayer EXR?)")
        # A float frame (EXR) goes through the scene's view transform (AgX
        # by default), a byte one (PNG, JPEG...) is already display-ready.
        scene.view_settings.view_transform = "AgX" if img.is_float else "Standard"
        k = size / max(w, h)
        img.scale(max(1, round(w * k)), max(1, round(h * k)))
        img.save_render(tmp, scene=scene)
    finally:
        bpy.data.images.remove(img)


def _with_ffmpeg(src: str, tmp: str, layer: str | None) -> None:
    """Thumbnail of src into tmp with ffmpeg -- a multilayer EXR's layer.
    Raises with ffmpeg's error."""
    cmd = [ffmpeg, "-v", "error", "-y"]
    if layer:
        cmd += ["-layer", layer]
    if src.lower().endswith(".exr"):
        cmd += ["-apply_trc", "iec61966_2_1"]  # linear -> sRGB
    fit = f"scale='if(gte(iw,ih),{size},-2)':'if(gte(iw,ih),-2,{size})'"
    cmd += ["-i", src, "-vf", fit, "-frames:v", "1", "-q:v", "4", tmp]
    done = subprocess.run(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120
    )
    if done.returncode != 0 or not os.path.getsize(tmp):
        raise RuntimeError(done.stderr.decode("utf-8", "replace").strip()[:200])


results = {}
for job in request["jobs"]:
    src, dst = job["src"], job["dst"]
    tmp = f"{dst}.tmp.jpg"
    try:
        try:
            _with_blender(src, tmp)
        except Exception as e:
            if not ffmpeg:
                raise RuntimeError(f"{e}; ffmpeg not found on this machine") from e
            _with_ffmpeg(src, tmp, job.get("layer"))
        _replace(tmp, dst)
        results[dst] = "ok"
    except Exception as e:
        results[dst] = str(e) or type(e).__name__
        try:
            os.remove(tmp)
        except OSError:
            pass

if request.get("detach"):
    request_path.unlink(missing_ok=True)
else:
    request_path.write_text(json.dumps({"results": results}), encoding="utf-8")
