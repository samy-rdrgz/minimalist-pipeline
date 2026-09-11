"""Base types: core utilities."""

from __future__ import annotations

import json
import os
import random
import shutil
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import bpy

from .errors import PipelineError
from .logs import log


def get_addon_version() -> str:
    """This addon's version as "X.Y.Z", read via addon_utils (same source as
    Preferences > Add-ons, no second hardcoded copy). Stamped into
    project_config.json on create/edit to track which version wrote it.
    Falls back to "0.0.0" rather than raising -- metadata, never worth blocking on."""
    import addon_utils

    addon_name = __package__.split(".")[
        0
    ]  # "minimalist_pipeline.lib" → "minimalist_pipeline"
    try:
        for mod in addon_utils.modules():
            if mod.__name__ == addon_name:
                version = mod.bl_info.get("version", (0, 0, 0))
                return ".".join(str(x) for x in version)
    except Exception:
        pass
    return "0.0.0"


def addon_pref(context: bpy.types.Context | None = None):
    """Return addon preferences."""
    try:
        ctx = context or bpy.context
        pkg = __package__.rsplit(".", 1)[
            0
        ]  # "minimalist_pipeline.lib" → "minimalist_pipeline"
        return ctx.preferences.addons[pkg].preferences
    except Exception:
        return None


# Last-resort fallback for resolve_ffmpeg() -- see NOTES.md, "FFmpeg detection".
_COMMON_FFMPEG_PATHS = {
    "linux": ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/snap/bin/ffmpeg"],
    "darwin": [
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/opt/local/bin/ffmpeg",
    ],
    "win32": [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    ],
}


def resolve_ffmpeg() -> str | None:
    """Absolute ffmpeg binary, or None. prefs.ffmpeg_path if set (no PATH
    fallback if it's invalid), else shutil.which(), then
    _COMMON_FFMPEG_PATHS -- see NOTES.md, "FFmpeg detection"."""
    prefs = addon_pref()
    override = getattr(prefs, "ffmpeg_path", "") if prefs else ""
    if override:
        path = Path(bpy.path.abspath(override))
        return str(path) if path.is_file() else None
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in _COMMON_FFMPEG_PATHS.get(sys.platform, []):
        if Path(candidate).is_file():
            return candidate
    return None


def json_get(data, path, default=None):
    """Get a nested dict value via dot-notation (path e.g. "naming.version.digits").
    Returns default if any key along the way is missing or a non-dict is hit."""
    for key in path.split("."):
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data


def read_csv(filepath: Path) -> list[dict]:
    """Read a .csv file into a list of row dicts, keyed by header."""
    import csv

    try:
        if filepath.suffix != ".csv":
            raise PipelineError("File selected is not a csv file.")
        # utf-8-sig transparently strips a BOM if present (Excel writes one
        # when saving "CSV UTF-8" on Windows) and behaves like plain utf-8
        # otherwise -- needed for accented text (descriptions, names...).
        with open(filepath, mode="r", encoding="utf-8-sig") as file:
            csv_reader = csv.DictReader(file)  # Create DictReader
            data_list = []  # List to store dictionaries
            for row in csv_reader:
                data_list.append(row)

        return data_list
    except Exception as e:
        raise PipelineError(f"Error durring reading csv file {filepath} : {e}")


def list_to_labels(layout, items, first_icon="INFO", next_icon="BLANK1"):
    """Draw multi-line label groups in a Blender layout."""
    col = layout.column()
    for text_lines in items:
        txt = col.column()
        txt.scale_y = 0.5
        for i, line in enumerate(text_lines):
            txt.label(text=line, icon=first_icon if i == 0 else next_icon)
        txt.separator(factor=2)
    return col


def now(iso: bool = True) -> str | datetime:
    """Current local time: ISO-8601 string (seconds precision) if iso=True,
    raw datetime otherwise. Local, not UTC -- comparing timestamps across
    machines assumes their clocks are roughly aligned."""
    if iso:
        return datetime.now().isoformat(timespec="seconds")
    else:
        return datetime.now()


# Corrects a popup's declared width= vs its actual rendered content-area
# width -- see NOTES.md, "Text wrapping in panels". Recalibrate this one
# constant if popup text still looks off, never the per-call-site formula.
POPUP_WIDTH_SCALE = 3.0


def region_char_budget(
    context: bpy.types.Context,
    margin: int = 2,
    floor: int = 12,
    width_px: float | None = None,
) -> int:
    """Panel width (px) -> characters per line, for text_to_lines()'s max_width.
    Leave width_px unset in a real panel's draw(): context.region there is
    genuinely that panel's own region. Pass a popup/dialog operator's own
    invoke_popup(width=...)/invoke_props_dialog(width=...) value as width_px
    when calling this from that operator's draw() instead -- see
    POPUP_WIDTH_SCALE above for why it needs correcting first."""
    if width_px is not None:
        width_px = width_px * POPUP_WIDTH_SCALE
    else:
        width_px = context.region.width
    char_w = 7.0 * context.preferences.system.ui_scale  # px/char, average
    return max(int(width_px / char_w) - margin, floor)


def _effective_len(text: str, cap_weight: float = 1.3) -> float:
    """Character count, but each uppercase letter counts extra: capitals
    render visibly wider than lowercase in Blender's UI font, so a
    caps-heavy string (an acronym, a title.upper()...) needs more room per
    character than a flat per-char budget assumes. Used by both
    lines_budget() and text_to_lines()'s own wrap decision, so the two
    stay consistent with each other."""
    return sum(cap_weight if ch.isupper() else 1 for ch in text)


def lines_budget(text: str, base: int = 2, per_chars: int = 60, cap: int = 6) -> int:
    """Proportional max_lines for text_to_lines(): short text gets `base`
    lines, longer source text earns a few more before truncating, capped at
    `cap` so a very long text still gets cut rather than take over the
    panel."""
    return min(base + int(_effective_len(text)) // per_chars, cap)


def text_to_lines(
    layout: bpy.types.Layout,
    text: str,
    max_width: float | None = None,
    scale_y: float = 1,
    icon: str = "NONE",
    max_lines: int | None = None,
) -> bpy.types.Layout:
    """Split text into lines at max_width characters (see _effective_len()
    for how a character counts). If max_lines is set and the text would
    take more lines than that, the extra lines are dropped and the last
    visible line is truncated with "..." -- see lines_budget() for a
    max_lines proportional to the text length."""
    if not max_width:
        layout.label(text=text, icon=icon)
        return layout

    split = text.split(" ")
    wrapped = []
    line = ""
    for word in split:
        candidate = word if not line else f"{line} {word}"
        if _effective_len(candidate) > max_width:
            if line:  # skip: first word alone already overflows
                wrapped.append(line)
            line = word
        else:
            line = candidate
    if line:
        wrapped.append(line)

    if max_lines is not None and len(wrapped) > max(max_lines, 1):
        wrapped = wrapped[: max(max_lines, 1)]
        last = wrapped[-1]
        budget = max(max_width - 3, 1)  # room for "..."
        if _effective_len(last) > budget:
            words = last.split(" ")
            while len(words) > 1 and _effective_len(" ".join(words)) > budget:
                words.pop()
            # Character-budget slicing below still counts raw characters, not
            # _effective_len() -- close enough for a last-resort hard cut
            # inside a single overlong word, not worth a second weighted pass.
            last = " ".join(words)[: int(budget)]
        wrapped[-1] = f"{last.rstrip()}..."

    lines = layout.column(align=True)
    lines.separator(factor=1 * scale_y)
    lines.scale_y = scale_y
    for i, wrapped_line in enumerate(wrapped):
        lines.label(text=wrapped_line, icon=(icon if i == 0 else "NONE"))
    return layout


def responsive_layout(context, layout, threshold, align=True):
    if context.region.width > (threshold * context.preferences.system.ui_scale):
        return layout.row(align=align)
    else:
        return layout.column(align=align)


def draw_box_tip(
    layout: bpy.types.Layout,
    context: bpy.types.Context,
    text: str,
    icon: str = "INFO",
    width_px: float | None = None,
) -> None:
    """Short concept explanation drawn inline in a panel, capped to a few
    lines regardless of panel width (see text_to_lines()/lines_budget()).
    No-op unless the user's experience_level preference is "BEGINNER" --
    call unconditionally from a panel's draw(), the gating lives here.
    width_px: leave unset in a panel's draw() to size from the panel's real
    width; pass the popup's own invoke_popup(width=...)/invoke_props_dialog
    (width=...) value when calling this from a popup operator's draw()
    instead -- see region_char_budget()'s docstring."""
    pref = addon_pref(context)
    if not pref or getattr(pref, "experience_level", "BEGINNER") != "BEGINNER":
        return
    box = layout.box().column(align=True)
    box.active = False
    text_to_lines(
        box,
        text,
        max_width=region_char_budget(context, width_px=width_px),
        max_lines=lines_budget(text),
        scale_y=0.8,
        icon=icon,
    )


def get_machine_id(context: bpy.types.Context | None = None) -> str:
    """Persistent per-machine UUID, generated once and stored in the addon
    prefs. Falls back to a MAC-derived id if prefs aren't reachable (e.g. a
    headless subprocess that never registered the addon) -- never crashes,
    locked_json() calls this on every single read/write."""
    prefs = addon_pref(context)
    if prefs is None:
        return f"{uuid.getnode():012x}"
    if not prefs.machine_id:
        prefs.machine_id = uuid.uuid4().hex[:12]
    return prefs.machine_id


# Adjectives/colors and animal names, used only to build a locally-generated
# placeholder display name (random_display_name() below) -- no meaning
# beyond that, no OS/account info involved, same spirit as machine_id above.
_ADJECTIVES = [
    "amber", "azure", "bold", "brisk", "calm", "coral", "crimson", "dusty",
    "emerald", "faded", "fuzzy", "gentle", "golden", "hazy", "indigo",
    "ivory", "jolly", "keen", "lively", "lucky", "mellow", "misty", "mossy",
    "muted", "noble", "olive", "plucky", "quick", "quiet", "rosy", "rusty",
    "sandy", "scarlet", "silent", "silver", "sleepy", "smoky", "sober",
    "solar", "spry", "steady", "stormy", "sunny", "swift", "tawny", "teal",
    "tidy", "vivid", "witty",
]
_ANIMALS = [
    "badger", "beetle", "bison", "dingo", "egret", "finch", "fox", "gecko",
    "hare", "heron", "ibex", "ibis", "jay", "koala", "kite", "lark", "lemur",
    "lynx", "mink", "mole", "moth", "newt", "ocelot", "otter", "panda",
    "puffin", "quail", "raven", "robin", "salmon", "seal", "shrike", "skunk",
    "sloth", "sparrow", "stork", "swan", "tapir", "tern", "toad", "viper",
    "vole", "walrus", "weasel", "wombat", "wren", "yak", "zebra",
]


def random_display_name() -> str:
    """Locally-generated placeholder for prefs.user_name -- picked so several
    unconfigured teammates don't all show up under the same generic string
    (e.g. "locked by unknown") before anyone has typed their own name in."""
    return f"{random.choice(_ADJECTIVES)}-{random.choice(_ANIMALS)}"


def path_reachable(path: str | Path) -> bool:
    """Like Path(path).exists(), but never raises. Path.exists() only
    swallows a narrow set of errno (ENOENT/ENOTDIR/EBADF/ELOOP) -- a mount
    that vanished mid-session (NAS dropped, drive unmapped) surfaces as
    ENODEV or similar instead and propagates as an uncaught OSError.
    Use this for any project-root reachability check: unlike a plain file
    inside an already-known-good project, the root itself is exactly the
    path a disconnected NAS breaks."""
    try:
        return Path(path).exists()
    except OSError:
        return False


def resolve_bpy_path(filepath: str) -> Path:
    """Absolute Path for a Blender-relative filepath (the "//..." convention
    used by Library.filepath and source_library.filepath) -- pathlib doesn't
    understand "//" on its own, only bpy.path.abspath() resolves it.
    normpath()'d: bpy.path.abspath() leaves any "../" in place (see
    NOTES.md), and a stored path is expected clean."""
    return Path(os.path.normpath(bpy.path.abspath(filepath)))


# ---------------------------------------------------------------------------
# Read Write Json utiles
# ---------------------------------------------------------------------------
# 3x the heartbeat interval, deliberately -- see NOTES.md, "Lock staleness".
LOCK_STALE_SECONDS = 90


def _is_unlock(lockpath: Path) -> bool:
    """Whether a lock file is stale (older than LOCK_STALE_SECONDS) or
    unreadable/corrupt -- fail-open, so garbage never freezes the resource
    forever. Only the writer path acts on this to steal a lock; readers never do."""
    try:
        data = json.loads(lockpath.read_text(encoding="utf-8"))
        age = (now(iso=False) - datetime.fromisoformat(data["at"])).total_seconds()
        return age > LOCK_STALE_SECONDS
    except Exception:
        return True


def acquire_lock(
    path: Path, machine_id: str, retries: int = 10, delay: float = 0.1
) -> bool:
    """Acquire an exclusive write lock for `path` via an O_EXCL lock file,
    retrying `retries` times `delay` seconds apart. A stale lock (_is_unlock)
    is removed and re-taken -- not atomic, so two writers racing on the same
    stale lock is possible but rare. True once acquired, False if still held."""
    lockpath = path.parent / f".{path.name}.lock"
    payload = json.dumps({"machine_id": machine_id, "at": now()}).encode("utf-8")
    lockpath.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(retries):
        try:
            fd = os.open(str(lockpath), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, payload)
            os.close(fd)
            return True
        except FileExistsError:
            if _is_unlock(lockpath):
                try:
                    lockpath.unlink()
                except FileNotFoundError:
                    pass  # someone else already picked it up meanwhile, loop back
                continue
            time.sleep(delay)
    return False


def check_lock(path: Path, retries: int = 10, delay: float = 0.1) -> bool:
    """Poll up to `retries` * `delay` seconds for the lock on `path` to
    clear, without ever taking, stealing, or removing it -- only observes.
    Used by read-only access, which must yield briefly to an in-flight write
    but never block one. True if still held after all retries, False if cleared."""
    lockpath = path.parent / f".{path.name}.lock"
    lockpath.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(retries):
        if lockpath.exists():
            time.sleep(delay)
        else:
            return False
    return True


def release_lock(path: Path, machine_id: str) -> None:
    """Release the lock for `path`, but only if this machine owns it.

    The machine_id check prevents releasing a lock that was stolen from us
    (e.g. after we were presumed stale). A missing lock file is not an error.
    """
    lockpath = path.parent / f".{path.name}.lock"
    try:
        data = json.loads(lockpath.read_text(encoding="utf-8"))
        if data.get("machine_id") == machine_id:
            lockpath.unlink()
    except FileNotFoundError:
        pass


def refresh_lock(path: Path, machine_id: str) -> bool:
    """Re-timestamp the lock this machine already holds on `path`, so it
    doesn't go stale while still legitimately in use. Never creates or
    steals: does nothing and returns False if there's no lock, or if it now
    belongs to someone else (e.g. stolen during a long network hiccup)."""
    lockpath = path.parent / f".{path.name}.lock"
    try:
        data = json.loads(lockpath.read_text(encoding="utf-8"))
        if data.get("machine_id") != machine_id:
            return False
        payload = json.dumps({"machine_id": machine_id, "at": now()}).encode("utf-8")
        lockpath.write_bytes(payload)
        return True
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False


@contextmanager
def locked_json(path: Path, read_only=False):
    """Read/write a JSON file under a cross-process lock. Yields a mutable
    box {"data": <parsed JSON or None>, "action": ""} -- set action to
    "to_write" (atomic tmp + os.replace) or "to_delete" to commit on exit,
    leave it "" for a plain read. read_only=False (default) acquires an
    exclusive lock, raising PipelineError if still held after retries (may
    steal a stale one); read_only=True never takes/steals/releases it --
    waits briefly for an in-flight write, then reads regardless (a write
    attempt is refused and logged, not silently dropped)."""
    machine_id = get_machine_id()
    if read_only:
        check_lock(path)
    else:
        if not acquire_lock(path, machine_id):
            raise PipelineError(f"{path} is locked by another process.")
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        box = {"data": data, "action": ""}
        yield box
        if box["action"] != "" and read_only:
            log(
                "WARNING",
                "JSON_reading",
                f"Asked {box['action']} on {path} but was in Read_Only. Action cancelled.",
            )
            return
        elif box["action"] == "to_write":
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(box["data"], indent=4), encoding="utf-8")
            os.replace(tmp, path)
        elif box["action"] == "to_delete":
            try:
                os.remove(path)
            except OSError:
                pass
    finally:
        if not read_only:
            release_lock(path, machine_id)
