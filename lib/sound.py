"""The render's sound (phase 5b): the shot file's own -- its sequencer's
sound strips, its speakers -- mixed down by the farm's render setup over
the job's range, beside the frames. The compilation puts it in the video
(farm/post_render.py), silence when there's none."""

import os
import time
from pathlib import Path

from .logs import log
from .preview import AUDIO_RATE, media_info


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


def _mixdown(path: str) -> None:
    """bpy.ops.sound.mixdown to a FLAC, 16 bits stereo at AUDIO_RATE; with
    only the format named if this Blender takes none of the rest."""
    import bpy

    try:
        bpy.ops.sound.mixdown(
            filepath=path, check_existing=False, relative_path=False,
            container="FLAC", codec="FLAC", format="S16", channels="STEREO", mixrate=AUDIO_RATE,
        )
    except TypeError:
        bpy.ops.sound.mixdown(filepath=path, container="FLAC", codec="FLAC")


def _evaluate(scene, frame: int) -> None:
    """The scene evaluated before the mixdown, which reads the evaluated
    one: a background Blender has no event loop to do it -- the Mute just
    turned off (applied at evaluation), the strips' sound handles, stayed
    as they were: the mixdown came out silent (Blender 5.2.2, -b)."""
    import bpy

    try:
        scene.frame_set(frame)
    except Exception:
        pass
    try:
        scene.view_layers[0].depsgraph.update()
    except Exception:
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass


# How long a mixdown may take to be written whole, at most.
MIXDOWN_TIMEOUT = 300.0


def _wait_written(path: Path, seconds: float, timeout: float | None = None) -> bool:
    """Wait for the mixdown at path to be written whole: Blender (5.x at
    least) runs bpy.ops.sound.mixdown as a background job -- it returns
    FINISHED at once, the file comes after, from another thread, and a
    background Blender quitting at the end of its script would cut it
    short. Whole: ffmpeg reads it as long as the range (a FLAC says its
    length once closed), its size still for a moment; without ffmpeg, its
    size still for longer. False if it isn't by timeout."""
    from .core import resolve_ffmpeg  # local: core imports this package's modules

    timeout = MIXDOWN_TIMEOUT if timeout is None else timeout
    ffmpeg = resolve_ffmpeg()
    still_for = 0.5 if ffmpeg else 3.0
    deadline = time.monotonic() + timeout
    last, since = None, time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(0.25)
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size != last:
            last, since = size, time.monotonic()
            continue
        if not size or time.monotonic() - since < still_for:
            continue
        if not ffmpeg:
            return True
        info = media_info(path, ffmpeg, timeout=30) or {}
        if info.get("audio") and info.get("duration") and abs(info["duration"] - seconds) < 0.1:
            return True
    return False


# Why the last mixdown() wrote nothing ("" if it did): the log says it
# too, but only with a project active -- tests/blender_sound_check.py
# prints it.
last_error = ""


def mixdown(scene, path: Path, start: int, end: int) -> bool:
    """The scene's sound from frame start to end, to path (a .flac):
    written beside then renamed, never left half-written. Without sound,
    no file -- one left from a render before removed. True if written.
    Never raises: a render without its sound is still a render (its video
    gets silence)."""
    global last_error
    last_error = ""
    path = Path(path)
    try:
        if not scene_has_sound(scene):
            path.unlink(missing_ok=True)
            return False
        # The render setup never saves the file: its range, its sound on
        # (the timeline's Mute mutes the mixdown too, an animator may have
        # left it on), no preview range.
        scene.frame_start, scene.frame_end = int(start), int(end)
        for prop, value in (("use_preview_range", False), ("use_audio", False)):
            if hasattr(scene, prop):
                setattr(scene, prop, value)
        _evaluate(scene, int(start))
        tmp = path.with_name(f".{path.stem}.tmp.flac")
        tmp.unlink(missing_ok=True)
        fps = scene.render.fps / (scene.render.fps_base or 1.0)
        _mixdown(str(tmp))
        if not _wait_written(tmp, (int(end) - int(start) + 1) / fps):
            raise OSError("the mixdown wrote no whole file in time" if tmp.exists() else "the mixdown wrote no file")
        # Windows: the writer may still hold it a moment after its last byte.
        for _ in range(40):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                time.sleep(0.25)
        else:
            os.replace(tmp, path)
        return True
    except Exception as e:
        last_error = f"{type(e).__name__}: {e}"
        log("WARNING", "farm", f"No sound for {path.name}: {e}")
        try:
            path.with_name(f".{path.stem}.tmp.flac").unlink(missing_ok=True)
        except OSError:
            pass
        return False
