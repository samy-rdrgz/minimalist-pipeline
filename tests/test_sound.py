"""The renders' sound (phase 5b): the scene's sound found and rendered
(lib/sound.py, Blender's movie output stood in for), the compilation putting it in the
video at the frames' length -- silence without one --, the light copy and
the .mov keeping it, a sequence preview keeping each shot's in its place.
The ffmpeg part runs for real when there is one.

    python3 tests/test_sound.py
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def _streams(path: Path) -> dict:
    """{codec_type: (codec, duration)} of a video."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,duration",
         "-of", "json", str(path)], capture_output=True, text=True, check=True,
    ).stdout
    return {s["codec_type"]: (s["codec_name"], float(s.get("duration") or 0)) for s in json.loads(out)["streams"]}


def _silences(path: Path) -> list[tuple[float, float]]:
    """(start, end) of each silence in a video's sound."""
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "silencedetect=n=-50dB:d=0.2", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return list(zip(starts, ends + [None] * (len(starts) - len(ends))))


def check_detection(sound) -> None:
    """scene_has_sound(): strips, their channel, speakers."""
    strip = NS(type="SOUND", mute=False, sound=object())

    def scene(strips=(), objects=(), editor=True):
        return NS(sequence_editor=NS(strips_all=list(strips)) if editor else None, objects=list(objects))

    assert not sound.scene_has_sound(scene(editor=False))
    assert not sound.scene_has_sound(scene([NS(type="SOUND", mute=True, sound=object())]))
    assert not sound.scene_has_sound(scene([NS(type="MOVIE", mute=False)]))
    assert sound.scene_has_sound(scene([strip]))
    assert sound.scene_has_sound(scene(objects=[NS(type="SPEAKER", data=NS(sound=object(), muted=False))]))
    assert not sound.scene_has_sound(scene(objects=[NS(type="SPEAKER", data=NS(sound=object(), muted=True))]))
    # Its channel muted (the sequencer's channels, channel N at index N).
    chan = NS(sequence_editor=NS(strips_all=[NS(type="SOUND", mute=False, sound=object(), channel=2)],
                                 channels=[NS(mute=False), NS(mute=False), NS(mute=True)]), objects=[])
    assert not sound.scene_has_sound(chan)
    chan.sequence_editor.channels[2].mute = False
    assert sound.scene_has_sound(chan)
    # Before Blender 4.4: sequences_all.
    assert sound.scene_has_sound(NS(sequence_editor=NS(sequences_all=[strip]), objects=[]))


def check_render(sound, core, preview, bpy) -> None:
    """mixdown(): the scene rendered by Blender's movie output (stood in
    for: ffmpeg writes the MKV a render would), its sound taken out to a
    FLAC as long as the range; a colour strip over the sequencer, the
    render's settings; nothing left beside it; no sound, no file."""
    core.resolve_ffmpeg = lambda: "ffmpeg"
    renders, covers = [], []
    state = {"scene": None, "no_track": False, "cover_api": "new"}

    def render(animation=False):
        sc = state["scene"]
        r = sc.render
        renders.append({"engine": r.engine, "use_compositing": r.use_compositing, "format": r.ffmpeg.format,
                        "codec": r.ffmpeg.codec, "audio": r.ffmpeg.audio_codec,
                        "range": (sc.frame_start, sc.frame_end), "use_audio": sc.use_audio})
        secs = (sc.frame_end - sc.frame_start + 1) / (r.fps / r.fps_base)
        if state["no_track"]:
            cmd = ["-f", "lavfi", "-i", f"testsrc=d={secs}:size=64x64"]
        else:
            cmd = ["-f", "lavfi", "-i", f"sine=f=440:d={secs}:r=48000", "-c:a", "flac"]
        subprocess.run(["ffmpeg", "-v", "error", "-y", *cmd, "-f", "matroska", r.filepath], check=True)
        return {"FINISHED"}

    bpy.ops.render.render = render

    def new_effect(**kw):
        covers.append(kw)
        if "length" in kw and state["cover_api"] == "old":
            raise TypeError("length")

    def scene(fps_base=1.0, sounds=True, mute=True):
        strips = [NS(type="SOUND", mute=False, sound=object(), channel=3)] if sounds else []
        render_settings = NS(
            fps=24, fps_base=fps_base, image_settings=NS(file_format="PNG", media_type="IMAGE"),
            ffmpeg=NS(format="MPEG4", codec="H264", audio_codec="NONE", audio_channels="MONO", audio_mixrate=44100),
            engine="CYCLES", resolution_x=1920, resolution_y=1080, resolution_percentage=100,
            use_compositing=True, use_sequencer=False, use_file_extension=True, filepath="//out/")
        sc = NS(sequence_editor=NS(strips_all=strips, strips=NS(new_effect=new_effect)), objects=[],
                frame_start=1, frame_end=250, use_preview_range=True, use_audio=mute, render=render_settings)
        state["scene"] = sc
        return sc

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        out = d / "sq010_sh010_v003_001.flac"
        # No sound: no render, no file, one left from before removed.
        out.write_bytes(b"old")
        assert sound.mixdown(scene(sounds=False), out, 1001, 1100) is False and not out.exists() and not renders
        # 23.976, the Mute left on: rendered over the range, its sound on.
        sc = scene(fps_base=1.001)
        assert sound.mixdown(sc, out, 25, 72), sound.last_error
        r = renders[-1]
        assert r["range"] == (25, 72) and r["use_audio"] is False and r["engine"] == "BLENDER_WORKBENCH", r
        assert r["format"] == "MKV" and r["codec"] == "NONE" and r["audio"] == "FLAC" and not r["use_compositing"], r
        assert sc.render.image_settings.media_type == "VIDEO" and sc.render.image_settings.file_format == "FFMPEG"
        assert covers[-1]["type"] == "COLOR" and covers[-1]["channel"] == 4 and covers[-1]["frame_start"] == 25
        assert covers[-1]["length"] == 48, covers[-1]
        info = preview.media_info(out, "ffmpeg")
        assert info["audio"] == "flac" and abs(info["duration"] - 48 / (24 / 1.001)) < 0.02, info
        assert sorted(p.name for p in d.iterdir()) == [out.name], list(d.iterdir())
        # A Blender whose new_effect takes frame_end (before 4.4 / 5.0).
        state["cover_api"] = "old"
        assert sound.mixdown(scene(), out, 1, 24) and covers[-1].get("frame_end") == 25, covers[-1]
        # A render without sound: no file, said why, nothing left.
        state["no_track"] = True
        out.unlink()
        assert not sound.mixdown(scene(), out, 1, 24) and "no sound" in sound.last_error, sound.last_error
        assert not any(d.iterdir()), list(d.iterdir())
        state["no_track"] = False
        # No ffmpeg: no sound, said why.
        core.resolve_ffmpeg = lambda: None
        assert not sound.mixdown(scene(), out, 1, 24) and "ffmpeg" in sound.last_error
        core.resolve_ffmpeg = lambda: "ffmpeg"

        # A render that fails: no sound, no exception, nothing left.
        def boom(**kw):
            raise RuntimeError("Error: render failed")

        bpy.ops.render.render = boom
        assert not sound.mixdown(scene(), out, 1, 24) and "render failed" in sound.last_error
        assert not any(d.iterdir())


def main() -> None:
    import importlib

    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    sound = importlib.import_module(f"{pkg.__name__}.lib.sound")
    check_detection(sound)
    if shutil.which("ffmpeg"):
        check_render(sound, importlib.import_module(f"{pkg.__name__}.lib.core"),
                     importlib.import_module(f"{pkg.__name__}.lib.preview"), sys.modules["bpy"])

    config = importlib.import_module(f"{pkg.__name__}.lib.config")
    post = importlib.import_module(f"{pkg.__name__}.farm.post_render")
    assert post.audio_codec_args({}, ".mov") == ["-c:a", "pcm_s16le"]
    assert post.audio_codec_args({}, "mp4")[:2] == ["-c:a", "aac"]
    assert post.audio_codec_args({"audio_args": ["-an"]}, "mp4") == ["-an"]

    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("sound: ok (no ffmpeg: not encoded)")
        return

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        root = d / "proj"
        (root / "config" / "presets" / "ffmpeg_presets").mkdir(parents=True)
        cfg = root / "config" / "project_config.json"
        config.set_daemon_active_project_root(root)

        def use(fmt):
            cfg.write_text(json.dumps({"resolution": {"x": 320, "y": 180}, "default_fps": 24, "video": {"format": fmt}}))
            config.ConfigCache.invalidate()

        def run(cmd):
            subprocess.run(cmd[:1] + ["-v", "error"] + cmd[1:], check=True, capture_output=True)

        # 30 frames at 23.976 (the fps the setup writes, rounded), from 1001.
        frames = d / "frames"
        frames.mkdir()
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24",
                        "-frames:v", "30", "-start_number", "1001", str(frames / "f.%05d.png")], check=True)
        fps, n = 23.976, 30
        length = n / fps
        flacs = {}
        for name, secs in (("short", 0.6), ("long", 3.0), ("exact", length)):
            flacs[name] = d / f"{name}.flac"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"sine=f=440:d={secs}:r=44100",
                            "-ac", "2", str(flacs[name])], check=True)

        def compile_(video, audio, fmt="mp4", width=320):
            use(fmt)
            preset = post.resolve_ffmpeg_preset("default")
            cmd = post.compile_command(
                ffmpeg_bin="ffmpeg", frames_pattern=str(frames / "f.%05d.png"), first=1001, last=1000 + n,
                fps=fps, preset=preset, video=video, width=width, size=(320, 180), audio=audio,
            )
            run(cmd)
            return _streams(video)

        out = d / "out"
        out.mkdir()
        # The sound as long as the frames, whatever the mixdown's length;
        # silence when there's none.
        for name in ("short", "long", "exact", None):
            video = out / f"sh_{name}.mp4"
            st = compile_(video, flacs.get(name) if name else out / "missing.flac")
            assert st["audio"][0] == "aac" and st["video"][0] == "h264", st
            assert abs(st["audio"][1] - length) < 0.002 and abs(st["video"][1] - length) < 0.002, (name, st)
        assert _silences(out / "sh_None.mp4"), "no sound: silence"
        assert not _silences(out / "sh_exact.mp4")
        # A preset without sound: none, and no silence input either.
        use("mp4")
        cmd = post.compile_command(ffmpeg_bin="ffmpeg", frames_pattern=str(frames / "f.%05d.png"), first=1001,
                                   last=1030, fps=fps, preset={"codec": "libx264", "audio_args": ["-an"]},
                                   video=out / "mute.mp4", audio=flacs["exact"])
        assert "lavfi" not in cmd and str(flacs["exact"]) not in cmd
        run(cmd)
        assert "audio" not in _streams(out / "mute.mp4")

        # Submitted without sound: no track, the mixdown there or not.
        cmd = post.compile_command(ffmpeg_bin="ffmpeg", frames_pattern=str(frames / "f.%05d.png"), first=1001,
                                   last=1030, fps=fps, preset=post.resolve_ffmpeg_preset("default"),
                                   video=out / "off.mp4", audio=flacs["exact"], sound=False)
        assert "lavfi" not in cmd and str(flacs["exact"]) not in cmd
        run(cmd)
        assert "audio" not in _streams(out / "off.mp4")
        # ...and its sequence preview still has one (silence there).
        prev0 = out / "off_preview.mp4"
        run(post.build_concat_command([out / "off.mp4", out / "sh_exact.mp4"], prev0,
                                      json.loads(cfg.read_text()), "default", "ffmpeg"))
        assert _streams(prev0)["audio"][0] == "aac"

        # ProRes: PCM in the .mov, AAC in its light copy, both its length.
        mov = out / "sh_pr.mov"
        st = compile_(mov, flacs["long"], "prores_lt")
        assert st["audio"][0] == "pcm_s16le" and abs(st["audio"][1] - length) < 0.002, st
        ld = post.ld_path(mov)
        st = _streams(ld)
        assert st["audio"][0] == "aac" and abs(st["audio"][1] - length) < 0.002, st

        # The snapshot's light copy of a .mov: its sound made AAC.
        lib_preview = importlib.import_module(f"{pkg.__name__}.lib.preview")
        ld.unlink()
        made = lib_preview.ensure_ld(mov, "ffmpeg")
        assert made and _streams(made)["audio"][0] == "aac", _streams(made)

        # An old render, without a sound track.
        legacy = out / "sh_legacy.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24",
                        "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(legacy)], check=True)

        # A sequence preview: sound, legacy (no track), sound. The second
        # shot's silence where its picture is, the third's sound after it.
        use("prores_lt")
        prev = out / "sq010_preview.mp4"
        run(post.build_concat_command([out / "sh_exact.mp4", legacy, out / "sh_exact.mp4"], prev,
                                      json.loads(cfg.read_text()), "default", "ffmpeg"))
        st = _streams(prev)
        total = 2 * length + 1.0
        assert st["video"][0] == "h264" and st["audio"][0] == "aac", st
        assert abs(st["video"][1] - total) < 0.06 and abs(st["audio"][1] - total) < 0.06, (st, total)
        gaps = _silences(prev)
        assert len(gaps) == 1, gaps
        start, end = gaps[0]
        assert abs(start - length) < 0.05 and abs(end - (length + 1.0)) < 0.05, (gaps, length)

        # Its silence for the last shot too: the sound as long as the picture.
        prev2 = out / "sq010_preview2.mp4"
        run(post.build_concat_command([out / "sh_exact.mp4", legacy], prev2,
                                      json.loads(cfg.read_text()), "default", "ffmpeg"))
        st = _streams(prev2)
        assert abs(st["audio"][1] - (length + 1.0)) < 0.06, st
    print("sound: ok")


if __name__ == "__main__":
    main()
