"""Shot collection preset: executed fresh from disk at every shot creation.
Edit freely: lives in YOUR project's config/presets/creation/, changes apply
live, no restart.
Contract: build_collections(sequence, shots) -> Collection, the one the
shots' cameras go in. The addon makes the cameras and their timeline
markers itself (the shots' split reads them); this script only lays out
the collections. It may run again on the same file (a shot added to a
block): reuse what's there instead of making it twice. Any exception, or
no collection returned, falls back to CAM / SET / ASSETS, never blocks
creation."""

import bpy


def _collection(name: str, parent=None):
    """name under parent (the scene's collection by default): reused when
    there, made when not."""
    parent = parent or bpy.context.scene.collection
    col = parent.children.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        parent.children.link(col)
    return col


def build_collections(sequence: str, shots: list):
    """sequence: the sequence's label (e.g. "sq010").
    shots: the shot numbers this file holds (e.g. [10], or [10, 20, 30]
    for a block)."""
    cam = _collection("CAM")
    _collection("SET")
    _collection("ASSETS")

    # Your own structure here, e.g. a collection for the FX:
    # _collection("FX")
    # or the set split by kind:
    # set_col = _collection("SET")
    # for sub in ("SET_props", "SET_env"):
    #     _collection(sub, set_col)

    return cam
