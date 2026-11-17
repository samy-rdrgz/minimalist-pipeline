"""Why a background Blender's mixdown comes out silent: the same tone
mixed down five ways, each in a Blender of its own, each said loud or
silent. Needs ffmpeg (the add-on's, else the PATH's).

    blender -b --python tests/blender_sound_probe.py
"""

import math
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import traceback
import wave
from pathlib import Path

import bpy

ARGS = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
START, END = 25, 72  # 1 s to 3 s at 24 fps: the tone


def ffmpeg_bin():
    try:
        import addon_utils
        import importlib

        for m in addon_utils.modules():
            if m.__name__.split(".")[-1] == "minimalist_pipeline":
                addon_utils.enable(m.__name__, default_set=False, persistent=False)
                found = importlib.import_module(f"{m.__name__}.lib").resolve_ffmpeg()
                if found:
                    return found
    except Exception:
        pass
    return shutil.which("ffmpeg")


def loudness(path, ffmpeg):
    """max_volume of a file's sound in dB ("" if unread), and its duration."""
    err = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True, errors="replace").stderr
    vol = next((l.split("max_volume:")[1].strip() for l in err.splitlines() if "max_volume:" in l), "")
    dur = next((l.split("Duration:")[1].split(",")[0].strip() for l in err.splitlines() if "Duration:" in l), "")
    return vol, dur


def write_wav(path, rate=48000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * rate + b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(3 * rate)))


def setup_scene(wav):
    scene = bpy.context.scene
    editor = scene.sequence_editor or scene.sequence_editor_create()
    strips = editor.strips if hasattr(editor, "strips") else editor.sequences
    strips.new_sound("tone", str(wav), 1, 1)
    scene.render.fps, scene.render.fps_base = 24, 1.0
    scene.frame_start, scene.frame_end = START, END
    scene.use_audio = False
    return scene


def wait_file(path, timeout=60):
    last, since, t0 = None, time.monotonic(), time.monotonic()
    while time.monotonic() - t0 < timeout:
        time.sleep(0.25)
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size != last:
            last, since = size, time.monotonic()
        elif size and time.monotonic() - since > 1.5:
            return True
    return path.exists()


def mixdown(path):
    bpy.ops.sound.mixdown(filepath=str(path), check_existing=False, relative_path=False,
                          container="FLAC", codec="FLAC", format="S16", channels="STEREO", mixrate=48000)
    return wait_file(path)


def strip_of(scene):
    ed = scene.sequence_editor
    return next(iter(ed.strips_all if hasattr(ed, "strips_all") else ed.sequences_all))


def probe(kind, d):
    """One way, in this Blender; prints 'RESULT <kind> <file>' or 'ERROR'."""
    out = d / f"{kind}.flac"
    if kind == "inscript":
        setup_scene(d / "tone.wav")
        mixdown(out)
    else:
        scene = bpy.context.scene
        st = strip_of(scene)
        snd = st.sound
        print(f"INFO {kind}: strip frames {st.frame_final_start}-{st.frame_final_end}, "
              f"sound.factory {'None' if getattr(snd, 'factory', None) is None else 'loaded'}")
        if kind == "fromfile":
            mixdown(out)
        elif kind == "evaluated":
            scene.frame_set(START)
            bpy.context.evaluated_depsgraph_get().update()
            for s in bpy.data.sounds:
                try:
                    s.reload() if hasattr(s, "reload") else None
                except Exception as e:
                    print(f"INFO reload: {e}")
            bpy.context.evaluated_depsgraph_get().update()
            print(f"INFO {kind}: after evaluation, sound.factory "
                  f"{'None' if getattr(snd, 'factory', None) is None else 'loaded'}")
            mixdown(out)
        elif kind == "movie":
            out = d / "movie.mp4"
            r = scene.render
            r.engine = "BLENDER_WORKBENCH"
            r.resolution_x, r.resolution_y, r.resolution_percentage = 64, 64, 100
            imf = r.image_settings
            if hasattr(imf, "media_type"):
                imf.media_type = "VIDEO"
            imf.file_format = "FFMPEG"
            r.ffmpeg.format, r.ffmpeg.codec = "MPEG4", "H264"
            r.ffmpeg.audio_codec, r.ffmpeg.audio_channels, r.ffmpeg.audio_mixrate = "AAC", "STEREO", 48000
            r.use_file_extension = False
            r.filepath = str(out)
            bpy.ops.render.render(animation=True)
        elif kind == "aud":
            import aud

            fps = scene.render.fps / scene.render.fps_base
            # The strip's sound from the range's start, as the scene plays it.
            begin = (st.frame_start - 1) / fps  # where its content starts, from frame 1
            skip = max(0.0, (START - st.frame_start) / fps)
            length = (END - START + 1) / fps
            src = aud.Sound(bpy.path.abspath(st.sound.filepath)) if not hasattr(aud.Sound, "file") else aud.Sound.file(bpy.path.abspath(st.sound.filepath))
            snd2 = src.limit(skip, skip + length).volume(st.volume)
            snd2.write(str(out), 48000, aud.CHANNELS_STEREO, aud.FORMAT_S16, aud.CONTAINER_FLAC, aud.CODEC_FLAC)
            print(f"INFO aud: begin {begin:.3f} skip {skip:.3f} length {length:.3f}")
    print(f"RESULT {kind} {out}")


def main():
    ffmpeg = ffmpeg_bin()
    if not ffmpeg:
        sys.exit("No ffmpeg found.")
    print(f"Blender {bpy.app.version_string}, ffmpeg {ffmpeg}")
    d = Path(tempfile.mkdtemp(prefix="mp_probe_"))
    write_wav(d / "tone.wav")
    setup_scene(d / "tone.wav")
    blend = d / "shot.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), copy=True)
    for kind in ("inscript", "fromfile", "evaluated", "movie", "aud"):
        cmd = [bpy.app.binary_path, "-b"] + ([] if kind == "inscript" else [str(blend)])
        cmd += ["--python", __file__, "--", "--probe", kind, "--dir", str(d)]
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        lines = r.stdout.splitlines()
        for l in lines:
            if l.startswith(("INFO", "ERROR")):
                print("   ", l)
        res = next((l.split(" ", 2)[2] for l in lines if l.startswith("RESULT")), None)
        if not res:
            print(f"{kind:10} no result  {(r.stderr or r.stdout).strip()[-600:]}")
            continue
        vol, dur = loudness(res, ffmpeg) if Path(res).exists() else ("", "")
        loud = vol and float(vol.split()[0]) > -30
        print(f"{kind:10} {'LOUD  ' if loud else 'SILENT'} max {vol or '?'}  duration {dur or 'no file'}")
    print(f"Files: {d}")


if "--probe" in ARGS:
    try:
        probe(ARGS[ARGS.index("--probe") + 1], Path(ARGS[ARGS.index("--dir") + 1]))
    except Exception:
        print("ERROR " + traceback.format_exc().replace("\n", " | "))
    sys.exit(0)
main()
