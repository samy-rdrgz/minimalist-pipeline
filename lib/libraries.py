"""Post-import handling: warn on append vs link, track newly linked libraries."""

from __future__ import annotations

from pathlib import Path

import bpy

from .actions import PipelineAction, set_pending_action
from .config import file_in_active_project, to_relative
from .core import resolve_bpy_path
from .logs import log
from .tracking import wipmeta_add_link, wipmeta_sync_links

APPEND_DETECTED_EXPLANATION = (
    "In a pipeline, assets are linked (a live reference) rather than "
    "copied in. That keeps a single source of truth and clean updates. "
    "You just appended a copy; re-linking is usually what you want."
)


def _blender_internal_roots() -> list[Path]:
    """Directories whose imports are Blender's own plumbing, not a deliberate
    user append/link: the copy/paste temp buffers (one file per editor --
    copybuffer.blend, copybuffer_node.blend, copybuffer_pose.blend...,
    always under bpy.app.tempdir) and Blender's bundled datafiles (the
    Essentials asset library -- brushes, matcaps... -- shipped inside the
    Blender install, resolved via resource_path('LOCAL' | 'SYSTEM'))."""
    roots = []
    if bpy.app.tempdir:
        roots.append(Path(bpy.app.tempdir))
    for kind in ("LOCAL", "SYSTEM"):
        try:
            p = bpy.utils.resource_path(kind)
        except Exception:
            p = ""
        if p:
            roots.append(Path(p))
    return roots


def _is_internal_import(filepath: str) -> bool:
    """True if filepath (a source_library.filepath) resolves under one of
    Blender's own internal roots, or is itself a copy/paste buffer file,
    rather than a real project/user file."""
    resolved = resolve_bpy_path(filepath).resolve()
    # Matched by name, not just directory -- see NOTES.md, "Copy/paste
    # isn't always under bpy.app.tempdir".
    if resolved.name.startswith("copybuffer") and resolved.suffix == ".blend":
        return True
    for root in _blender_internal_roots():
        try:
            resolved.relative_to(root.resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


# ---------------------------------------------------------------------------
# Scan of the links already in the file
# ---------------------------------------------------------------------------


def scan_linked_libraries() -> list[dict]:
    """{"file"} for every project file the open file links directly --
    one entry per file, whatever it brings (see NOTES.md, "Linked
    libraries: one line per file"). Only direct libraries (lib.parent is
    None): an indirect one comes with a linked asset and is already in
    that asset's own meta. Blender's internal files and files outside the
    project are skipped."""
    out = []
    for lib in bpy.data.libraries:
        if lib.parent is not None or _is_internal_import(lib.filepath):
            continue
        abs_path = resolve_bpy_path(lib.filepath)
        if file_in_active_project(str(abs_path)):
            out.append({"file": to_relative(abs_path)})
    return out


def sync_linked_libraries():
    """Record in the open file's .wipmeta the links it already contains but
    the pipeline never saw being made (file migrated from outside, library
    repointed by a script...). Called on load and save. Never raises:
    handler-called, same rule as check_library_update()."""
    filepath = bpy.data.filepath
    if not filepath or not file_in_active_project(filepath):
        return
    try:
        added = wipmeta_sync_links(Path(filepath), scan_linked_libraries())
        if added:
            log("INFO", "sync_links", f"{added} existing link(s) added to the wipmeta")
    except Exception as e:
        log("WARNING", "sync_links", f"Could not sync linked libraries: {e}")


def clean_append_and_relink(items: list[bpy.types.BlendImportContextItem]):
    """Delete given datablock append and re-import them as Linked library."""
    clean_append(items)
    for link in [i for i in items if not i.import_info]:
        try:
            bpy.ops.wm.link(
                filepath=f"{link.source_library.filepath}/{link.id.rna_type.name}/{link.name}",
                directory=f"{link.source_library.filepath}/{link.id.rna_type.name}/",
                filename=link.name,
                link=True,
                autoselect=True,
                active_collection=True,
            )
        except Exception:
            pass


def clean_append(items: list[bpy.types.BlendImportContextItem]):
    """Delete given datablock append."""
    try:
        bpy.data.batch_remove([item.id for item in items if item.id is not None])
    except Exception:
        pass


def import_warnings(items):
    """Prompt the user or let the user choose actions based on the type of import."""
    if not items:
        return
    # Copy/paste (any editor: 3D viewport, node editor, pose library...) and
    # dragging a built-in asset (Essentials brushes, matcaps...) both round-
    # trip through blend_import_post exactly like a real append/link, even
    # though nothing was actually appended/linked from the project. Filter
    # those out so they don't trigger the library warning popup.
    items = [i for i in items if not _is_internal_import(i.source_library.filepath)]
    if not items:
        return
    append_action = [i.append_action for i in items]
    if "MAKE_LOCAL" in append_action:  # APPEND Done
        if file_in_active_project(
            str(resolve_bpy_path(items[0].source_library.filepath))
        ):
            set_pending_action(
                PipelineAction(
                    title="Append done: link instead?",
                    message="You appended data from a project file\nconsider linking it instead.",
                    severity="warning",
                    choices=[
                        ("Ignore", None, "Keep the appended data as-is."),
                        (
                            "Clean & reLink",
                            lambda: clean_append_and_relink(items),
                            "Delete the appended data and re-import it as a link instead.",
                        ),
                    ],
                    explanation=APPEND_DETECTED_EXPLANATION,
                )
            )
            return bpy.ops.m_pipeline.action_popup("INVOKE_DEFAULT")
        else:
            set_pending_action(
                PipelineAction(
                    title="Append done: link instead?",
                    message="You appended data from a non project file\nconsider moving file in project dir and linking it instead.",
                    severity="warning",
                    choices=[
                        ("Ignore", None, "Keep the appended data as-is."),
                        (
                            "Clean",
                            lambda: clean_append(items),
                            "Delete the appended data.",
                        ),
                    ],
                    explanation=APPEND_DETECTED_EXPLANATION,
                )
            )
            return bpy.ops.m_pipeline.action_popup("INVOKE_DEFAULT")

    else:
        # One entry per file (wipmeta_add_link() dedupes): what was linked
        # from it doesn't matter to anything reading the list.
        data = [
            {"file": to_relative(resolve_bpy_path(i.source_library.filepath))}
            for i in items
            if not i.import_info
        ]
        if not file_in_active_project(
            str(resolve_bpy_path(items[0].source_library.filepath))
        ):
            set_pending_action(
                PipelineAction(
                    title="External project Link done ?",
                    message="You linked data from a non project file\nconsider moving file in project dir and relinking it.",
                    severity="warning",
                    choices=[
                        (
                            "Ignore",
                            lambda: wipmeta_add_link(Path(bpy.data.filepath), data),
                            "Keep the link as-is, outside the project folder.",
                        ),
                        (
                            "Undo Link",
                            lambda: clean_append(items),
                            "Remove the linked data.",
                        ),
                    ],
                    # Closed without choosing: the link stays, so record it
                    # like "Ignore" does.
                    on_dismiss=lambda: wipmeta_add_link(Path(bpy.data.filepath), data),
                )
            )
            return bpy.ops.m_pipeline.action_popup("INVOKE_DEFAULT")
        else:
            wipmeta_add_link(Path(bpy.data.filepath), data)
            return
