"""Dynamic enum callbacks: file-browser cascade dropdowns (prefix/folder,
sequence/shot, version), and department pickers shared by the create/edit
dialogs (asset, shot, file, tracking entry)."""

from pathlib import Path

import bpy

from .config import (
    ConfigCache,
    get_active_project_root,
    parse_filename,
    shots_in_segment,
)
from .core import cached_scandir, json_get, monitoring_detail
from .logs import log
from .tracking import TrackingStatusCache, list_active_blocks


def get_folder(self, context) -> Path | None:
    """Return the target folder based on current operator state, or None."""
    try:
        project_root = get_active_project_root()
        if self.file_type == "asset":
            if not self.asset_folder or self.asset_folder == "NONE":
                return None
            return Path(self.asset_folder)
        else:
            if not self.sequence or self.sequence == "NONE":
                return None
            if not self.shot or self.shot == "NONE":
                return None
            if self.sequence == "all":
                return (
                    project_root
                    / "shots"
                    / self.shot.split("_", 1)[0]
                    / self.shot.split("_", 1)[1]
                )
            else:
                return project_root / "shots" / self.sequence / self.shot
    except Exception:
        return None


def resolve_version_file(
    folder: Path | None, version_mode: str, custom_version: str = ""
) -> Path | None:
    """The .blend in folder matching version_mode ("last" | "stable" |
    "custom"), or None. Shared by the Open file and Render dialogs, whose
    draw() calls it on every redraw to preview the pick: lists the folder
    through cached_scandir() -- no exists(), no iterdir(), nothing on disk
    within its TTL -- instead of one full listing per redraw."""
    if not folder:
        return None
    candidates = []
    for entry in cached_scandir(Path(folder)):
        if not entry.name.endswith(".blend"):
            continue
        parsed = parse_filename(entry.name)
        if parsed:
            candidates.append(
                (Path(entry.path), int(parsed["number"]), parsed.get("tag"))
            )
    if not candidates:
        return None
    if version_mode == "last":
        return max(candidates, key=lambda x: x[1])[0]
    if version_mode == "stable":
        stable = [c for c in candidates if c[2] == "stable"]
        return max(stable, key=lambda x: x[1])[0] if stable else None
    if version_mode == "custom" and custom_version and custom_version != "NONE":
        # Picked from version_items(), i.e. from this same listing.
        target = Path(custom_version)
        return target if any(c[0] == target for c in candidates) else None
    return None


# ---------------------------------------------------------------------------
# Dynamic enum callbacks
# ---------------------------------------------------------------------------

# NOTE: EnumProperty callbacks must keep returned strings alive across calls
# (Blender docs) or the active selection can get corrupted - worse with
# `expand=True`, which re-invokes the callback every redraw.
_prefix_items_cache: list = []
_asset_folder_items_cache: list = []
_sequence_items_cache: list = []
_shot_items_cache: list = []
_version_items_cache: list = []
_dir_version_items_cache: list = []


def _stable_items(cache: list, items: list) -> list:
    """Return `items`, or the previously cached equal list if unchanged."""
    if cache and cache[0] == items:
        return cache[1]
    cache[:] = [items, items]
    return items


def prefix_items(self, context) -> list[tuple]:
    """Asset and library prefixes from project config."""
    try:
        config = ConfigCache.get()
        structure = config.get("structure", {})
        prefixes = structure.get("asset_prefixes", []) + structure.get(
            "library_prefixes", []
        )
        items = [("all", "All", "")] + [(p, p, "") for p in prefixes]
        return _stable_items(_prefix_items_cache, items or [("NONE", "—", "")])
    except Exception:
        return [("NONE", "—", "")]


def asset_folder_items(self, context) -> list[tuple]:
    """Asset folders filtered by the selected prefix."""
    try:
        project_root = get_active_project_root()
        config = ConfigCache.get()
        structure = config.get("structure", {})

        prefix = self.asset_prefix
        if not prefix or prefix == "NONE":
            return [("NONE", "Select a prefix first", "")]

        if prefix == "all":
            # Return all asset folders under assets/{prefix}/ and library/{prefix}/
            items = []
            for parent in ["assets", "library"]:
                for p in structure.get("asset_prefixes", []) + structure.get(
                    "library_prefixes", []
                ):
                    prefix_path = project_root / parent / p
                    items += sorted(
                        (
                            (d.path, d.name, "")
                            for d in cached_scandir(prefix_path)
                            if d.is_dir() and d.name.startswith(f"{p}_")
                        ),
                        key=lambda t: t[1],
                    )
        else:
            if prefix in structure.get("asset_prefixes", []):
                parent = project_root / "assets" / prefix
            elif prefix in structure.get("library_prefixes", []):
                parent = project_root / "library" / prefix
            else:
                return [("NONE", "Unknown prefix", "")]

            items = sorted(
                (
                    (d.path, d.name, "")
                    for d in cached_scandir(parent)
                    if d.is_dir() and d.name.startswith(f"{prefix}_")
                ),
                key=lambda t: t[1],
            )

        return _stable_items(
            _asset_folder_items_cache,
            items or [("NONE", f"No {prefix}_* folder found", "")],
        )
    except Exception:
        return [("NONE", "—", "")]


def sequence_items(self, context) -> list[tuple]:
    """Sequence folders under shots/."""
    try:
        project_root = get_active_project_root()
        shots_dir = project_root / "shots"
        items = [("all", "All", "")] + sorted(
            ((d.name, d.name, "") for d in cached_scandir(shots_dir) if d.is_dir()),
            key=lambda t: t[1],
        )
        return _stable_items(
            _sequence_items_cache, items or [("NONE", "No sequences", "")]
        )
    except Exception:
        return [("NONE", "—", "")]


def shot_items(self, context) -> list[tuple]:
    """Shot folders under shots/{sequence}/, archived blocks excluded."""
    try:
        project_root = get_active_project_root()
        if not self.sequence or self.sequence == "NONE":
            return [("NONE", "Select a sequence first", "")]
        if self.sequence == "all":
            items = [
                (
                    f"{sh_dir.parent.name}_{sh_dir.name}",
                    f"{sh_dir.parent.name} {sh_dir.name}",
                    "",
                )
                for sh_dir in list_active_blocks(project_root)
            ]
        else:
            items = [
                (d.name, d.name, "")
                for d in list_active_blocks(project_root, self.sequence)
            ]
        return _stable_items(_shot_items_cache, items or [("NONE", "No shots", "")])
    except Exception:
        return [("NONE", "—", "")]


def version_items(self, context):
    """All versioned blend files in the selected folder, newest first."""
    try:
        folder = get_folder(self, context)
        if not folder:  # missing folder: cached_scandir() returns [] below
            return [("NONE", "—", "")]

        candidates = []
        for f in cached_scandir(folder):
            if not f.name.endswith(".blend"):
                continue
            parsed = parse_filename(f.name)
            if not parsed:
                continue
            v = int(parsed["number"])
            tag = parsed.get("tag") or ""
            label = f"v{v:03d}" + (f"  [{tag}]" if tag else "")
            candidates.append((f.path, label, f.name, v))

        candidates.sort(key=lambda x: x[3], reverse=True)
        items = [(val, lbl, desc) for val, lbl, desc, _ in candidates]
        return _stable_items(
            _version_items_cache, items or [("NONE", "No versions found", "")]
        )
    except Exception:
        return [("NONE", "—", "")]


# ---------------------------------------------------------------------------
# Department item callbacks
# ---------------------------------------------------------------------------

_assets_deps_items_cache: list = []
_shots_deps_items_cache: list = []
_files_deps_items_cache: list = []


def _department_items(deps: list[str]) -> list[tuple]:
    """Build enum items (id, label, "", 2**i) from a department name list.
    The bitflag value lets callers store a selection as an ENUM_FLAG set."""
    return [(d.lower(), str(d.capitalize()), "", 2**i) for i, d in enumerate(deps)]


def asset_department_items(self, context):
    """Enum items from config's assets_departments, cached until the list changes."""
    global _assets_deps_items_cache
    try:
        deps = ConfigCache.get().get(
            "assets_departments", ["modeling", "rigging", "texturing"]
        )
        if _assets_deps_items_cache and deps == _assets_deps_items_cache[0]:
            return _assets_deps_items_cache[1]
        items = _department_items(deps)
        _assets_deps_items_cache = [deps, items]
        return items
    except Exception as e:
        log("WARNING", "asset_creation", f"Could not list departments : {e}")
        return [("NONE", "—", "")]


def shot_department_items(self, context):
    """Enum items from config's shots_departments, cached until the list changes."""
    global _shots_deps_items_cache
    try:
        deps = ConfigCache.get().get(
            "shots_departments", ["layout", "animation", "lighting", "render"]
        )
        if _shots_deps_items_cache and deps == _shots_deps_items_cache[0]:
            return _shots_deps_items_cache[1]
        items = _department_items(deps)
        _shots_deps_items_cache = [deps, items]
        return items
    except Exception as e:
        log("WARNING", "asset_creation", f"Could not list departments : {e}")
        return [("NONE", "—", "")]


def file_department_items(self, context):
    """Enum items from the current file's required departments, cached until they change."""
    global _files_deps_items_cache
    try:
        # TrackingStatusCache, not get_departments_required(): that one reads
        # tracking.json from disk on every call, and this enum is evaluated
        # on every redraw of the increment-version dialog.
        deps = (
            TrackingStatusCache.get(bpy.data.filepath).get("departments_required") or []
        )
        if _files_deps_items_cache and deps == _files_deps_items_cache[0]:
            return _files_deps_items_cache[1]
        items = _department_items(deps)
        _files_deps_items_cache = [deps, items]
        return items
    except Exception as e:
        log("WARNING", "file_creation", f"Could not list departments : {e}")
        return [("NONE", "—", "")]


def tracked_department_items(self, context):
    """Enum items from the target file's tracked departments (pre-built by
    TrackingStatusCache, already bitflag-encoded), plus a blank "" option.
    filepath fallback order -- see NOTES.md, "Department filter"."""
    filepath = (
        getattr(self, "filepath", "") or monitoring_detail("file") or bpy.data.filepath
    )
    items = TrackingStatusCache.get(filepath).get("departments_items", [])
    return [("NONE", "—", "No department")] + list(items)


_department_filter_items_cache: list = []


def department_filter_items(self, context):
    """Same source as tracked_department_items, but the blank sentinel reads
    as "no filter" (this is for the notes/tasks department filter, not for
    tagging an entry's own department)."""
    items = [("NONE", "All departments", "Show every department")] + list(
        tracked_department_items(self, context)[1:]
    )
    return _stable_items(_department_filter_items_cache, items)


def dir_version_items(self, context):
    """Same as version_items, but reads the folder from self.filepath directly (no cascade)."""
    try:
        folder = Path(self.filepath)
        if not folder:  # missing folder: cached_scandir() returns [] below
            return [("NONE", "—", "")]

        candidates = []
        for f in cached_scandir(folder):
            if not f.name.endswith(".blend"):
                continue
            parsed = parse_filename(f.name)
            if not parsed:
                continue
            v = int(parsed["number"])
            tag = parsed.get("tag") or ""
            label = f"v{v:03d}" + (f"  [{tag}]" if tag else "")
            candidates.append((f.path, label, f.name, v))

        candidates.sort(key=lambda x: x[3], reverse=True)
        items = [(val, lbl, desc) for val, lbl, desc, _ in candidates]
        return _stable_items(
            _dir_version_items_cache, items or [("NONE", "No versions found", "")]
        )
    except Exception:
        return [("NONE", "—", "")]


_entry_version_items_cache: list = []


def entry_version_items(self, context):
    """Same as dir_version_items, but self.filepath may be the folder or a
    specific .blend file inside it (M_PIPELINE_OT_create_entry.filepath follows
    the same convention as create_entry() itself: falls back to bpy.data.filepath)."""
    try:
        target = Path(self.filepath) if self.filepath else Path(bpy.data.filepath)
        # From the name, not is_file() (a disk call per redraw).
        folder = target.parent if target.suffix.lower() == ".blend" else target
        if not folder:  # missing folder: cached_scandir() returns [] below
            return [("NONE", "—", "")]

        candidates = []
        for f in cached_scandir(folder):
            if not f.name.endswith(".blend"):
                continue
            parsed = parse_filename(f.name)
            if not parsed:
                continue
            v = int(parsed["number"])
            tag = parsed.get("tag") or ""
            label = f"v{v:03d}" + (f"  [{tag}]" if tag else "")
            candidates.append((f.path, label, f.name, v))

        candidates.sort(key=lambda x: x[3], reverse=True)
        items = [(val, lbl, desc) for val, lbl, desc, _ in candidates]
        return _stable_items(
            _entry_version_items_cache, items or [("NONE", "No versions found", "")]
        )
    except Exception:
        return [("NONE", "—", "")]


_shot_tag_items_cache: list = []


def shot_tag_items(self, context):
    """Enum items from the target file's own shot segment (a block covering
    shots 010-020-030 offers exactly those three, zero-padded), plus a
    blank "not shot-specific" option -- self.filepath follows the same
    convention as entry_version_items(). Any file that isn't a shot (an
    asset, or self.filepath unset) just collapses to the blank option."""
    try:
        target = Path(self.filepath) if self.filepath else Path(bpy.data.filepath)
        # Folder vs file from the name, not is_dir(); listing through
        # cached_scandir(), not glob() -- this enum is re-evaluated many
        # times per redraw of the entry dialogs and the file details popup.
        if target.suffix.lower() != ".blend":
            # Folder path (e.g. from the tracking monitor's file details
            # popup, see draw_file_details()) -- target.name is then just
            # the bare folder name ("sh010-020-030"), which parse_filename
            # never matches (no sequence/version parts). Read the shot
            # segment off one of its versioned files instead, same fix as
            # entry_version_items()'s folder-vs-file handling.
            target = next(
                (
                    Path(e.path)
                    for e in cached_scandir(target)
                    if e.name.endswith(".blend")
                ),
                target,
            )
        parsed = parse_filename(target.name) if target.name else None
        shot_segment = parsed.get("shot") if parsed else None
        if not shot_segment:
            return [("NONE", "—", "Not tied to a specific shot")]

        digits = json_get(ConfigCache.get(), "naming.shot.digits", 3)
        items = [("NONE", "—", "Not tied to a specific shot")]
        for n in shots_in_segment(shot_segment):
            padded = f"{n:0{digits}d}"
            items.append((padded, padded, ""))
        return _stable_items(_shot_tag_items_cache, items)
    except Exception:
        return [("NONE", "—", "")]
