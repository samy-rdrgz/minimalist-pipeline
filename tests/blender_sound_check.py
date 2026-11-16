"""The renders' sound, checked in Blender: the add-on's own mixdown
(lib/sound.py) and compilation command (farm/post_render.py) on a scene
made here -- a sound strip of 1 s of silence then a tone, the render range
starting where the tone does. Needs the add-on installed and ffmpeg.

    blender -b --python tests/blender_sound_check.py

Each mixdown runs in a Blender of its own (started by this one): a
background Blender runs one mixdown job.

Prints OK / FAIL per check, and leaves its files in a temporary folder
(printed) to listen to.
"""

import importlib
import math
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import addon_utils
import bpy

RESULTS = []


def check(label, ok, detail=""):
    RESULTS.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + (f"  ({detail})" if detail else ""))


def addon():
    for m in addon_utils.modules():
        if m.__name__.split(".")[-1] == "minimalist_pipeline":
            addon_utils.enable(m.__name__, default_set=False, persistent=False)
            return m.__name__
    sys.exit("The add-on Minimalist Pipeline isn't installed in this Blender.")


def write_wav(path, seconds_silence=1.0, seconds_tone=3.0, rate=48000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n0, n1 = int(seconds_silence * rate), int(seconds_tone * rate)
        frames = b"\0\0" * n0 + b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(n1)
        )
        w.writeframes(frames)


def leading_silence(path, ffmpeg):
    """Seconds of silence at the start of a file's sound (0 if none)."""
    err = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path), "-af", "silencedetect=n=-40dB:d=0.1", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    for line in err.splitlines():
        if "silence_start: 0" in line or "silence_start: -0" in line:
            ends = [l for l in err.splitlines() if "silence_end" in l]
            return float(ends[0].split("silence_end: ")[1].split()[0]) if ends else 99.0
    return 0.0


_DIAGNOSED = []


def diagnose(scene, d):
    """The mixdown failed: what this Blender's operator takes, and which
    call works -- printed for the add-on to follow."""
    if _DIAGNOSED:
        return
    _DIAGNOSED.append(1)
    import traceback

    op = bpy.ops.sound.mixdown
    print("\n--- diagnosis ---")
    try:
        print("poll:", op.poll())
    except Exception as e:
        print("poll raised:", e)
    try:
        for prop in op.get_rna_type().properties:
            items = [i.identifier for i in getattr(prop, "enum_items", [])]
            print(f"  {prop.identifier}: {prop.type}" + (f" {items}" if items else f" = {getattr(prop, 'default', '')}"))
    except Exception as e:
        print("properties unread:", e)
    variants = [
        ("flac full", dict(container="FLAC", codec="FLAC", format="S16", channels="STEREO", mixrate=48000)),
        ("flac minimal", dict(container="FLAC", codec="FLAC")),
        ("flac S16 only", dict(container="FLAC", codec="FLAC", format="S16")),
        ("wav pcm", dict(container="WAV", codec="PCM", format="S16")),
        ("defaults", {}),
    ]
    for name, kw in variants:
        for prefix in ("", "."):
            ext = ".wav" if kw.get("container") == "WAV" else ".flac"
            out = d / f"{prefix}diag_{name.replace(' ', '_')}{ext}"
            before = set(p.name for p in d.iterdir())
            try:
                res = op(filepath=str(out), **kw)
                err = ""
            except Exception as e:
                res, err = None, "".join(traceback.format_exception_only(type(e), e)).strip()
            new_files = sorted(set(p.name for p in d.iterdir()) - before)
            print(f"  {name:14} {'hidden ' if prefix else 'visible'}: {res} {err} -> new files {new_files}")
    print("--- end of diagnosis ---\n")


ARGS = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def tone_scene(wav):
    """The scene: the tone as a sound strip on channel 1, from frame 1."""
    scene = bpy.context.scene
    editor = scene.sequence_editor or scene.sequence_editor_create()
    strips = editor.strips if hasattr(editor, "strips") else editor.sequences  # 4.4+ / before
    strips.new_sound("tone", str(wav), 1, 1)
    return scene, editor


def run_case(base, d):
    """One mixdown and its compilations, in a Blender of its own: a
    background Blender runs one mixdown job (the next waits for the end
    of the first, which only its event loop would handle) -- the farm's
    setup makes one per Blender too."""
    name = addon()
    lib = importlib.import_module(f"{name}.lib")
    sound = importlib.import_module(f"{name}.lib.sound")
    post = importlib.import_module(f"{name}.farm.post_render")
    preview = importlib.import_module(f"{name}.lib.preview")
    ffmpeg = lib.resolve_ffmpeg()
    scene, _ = tone_scene(d / "tone.wav")
    frames_dir = d / "frames"
    rate = round(24 / base, 3)
    scene.render.fps, scene.render.fps_base = 24, base
    scene.use_audio = True  # the timeline's Mute, left on: the mixdown must still have sound
    flac = d / f"sh010_{rate}.flac"
    ok = sound.mixdown(scene, flac, 25, 72)
    check(f"[{rate} fps] mixdown written", ok and flac.is_file(), str(flac) if ok else getattr(sound, "last_error", "?"))
    if not flac.is_file():
        diagnose(scene, d)
        return
    info = preview.media_info(flac, ffmpeg)
    want = 48 / rate
    check(f"[{rate} fps] its length is the range's", info and abs(info["duration"] - want) < 0.03,
          f"{info and info['duration']} s, {want:.3f} expected")
    lead = leading_silence(flac, ffmpeg)
    check(f"[{rate} fps] it starts at the range's first frame (the tone)", lead < 0.05, f"{lead:.2f} s of silence first")
    for fmt in ("mp4", "prores_lt"):
        preset = dict(post.VIDEO_FORMATS[fmt])
        video = d / f"sh010_{rate}.{preset.get('extension', 'mp4')}"
        cmd = post.compile_command(
            ffmpeg_bin=ffmpeg, frames_pattern=str(frames_dir / "f.%05d.png"), first=25, last=72,
            fps=rate, preset=preset, video=video, width=320, size=(320, 180), audio=flac,
        )
        r = subprocess.run(cmd[:1] + ["-v", "error"] + cmd[1:], capture_output=True, text=True)
        check(f"[{rate} fps] {fmt}: compiled", r.returncode == 0, r.stderr.strip()[-300:])
        info = preview.media_info(video, ffmpeg) or {}
        expected = "pcm_s16le" if fmt == "prores_lt" else "aac"
        check(f"[{rate} fps] {fmt}: its sound ({expected})", info.get("audio") == expected, str(info))
        if abs((info.get("duration") or 0) - want) > 0.05:
            check(f"[{rate} fps] {fmt}: its length", False, f"{info.get('duration')} s, {want:.3f} expected")
        if fmt == "prores_lt":
            ld = info and preview.media_info(post.ld_path(video), ffmpeg) or {}
            check(f"[{rate} fps] {fmt}: its light copy has sound (aac)", ld.get("audio") == "aac", str(ld))


def main():
    name = addon()
    lib = importlib.import_module(f"{name}.lib")
    sound = importlib.import_module(f"{name}.lib.sound")
    ffmpeg = lib.resolve_ffmpeg()
    if not ffmpeg:
        sys.exit("No ffmpeg: on the PATH, or in the add-on's Preferences, FFmpeg path.")
    print(f"Blender {bpy.app.version_string}, ffmpeg {ffmpeg}, add-on {name}")

    d = Path(tempfile.mkdtemp(prefix="mp_sound_"))
    wav = d / "tone.wav"
    write_wav(wav)
    scene, editor = tone_scene(wav)
    check("scene with a sound strip: found", sound.scene_has_sound(scene))

    # A speaker, in a scene of its own.
    other = bpy.data.scenes.new("speaker_only")
    check("scene without sound: none found", not sound.scene_has_sound(other))
    spk = bpy.data.speakers.new("spk")
    spk.sound = bpy.data.sounds.load(str(wav))
    other.collection.objects.link(bpy.data.objects.new("spk", spk))
    check("scene with a speaker: found", sound.scene_has_sound(other))

    # Its sequencer channel muted: no sound found.
    if hasattr(editor, "channels"):
        editor.channels[1].mute = True
        check("its channel muted: no sound found", not sound.scene_has_sound(scene))
        editor.channels[1].mute = False

    # No sound: no mixdown, a file left from before removed.
    old = d / "old.flac"
    old.write_bytes(b"old")
    for s in list(editor.strips_all if hasattr(editor, "strips_all") else editor.sequences_all):
        s.mute = True
    check("all strips muted: no mixdown, the old file removed", not sound.mixdown(scene, old, 25, 72) and not old.exists())

    # Frames 25..72: from 1 s (the tone's start at 24 fps) for 2 s.
    (d / "frames").mkdir()
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24",
                    "-frames:v", "48", "-start_number", "25", str(d / "frames" / "f.%05d.png")], check=True)
    for base in (1.0, 1.001):
        print(f"... mixdown at {round(24 / base, 3)} fps, in a Blender of its own")
        r = subprocess.run(
            [bpy.app.binary_path, "-b", "--python", __file__, "--", "--case", str(base), "--dir", str(d)],
            capture_output=True, text=True, errors="replace",
        )
        for line in r.stdout.splitlines():
            if line.startswith(("OK  ", "FAIL")):
                print(line)
                RESULTS.append(line.startswith("OK"))
            elif line.startswith(("---", "  ", "poll")):
                print(line)
        if not any(l.startswith(("OK  ", "FAIL")) for l in r.stdout.splitlines()):
            check(f"[{round(24 / base, 3)} fps] its Blender ran", False, (r.stderr or r.stdout).strip()[-500:])

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} OK. Files: {d}")
    sys.exit(0 if all(RESULTS) else 1)


if "--case" in ARGS:
    run_case(float(ARGS[ARGS.index("--case") + 1]), Path(ARGS[ARGS.index("--dir") + 1]))
    sys.exit(0)
main()
