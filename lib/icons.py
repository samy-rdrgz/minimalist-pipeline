"""The add-on's coloured marks (icons/*.png, tools/make_icons.py) as
Blender icons: icon names "mark:<name>" next to Blender's own. See
NOTES.md, "Coloured marks"."""

from pathlib import Path

import bpy
import bpy.utils.previews

ICONS_DIR = Path(__file__).resolve().parent.parent / "icons"
PREFIX = "mark:"

_marks = None


def register_marks() -> None:
    global _marks
    if _marks is not None:
        return
    _marks = bpy.utils.previews.new()
    for path in sorted(ICONS_DIR.glob("*.png")):
        _marks.load(path.stem, str(path), "IMAGE")


def unregister_marks() -> None:
    global _marks
    if _marks is not None:
        bpy.utils.previews.remove(_marks)
        _marks = None


def icon_kw(icon: str) -> dict:
    """A layout call's icon argument: {"icon_value": ...} for a mark,
    {"icon": icon} for Blender's own -- a mark not loaded draws nothing."""
    if not icon.startswith(PREFIX):
        return {"icon": icon}
    mark = _marks.get(icon[len(PREFIX):]) if _marks is not None else None
    return {"icon_value": mark.icon_id if mark else 0}
