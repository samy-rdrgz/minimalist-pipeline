"""The renders' sound (phase 5b): the scene's sound found and mixed down
(lib/sound.py, Blender stood in for), the compilation putting it in the
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


def check_mixdown(sound, bpy) -> None:
    calls = []

    def fake_mixdown(**kw):
        calls.append(kw)
        Path(kw["filepath"]).write_bytes(b"fLaC")

    bpy.ops.sound.mixdown = fake_mixdown

    def scene(strips=(), objects=(), editor=True):
        ed = NS(strips_all=list(strips)) if editor else None
        return NS(sequence_editor=ed, objects=list(objects), frame_start=1, frame_end=250,
                  use_preview_range=True, use_audio=True)

    strip = NS(type="SOUND", mute=False, sound=object())
    speaker = NS(type="SPEAKER", data=NS(sound=object(), muted=False))
    assert not sound.scene_has_sound(scene(editor=False))
    assert not sound.scene_has_sound(scene([NS(type="SOUND", mute=True, sound=object())]))
    assert not sound.scene_has_sound(scene([NS(type="MOVIE", mute=False)]))
    assert sound.scene_has_sound(scene([strip]))
    assert sound.scene_has_sound(scene(objects=[speaker]))
    assert not sound.scene_has_sound(scene(objects=[NS(type="SPEAKER", data=NS(sound=object(), muted=True))]))
    # Its channel muted (the sequencer's channels): no sound either.
    chan = NS(sequence_editor=NS(strips_all=[NS(type="SOUND", mute=False, sound=object(), channel=2)],
                                 channels=[NS(mute=False), NS(mute=False), NS(mute=True)]), objects=[])
    assert not sound.scene_has_sound(chan)
    chan.sequence_editor.channels[2].mute = False
    assert sound.scene_has_sound(chan)
    # Before Blender 4.4: sequences_all.
    assert sound.scene_has_sound(NS(sequence_editor=NS(sequences_all=[strip]), objects=[]))

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "sq010_sh010_v003_001.flac"
        # No sound: no file, one left from before removed.
        out.write_bytes(b"old")
        assert sound.mixdown(scene(), out, 1001, 1100) is False and not out.exists() and not calls
        # Sound: the shot's range, its sound on, written beside then renamed.
        sc = scene([strip])
        assert sound.mixdown(sc, out, 1001, 1100) is True and out.read_bytes() == b"fLaC"
        assert (sc.frame_start, sc.frame_end, sc.use_preview_range, sc.use_audio) == (1001, 1100, False, False)
        assert calls[-1]["container"] == "FLAC" and calls[-1]["mixrate"] == 48000
        assert Path(calls[-1]["filepath"]).name.startswith(".") and Path(calls[-1]["filepath"]).parent == out.parent
        # A Blender that takes fewer options: the format alone.
        def picky(filepath, container, codec):
            calls.append({"filepath": filepath})
            Path(filepath).write_bytes(b"fLaC2")

        def strict(**kw):
            if "mixrate" in kw:
                raise TypeError("unexpected keyword")
            picky(**kw)

        bpy.ops.sound.mixdown = strict
        assert sound.mixdown(scene([strip]), out, 1, 10) and out.read_bytes() == b"fLaC2"
        # A mixdown that fails: no sound, no leftover, no exception.
        def boom(**kw):
            Path(kw["filepath"]).write_bytes(b"half")
            raise RuntimeError("Error: no audio device")

        bpy.ops.sound.mixdown = boom
        out.unlink()
        assert sound.mixdown(scene([strip]), out, 1, 10) is False
        assert not any(Path(d).iterdir()), list(Path(d).iterdir())


def main() -> None:
    import importlib

    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    check_mixdown(importlib.import_module(f"{pkg.__name__}.lib.sound"), sys.modules["bpy"])

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
