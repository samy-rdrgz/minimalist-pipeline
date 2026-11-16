"""The render's sound (phase 5b): the shot file's own -- its sequencer's
sound strips, its speakers -- mixed down by the farm's render setup over
the job's range, beside the frames. The compilation puts it in the video
(farm/post_render.py), silence when there's none.

Mixed by Blender's own movie output, not bpy.ops.sound.mixdown: in a
background Blender (5.2.2) the mixdown never loads the strips' sound and
writes silence, its movie output mixes the scene as the editor plays it
(volumes, animated fades, pan, speakers). See NOTES.md, "The renders'
sound"."""

import os
import subprocess
from pathlib import Path

from .logs import log
from .preview import AUDIO_RATE


def _strips(scene) -> list:
    """Every strip of the scene's sequencer, in metas too: strips_all
    (Blender 4.4+), sequences_all before (gone in 5.0)."""
    editor = getattr(scene, "sequence_editor", None)
    if editor is None:
        return []
    for name in ("strips_all", "sequences_all"):
        strips = getattr(editor, name, None)
        if strips is not None:
            return list(strips)
    return []


def _channel_muted(scene, strip) -> bool:
    """The strip's sequencer channel muted (Blender 3.3+'s channels; channel N at index N)."""
    try:
        return bool(scene.sequence_editor.channels[strip.channel].mute)
    except (AttributeError, IndexError, TypeError):
        return False


def scene_has_sound(scene) -> bool:
    """A sound strip not muted (nor its channel), or a speaker with a sound
    and not muted. The timeline's Mute (the scene's use_audio) isn't
    looked at: mixdown() turns it off for the render."""
    for strip in _strips(scene):
        if (
            getattr(strip, "type", "") == "SOUND"
            and not getattr(strip, "mute", False)
            and getattr(strip, "sound", None)
            and not _channel_muted(scene, strip)
        ):
            return True
    for ob in getattr(scene, "objects", []):
        data = getattr(ob, "data", None)
        if getattr(ob, "type", "") == "SPEAKER" and getattr(data, "sound", None) and not getattr(data, "muted", False):
            return True
    return False


COVER = "mp_sound_cover"


def _cover(scene, start: int, end: int) -> None:
    """A colour strip over every other, start to end: the movie output
    renders it (the sequencer's) instead of the 3D scene -- a render for
    its sound only, fast. Not there (an API that won't): the scene is
    rendered small, slower."""
    editor = scene.sequence_editor or scene.sequence_editor_create()
    strips = editor.strips if hasattr(editor, "strips") else editor.sequences  # 4.4+ / before
    channel = min(128, max([getattr(s, "channel", 0) for s in _strips(scene)] or [0]) + 1)
    try:
        strips.new_effect(name=COVER, type="COLOR", channel=channel, frame_start=start, length=end - start + 1)
    except TypeError:
        strips.new_effect(name=COVER, type="COLOR", channel=channel, frame_start=start, frame_end=end + 1)


def _render_sound(scene, movie: Path, start: int, end: int) -> None:
    """The scene's sound, start to end, by Blender's movie output: an MKV
    with FLAC sound (no picture if this Blender writes none), 64 px,
    Workbench, no compositing (no File Output node written). The render
    setup never saves the file: nothing of it stays."""
    import bpy

    try:
        _cover(scene, start, end)
    except Exception as e:
        log("INFO", "farm", f"Sound render: the scene rendered small ({e})")
    r = scene.render
    r.engine = "BLENDER_WORKBENCH"
    r.resolution_x, r.resolution_y, r.resolution_percentage = 64, 64, 100
    for prop, value in (("use_compositing", False), ("use_sequencer", True),
                        ("use_multiview", False), ("use_stamp", False), ("use_file_extension", False)):
        if hasattr(r, prop):
            setattr(r, prop, value)
    imf = r.image_settings
    if hasattr(imf, "media_type"):  # 5.0+
        imf.media_type = "VIDEO"
    imf.file_format = "FFMPEG"
    ff = r.ffmpeg
    ff.format = "MKV"
    for codec in ("NONE", "MPEG4", "H264"):
        try:
            ff.codec = codec
            break
        except (TypeError, ValueError):
            continue
    ff.audio_codec, ff.audio_channels, ff.audio_mixrate = "FLAC", "STEREO", AUDIO_RATE
    r.filepath = str(movie)
    scene.frame_start, scene.frame_end = int(start), int(end)
    bpy.ops.render.render(animation=True)


# Why the last mixdown() wrote nothing ("" if it did): the log says it
# too, but only with a project active -- tests/blender_sound_check.py
# prints it.
last_error = ""


def mixdown(scene, path: Path, start: int, end: int) -> bool:
    """The scene's sound from frame start to end, to path (a .flac):
    rendered (_render_sound()), its sound taken out by ffmpeg, written
    beside then renamed -- never left half-written. Without sound, no file
    -- one left from a render before removed. True if written. Never
    raises: a render without its sound is still a render (its video gets
    silence)."""
    from .core import resolve_ffmpeg  # local: core imports this package's modules

    global last_error
    last_error = ""
    path = Path(path)
    movie = path.with_name(f".{path.stem}.tmp.mkv")
    tmp = path.with_name(f".{path.stem}.tmp.flac")
    try:
        if not scene_has_sound(scene):
            path.unlink(missing_ok=True)
            return False
        ffmpeg = resolve_ffmpeg()
        if not ffmpeg:
            raise OSError("no ffmpeg to take the sound out of the render")
        # Its sound on: the timeline's Mute mutes the render too, an
        # animator may have left it on. No preview range.
        for prop, value in (("use_preview_range", False), ("use_audio", False)):
            if hasattr(scene, prop):
                setattr(scene, prop, value)
        _render_sound(scene, movie, start, end)
        if not movie.is_file():
            raise OSError("the render wrote no file")
        done = subprocess.run(
            [ffmpeg, "-v", "error", "-y", "-i", str(movie), "-map", "0:a:0", "-c:a", "flac",
             "-sample_fmt", "s16", "-f", "flac", str(tmp)],
            capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL,
        )
        if done.returncode or not tmp.is_file():
            raise OSError(f"no sound in the render: {done.stderr.strip()[-200:]}")
        os.replace(tmp, path)
        return True
    except Exception as e:
        last_error = f"{type(e).__name__}: {e}"
        log("WARNING", "farm", f"No sound for {path.name}: {e}")
        return False
    finally:
        for leftover in (movie, tmp):
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                pass
