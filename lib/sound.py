"""The render's sound (phase 5b): the shot file's own -- its sequencer's
sound strips, its speakers -- mixed down by the farm's render setup over
the job's range, beside the frames. The compilation puts it in the video
(farm/post_render.py), silence when there's none."""

import os
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


def scene_has_sound(scene) -> bool:
    """A sound strip not muted, or a speaker with a sound and not muted."""
    for strip in _strips(scene):
        if getattr(strip, "type", "") == "SOUND" and not getattr(strip, "mute", False) and getattr(strip, "sound", None):
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


def mixdown(scene, path: Path, start: int, end: int) -> bool:
    """The scene's sound from frame start to end, to path (a .flac):
    written beside then renamed, never left half-written. Without sound,
    no file -- one left from a render before removed. True if written.
    Never raises: a render without its sound is still a render (its video
    gets silence)."""
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
        tmp = path.with_name(f".{path.stem}.tmp.flac")
        _mixdown(str(tmp))
        if not tmp.is_file():
            raise OSError("the mixdown wrote no file")
        os.replace(tmp, path)
        return True
    except Exception as e:
        log("WARNING", "farm", f"No sound for {path.name}: {e}")
        try:
            path.with_name(f".{path.stem}.tmp.flac").unlink(missing_ok=True)
        except OSError:
            pass
        return False
