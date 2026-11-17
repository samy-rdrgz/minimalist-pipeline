"""Edit project's Video choice (farm/post_render.py VIDEO_FORMATS): the
preset each format gives, the light copy beside a ProRes .mov made in the
same pass, a sequence preview an mp4 a browser plays whatever the format.
Run with ffmpeg for real when there is one.

    python3 tests/test_video_formats.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def _probe(path: Path) -> tuple[str, str]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,pix_fmt", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    codec, pix = (out.split(",") + [""])[:2]
    return codec, pix


def main() -> None:
    import importlib

    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    config = importlib.import_module(f"{pkg.__name__}.lib.config")
    post = importlib.import_module(f"{pkg.__name__}.farm.post_render")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "proj"
        presets = root / "config" / "presets" / "ffmpeg_presets"
        presets.mkdir(parents=True)
        (presets / "default.json").write_text(json.dumps({"codec": "libx265", "crf": 20}), encoding="utf-8")
        cfg = root / "config" / "project_config.json"
        config.set_daemon_active_project_root(root)

        def use(fmt):
            data = {"resolution": {"x": 320, "y": 180}, "default_fps": 30}
            if fmt is not None:
                data["video"] = {"format": fmt}
            cfg.write_text(json.dumps(data), encoding="utf-8")
            config.ConfigCache.invalidate()

        # A project from before the choice: its preset file.
        use(None)
        assert post.video_format() == "preset"
        assert post.resolve_ffmpeg_preset("default")["codec"] == "libx265"
        use("mp4")
        assert post.resolve_ffmpeg_preset(None)["codec"] == "libx264"
        use("prores_lt")
        p = post.resolve_ffmpeg_preset("default")
        assert p["codec"] == "prores_ks" and p["extension"] == "mov", p
        # A preset named on purpose still wins.
        (presets / "draft.json").write_text(json.dumps({"codec": "libx264", "crf": 30}), encoding="utf-8")
        assert post.resolve_ffmpeg_preset("draft")["crf"] == 30
        use("nonsense")
        assert post.video_format() == "preset"

        if not shutil.which("ffmpeg"):
            print("video formats: ok (no ffmpeg: not encoded)")
            return
        frames = Path(d) / "frames"
        frames.mkdir()
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30",
                        "-frames:v", "12", str(frames / "f%04d.png")], check=True)
        out = Path(d) / "out"
        out.mkdir()

        # ProRes: the .mov, and its light copy in the same pass.
        use("prores_lt")
        preset = post.resolve_ffmpeg_preset("default")
        mov = out / "sh010.mov"
        cmd = ["ffmpeg", "-v", "error", "-y", "-framerate", "30", "-i", str(frames / "f%04d.png"),
               *post._ffmpeg_preset_to_args(preset), str(mov), *post._ld_args(320, preset, mov)]
        subprocess.run(cmd, check=True)
        assert _probe(mov) == ("prores", "yuv422p10le"), _probe(mov)
        ld = post.ld_path(mov)
        assert ld.is_file() and _probe(ld)[0] == "hevc", (ld, _probe(ld) if ld.exists() else None)

        # MP4: plays as is, no light copy.
        use("mp4")
        preset = post.resolve_ffmpeg_preset("default")
        mp4 = out / "sh020.mp4"
        assert post._ld_args(320, preset, mp4) == []
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "30", "-i", str(frames / "f%04d.png"),
                        *post._ffmpeg_preset_to_args(preset), str(mp4)], check=True)
        assert _probe(mp4) == ("h264", "yuv420p"), _probe(mp4)

        # A sequence preview with Video: MOV -- an H.264 mp4 all the same.
        use("prores_lt")
        prev = out / "sq010_preview.mp4"
        cmd = post.build_concat_command([mov, mp4], prev, json.loads(cfg.read_text()), "default", "ffmpeg")
        subprocess.run(cmd[:1] + ["-v", "error"] + cmd[1:], check=True)
        assert _probe(prev) == ("h264", "yuv420p"), _probe(prev)
    print("video formats: ok")


if __name__ == "__main__":
    main()
