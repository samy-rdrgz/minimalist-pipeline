"""Asset collection preset: executed fresh from disk at every asset creation.
Edit freely: lives in YOUR project's config/, changes apply live, no restart.
Contract: build_collections(prefix, name) -> Collection, called right before
save; any exception falls back to a single collection, never blocks creation."""

import bpy


def build_collections(prefix: str, name: str):
    """One elif branch per prefix, add your own below the existing ones.
    prefix: as defined in project_config.json (e.g. "ch", "pr", "env", "mat").
    name: the sanitized asset name (e.g. "bob")."""
    base = f"{prefix}_{name}"
    root = bpy.data.collections.new(base)
    bpy.context.scene.collection.children.link(root)

    if prefix in ("ch", "pr"):
        # Characters and props: minimal department scaffolding inside the
        # same work file. NOT a physical file split (rig stays here for v1,
        # unlike a true separate -rig.blend), just organizational.
        for suffix in ("mdl", "rig", "proxy"):
            sub = bpy.data.collections.new(f"{base}_{suffix}")
            root.children.link(sub)

    # elif prefix == "env":
    #     ...add your own structure here...

    # Anything else (env by default, library prefixes, unknown prefixes):
    # falls through to the single root collection created above.

    return root
