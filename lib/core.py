"""Base types: core utilities."""

from __future__ import annotations

import json
import os
import random
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import bpy

from .background import checkpoint
from . import formats
from .errors import PipelineError
from .logs import log

# The addon's real (possibly namespaced) module name: "bl_ext.<repo>.
# minimalist_pipeline" for an extension install. See NOTES.md, "CSV batch:
# the subprocess couldn't import itself".
ADDON_PACKAGE = __package__.rsplit(".", 1)[0]
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


# Set in the environment of a Blender with a window that works for the farm
# (a viewport render, farm/local.py): this addon behaves there as in a
# background Blender -- no session, lock, auto-version, popup nor timer.
HEADLESS_ENV = "MINIMALIST_PIPELINE_HEADLESS"


def headless() -> bool:
    """A Blender with no artist at it: background (-b), or one the farm
    opened with a window for a viewport render (HEADLESS_ENV)."""
    return bool(bpy.app.background) or os.environ.get(HEADLESS_ENV) == "1"


def blender_command(
    script: str, args=(), *, blend=None, flags=(), factory: bool = False, binary: str = "", window: bool = False
) -> list[str]:
    """The command running templates/<script> in a background Blender (this
    one's binary, or binary): blend opened first with its flags (-o, -F...),
    an exception in the script exiting 1 (not 0, a success), args after
    "--". factory: --factory-startup, no addon or preferences loaded.
    window: a Blender with its window instead (a viewport render) -- run it
    with HEADLESS_ENV set, its script quitting by itself."""
    cmd = [binary or bpy.app.binary_path] + ([] if window else ["-b"])
    if blend:
        cmd.append(str(blend))
    cmd += [str(f) for f in flags]
    if factory:
        cmd.append("--factory-startup")
    cmd += ["--python-exit-code", "1", "--python", str(TEMPLATES_DIR / script), "--"]
    return cmd + [str(a) for a in args]


def get_addon_version() -> str:
    """This addon's version as "X.Y.Z", read via addon_utils (same source as
    Preferences > Add-ons, no second hardcoded copy). Stamped into
    project_config.json on create/edit to track which version wrote it.
    Falls back to "0.0.0" rather than raising -- metadata, never worth blocking on."""
    import addon_utils

    try:
        for mod in addon_utils.modules():
            if mod.__name__ == ADDON_PACKAGE:
                version = mod.bl_info.get("version", (0, 0, 0))
                return ".".join(str(x) for x in version)
    except Exception:
        pass
    return "0.0.0"


def addon_pref(context: bpy.types.Context | None = None):
    """Return addon preferences."""
    try:
        ctx = context or bpy.context
        return ctx.preferences.addons[ADDON_PACKAGE].preferences
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
        with open(filepath, mode="r", encoding="utf-8-sig", newline="") as file:
            # Excel writes ";" in a French locale -- sniffed, never a "sep="
            # line (DictReader would take it for the header). On the header
            # line only: free text in the rows (commas in a description)
            # can't mislead it.
            try:
                dialect = csv.Sniffer().sniff(file.readline(), delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel  # a single column: nothing to detect
            file.seek(0)
            csv_reader = csv.DictReader(file, dialect=dialect)
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
    """Current local time with its UTC offset ("2026-11-14T10:03:00+01:00"):
    ISO-8601 string (seconds precision) if iso=True, aware datetime
    otherwise. See NOTES.md, "Dates with their offset"."""
    at = datetime.now().astimezone()
    return at.isoformat(timespec="seconds") if iso else at


# Before / after any date: aware, comparable with parse_iso()'s.
EARLIEST = datetime.min.replace(tzinfo=timezone.utc)
LATEST = datetime.max.replace(tzinfo=timezone.utc)


def _local(at: datetime) -> datetime:
    """at in this machine's time zone; one without an offset taken as this
    machine's local time. Aware, as it was at the ends of the calendar."""
    try:
        return at.astimezone()
    except (OverflowError, OSError, ValueError):
        return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def parse_iso(value) -> datetime | None:
    """A stored date or time as an aware datetime in this machine's time
    zone; None if absent or unreadable. The one reader of the pipeline's
    dates: ISO 8601 with an offset, without one (written before 1.2: this
    machine's local time), or epoch seconds (heartbeats)."""
    if not value or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return file_time(value)
    try:
        return _local(datetime.fromisoformat(str(value)))
    except ValueError:
        return None


def file_time(timestamp: float) -> datetime | None:
    """Epoch seconds (a file's mtime, a heartbeat) as parse_iso() gives
    dates. None if out of range."""
    try:
        return datetime.fromtimestamp(timestamp, timezone.utc).astimezone()
    except (OverflowError, OSError, ValueError):
        return None


def iso_timestamp(value) -> float | None:
    """parse_iso() as epoch seconds; None if absent or unreadable."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    at = parse_iso(value)
    try:
        return at.timestamp() if at else None
    except (OverflowError, OSError, ValueError):
        return None


def time_key(value) -> float:
    """Sort key of a stored date: in time order, whatever the offsets --
    never their text. Absent or unreadable first."""
    at = iso_timestamp(value)
    return float("-inf") if at is None else at


def local_time(value, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """A stored date as text, in this machine's time zone -- never its text
    cut: written elsewhere, that's another zone's hour. The value as it is
    if unreadable, "" if absent."""
    at = parse_iso(value)
    return f"{at:{fmt}}" if at else str(value or "")


def seconds_since(value) -> float | None:
    """Seconds from a stored time to now; None if absent or unreadable."""
    at = iso_timestamp(value)
    return time.time() - at if at is not None else None


def format_duration(seconds: float) -> str:
    """ "1h02m", "3m05s": a farm time read by a person."""
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def format_pace(seconds: float) -> str:
    """A frame's time: "0.6 s", "12 s", then format_duration() -- "0m00s"
    said nothing of a fast render."""
    if seconds < 10:
        return f"{seconds:.1f} s"
    if seconds < 60:
        return f"{seconds:.0f} s"
    return format_duration(seconds)


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
    """Panel width (px) -> characters per line, for text_to_lines()'s
    max_width. width_px: unset in a panel's draw(), a popup's own width from
    its draw() (corrected by POPUP_WIDTH_SCALE)."""
    if width_px is not None:
        width_px = width_px * POPUP_WIDTH_SCALE
    else:
        width_px = context.region.width
    char_w = 7.0 * context.preferences.system.ui_scale  # px/char, average
    return max(int(width_px / char_w) - margin, floor)


def _effective_len(text: str, cap_weight: float = 1.3) -> float:
    """Character count, each uppercase letter counting extra (wider in
    Blender's UI font) -- shared by lines_budget() and text_to_lines()."""
    return sum(cap_weight if ch.isupper() else 1 for ch in text)


def lines_budget(text: str, base: int = 2, per_chars: int = 60, cap: int = 6) -> int:
    """Proportional max_lines for text_to_lines(): short text gets `base`
    lines, longer source text earns a few more before truncating, capped at
    `cap` so a very long text still gets cut rather than take over the
    panel."""
    return min(base + int(_effective_len(text)) // per_chars, cap)


def text_field(layout: bpy.types.UILayout, data, prop: str, **kwargs):
    """Multi-line text field (UILayout.textbox, Blender 5.1+), or a plain
    one-line prop on older versions."""
    if hasattr(layout, "textbox"):
        layout.textbox(data, prop, **kwargs)
    else:
        layout.prop(data, prop, text="")


def safe_icon(name: str, fallback: str) -> str:
    """name if this Blender version has that icon, else fallback (icons get
    added between versions, and an unknown one makes the draw call raise)."""
    items = bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items
    return name if name in items else fallback


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


# Sidebar width (px, before UI scale) from which two buttons share a row.
SIDE_BY_SIDE_WIDTH = 240


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
    """A short concept tip drawn in a panel, capped to a few lines; no-op
    unless experience_level is "BEGINNER" (call it unconditionally).
    width_px: unset in a panel's draw(), the popup's own width from a
    popup's (region_char_budget())."""
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
    "amber",
    "azure",
    "bold",
    "brisk",
    "calm",
    "coral",
    "crimson",
    "dusty",
    "emerald",
    "faded",
    "fuzzy",
    "gentle",
    "golden",
    "hazy",
    "indigo",
    "ivory",
    "jolly",
    "keen",
    "lively",
    "lucky",
    "mellow",
    "misty",
    "mossy",
    "muted",
    "noble",
    "olive",
    "plucky",
    "quick",
    "quiet",
    "rosy",
    "rusty",
    "sandy",
    "scarlet",
    "silent",
    "silver",
    "sleepy",
    "smoky",
    "sober",
    "solar",
    "spry",
    "steady",
    "stormy",
    "sunny",
    "swift",
    "tawny",
    "teal",
    "tidy",
    "vivid",
    "witty",
]
_ANIMALS = [
    "badger",
    "beetle",
    "bison",
    "dingo",
    "egret",
    "finch",
    "fox",
    "gecko",
    "hare",
    "heron",
    "ibex",
    "ibis",
    "jay",
    "koala",
    "kite",
    "lark",
    "lemur",
    "lynx",
    "mink",
    "mole",
    "moth",
    "newt",
    "ocelot",
    "otter",
    "panda",
    "puffin",
    "quail",
    "raven",
    "robin",
    "salmon",
    "seal",
    "shrike",
    "skunk",
    "sloth",
    "sparrow",
    "stork",
    "swan",
    "tapir",
    "tern",
    "toad",
    "viper",
    "vole",
    "walrus",
    "weasel",
    "wombat",
    "wren",
    "yak",
    "zebra",
]


def is_placeholder_name(name: str) -> bool:
    """name is still random_display_name()'s ("amber-otter"): never typed."""
    adjective, _, animal = str(name or "").partition("-")
    return adjective in _ADJECTIVES and animal in _ANIMALS


# Folders a sync client keeps (their names on disk): a lock written there
# reaches the other machines late, two saves can cross.
_CLOUD_FOLDERS = {"dropbox": "Dropbox", "google drive": "Google Drive", "googledrive": "Google Drive",
                  "my drive": "Google Drive", "onedrive": "OneDrive", "icloud drive": "iCloud", "icloud": "iCloud"}


def cloud_synced(path) -> str:
    """The sync service path lies in ("Dropbox", "OneDrive"...), "" for none."""
    for part in Path(str(path or "")).parts:
        name = part.lower()
        for key, service in _CLOUD_FOLDERS.items():
            if name == key or name.startswith(key + " ") or name.startswith(key + "-"):
                return service
    return ""


def random_display_name() -> str:
    """Locally-generated placeholder for prefs.user_name -- picked so several
    unconfigured teammates don't all show up under the same generic string
    (e.g. "locked by unknown") before anyone has typed their own name in."""
    return f"{random.choice(_ADJECTIVES)}-{random.choice(_ANIMALS)}"


def path_reachable(path: str | Path) -> bool:
    """Path(path).exists() that never raises -- for any project-root check
    (see NOTES.md, "Small gotchas, out of the docstrings")."""
    try:
        return Path(path).exists()
    except OSError:
        return False


# path -> (mtime or None if missing, entries, last checked at -- time.monotonic())
class StampCache:
    """Values read from disk, read again only once their stamp moves (a
    file's mtime): {key: (stamp, value, checked at)}. ttl: within it, not
    even the stamp is checked again -- for draw(), where each check is a
    network round-trip. An entry is replaced whole: thread-safe enough."""

    def __init__(self, ttl: float = 0.0):
        self.ttl = ttl
        self.entries: dict = {}

    def get(self, key, stamp, read, missing=None):
        """read() for key, kept while stamp() gives the same; stamp()
        raising OSError: missing. read() must not raise."""
        now_t = time.monotonic()
        cached = self.entries.get(key)
        if cached and self.ttl and now_t - cached[2] < self.ttl:
            return cached[1]
        try:
            st = stamp()
        except OSError:
            self.entries[key] = (None, missing, now_t)
            return missing
        value = cached[1] if cached and cached[0] == st else read()
        self.entries[key] = (st, value, now_t)
        return value


SCANDIR_TTL = 2.0
_scandir_cache = StampCache(SCANDIR_TTL)


def cached_scandir(path: Path) -> list:
    """os.scandir(path) as a list of os.DirEntry (is_dir()/stat() need no
    extra disk call), cached while path's own mtime is unchanged -- which
    re-checks at most every SCANDIR_TTL seconds. [] if missing/unreadable.
    For draw()/enum callbacks only: a listing up to SCANDIR_TTL old must
    never decide what gets written. See NOTES.md, "Popups on a network
    share"."""

    def read():
        try:
            return list(os.scandir(path))
        except OSError:
            return []

    return _scandir_cache.get(str(path), lambda: path.stat().st_mtime, read, [])


def resolve_bpy_path(filepath: str) -> Path:
    """Absolute Path for a Blender-relative filepath (the "//..." convention
    used by Library.filepath and source_library.filepath) -- pathlib doesn't
    understand "//" on its own, only bpy.path.abspath() resolves it.
    normpath()'d: bpy.path.abspath() leaves any "../" in place (see
    NOTES.md), and a stored path is expected clean."""
    return Path(os.path.normpath(bpy.path.abspath(filepath)))


# ---------------------------------------------------------------------------
# Processes
# ---------------------------------------------------------------------------


def process_alive(pid: int | None, name_hint: str = "") -> bool:
    """Whether process pid runs on this machine (stdlib only, any OS).
    name_hint ("blender", "ffmpeg"): must appear in its executable's name,
    against a reused PID; unreadable, the PID alone decides."""
    if not pid:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        handle = k32.OpenProcess(0x1000, False, int(pid))  # QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: it exists
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            if code.value != 259:  # STILL_ACTIVE
                return False
            if name_hint:
                buf = ctypes.create_unicode_buffer(32768)
                size = wintypes.DWORD(len(buf))
                if k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                    return name_hint.lower() in Path(buf.value).name.lower()
            return True
        finally:
            k32.CloseHandle(handle)

    # Linux / macOS
    try:
        os.kill(int(pid), 0)  # signal 0: existence check only, nothing sent
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # exists, owned by another user
    except OSError:
        return False
    try:
        out = subprocess.run(
            ["ps", "-p", str(int(pid)), "-o", "stat=", "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return True
    if not out:
        return False
    stat, _, comm = out.partition(" ")
    if stat.startswith("Z"):
        return False  # zombie: exited, just not reaped yet
    if name_hint and comm.strip():
        return name_hint.lower() in Path(comm.strip()).name.lower()
    return True


class AdoptedProcess:
    """A Popen stand-in for a process this Blender didn't start (adopted
    after a crash), waited on by PID. poll(): None while it runs, then -1 --
    its exit code unknown, its result to check on disk."""

    adopted = True

    def __init__(self, pid: int, name_hint: str = "", **attrs):
        self.pid = pid
        self.name_hint = name_hint
        self.__dict__.update(attrs)

    def poll(self):
        return None if process_alive(self.pid, self.name_hint) else -1

    def terminate(self):
        try:
            os.kill(self.pid, signal.SIGTERM)
        except OSError:
            pass

    kill = terminate

    def wait(self, timeout=None):
        end = None if timeout is None else time.monotonic() + timeout
        while self.poll() is None:
            if end is not None and time.monotonic() > end:
                raise subprocess.TimeoutExpired(str(self.pid), timeout)
            time.sleep(0.1)
        return -1


# ---------------------------------------------------------------------------
# Read Write Json utiles
# ---------------------------------------------------------------------------
# 3x the heartbeat interval, deliberately -- see NOTES.md, "Lock staleness".
LOCK_STALE_SECONDS = 90


_reads = threading.local()


@contextmanager
def reads_once():
    """Within it, on this thread, read_json_quiet() reads each file once --
    one round trip on a share with latency (ProjectScan, per folder)."""
    _reads.texts = {}
    try:
        yield
    finally:
        _reads.texts = None


def read_json_quiet(path):
    """Parsed JSON at path, or None if missing/unreadable/corrupt. Pure
    os/json -- no bpy, no lock, no log -- so it can run on a background
    reader thread (ProjectScan, the farm snapshot). No lock is needed to
    read: every write is an atomic os.replace(), a reader sees the old or
    the new file, never half of one."""
    checkpoint()  # a reader thread waits out a window operator here
    texts = getattr(_reads, "texts", None)
    try:
        if texts is None:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        key = str(path)
        if key not in texts:
            try:
                texts[key] = Path(path).read_text(encoding="utf-8")
            except OSError:
                texts[key] = None
        return None if texts[key] is None else json.loads(texts[key])
    except (OSError, ValueError):
        return None


def retry_shared_io(fn, *args, attempts: int = 5, delay: float = 0.1):
    """Call fn(*args), retrying on PermissionError up to `attempts` times,
    `delay` seconds apart; re-raises the last error. For os.replace/remove/
    unlink on a shared file, which Windows refuses (WinError 5/32) while
    another process still has it open -- see NOTES.md, "Windows: replace/
    delete refused while a reader has the file open"."""
    for i in range(attempts):
        try:
            return fn(*args)
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay)


def _is_unlock(lockpath: Path) -> bool:
    """Whether a lock file is stale (older than LOCK_STALE_SECONDS) or
    unreadable/corrupt -- fail-open, so garbage never freezes the resource
    forever. Only the writer path acts on this to steal a lock; readers never do."""
    try:
        data = json.loads(lockpath.read_text(encoding="utf-8"))
        age = seconds_since(data["at"])
        return age is None or age > LOCK_STALE_SECONDS
    except PermissionError:
        # Unreadable *right now* (Windows: being deleted, or another
        # process's handle refuses us) is not corrupt -- treating it as
        # stale would let a writer steal a live lock. Assume held.
        return False
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
                    continue
                except FileNotFoundError:
                    continue  # someone else already picked it up meanwhile, loop back
                except PermissionError:
                    pass  # still open somewhere (see retry_shared_io) -- wait, retry
            time.sleep(delay)
        except PermissionError:
            # Lock file mid-deletion by its previous holder (Windows
            # "delete pending": refuses every open until the last handle
            # closes) -- same as held, wait and retry.
            time.sleep(delay)
    return False


def check_lock(path: Path, retries: int = 10, delay: float = 0.1) -> bool:
    """Poll up to `retries` * `delay` seconds for the lock on `path` to
    clear, without ever taking, stealing, or removing it -- only observes.
    A stale lock (_is_unlock()) counts as cleared at once, never waited out
    (see NOTES.md, "Network-share redraw cost"). True if still held (and
    fresh) after all retries, False if cleared or found stale."""
    lockpath = path.parent / f".{path.name}.lock"
    for _ in range(retries):
        if not lockpath.exists() or _is_unlock(lockpath):
            return False
        time.sleep(delay)
    return lockpath.exists() and not _is_unlock(lockpath)


def release_lock(path: Path, machine_id: str) -> None:
    """Release the lock for `path`, but only if this machine owns it.

    The machine_id check prevents releasing a lock that was stolen from us
    (e.g. after we were presumed stale). A missing lock file is not an error.
    """
    lockpath = path.parent / f".{path.name}.lock"
    try:
        data = json.loads(lockpath.read_text(encoding="utf-8"))
        if data.get("machine_id") == machine_id:
            retry_shared_io(lockpath.unlink)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        # Never raise from locked_json()'s finally: it would mask the
        # caller's own outcome. A lock left behind just goes stale.
        log("WARNING", "lock", f"Could not release lock {lockpath.name}: {e}")


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


def write_json_atomic(path: Path, data, attempts: int = 5) -> None:
    """Write data as JSON to path atomically: a .tmp, then os.replace() --
    a reader sees the old file or the new one, never half of one. No lock:
    for a file with one writer (a chunk claim), or under locked_json()'s.
    attempts: tries for the replace (retry_shared_io()). Raises if it
    fails, the .tmp removed."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = formats.stamp(path, data)  # its "format_version" (lib/formats.py)
    tmp.write_text(json.dumps(data, indent=4), encoding="utf-8")
    try:
        retry_shared_io(os.replace, tmp, path, attempts=attempts)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


@contextmanager
def locked_json(path: Path, read_only=False, retries: int = 10, io_attempts: int = 5):
    """Read/write a JSON file under a cross-process lock. Yields {"data",
    "action"}: set action to "to_write" (atomic replace) or "to_delete" to
    commit on exit. read_only=False: an exclusive lock, PipelineError if
    still held after retries (a stale one stolen); True: no lock, a brief
    wait for a write in flight. retries: polls 0.1 s apart (0 on the UI
    thread). io_attempts: tries for the final replace/remove
    (retry_shared_io())."""
    machine_id = get_machine_id()
    if read_only:
        if retries > 0:  # 0: don't even look at the lock file
            check_lock(path, retries=retries)
    else:
        if not acquire_lock(path, machine_id, retries=retries):
            raise PipelineError(f"{path} is locked by another process.")
    try:
        try:  # no exists() first: one disk call, not two
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = None
        newer = None if read_only else formats.too_new(path, data)
        if newer is not None:
            # A newer addon's form: rewriting it would drop what this one doesn't know.
            raise PipelineError(
                f"{Path(path).name} was written by a newer Minimalist Pipeline "
                f"(form of {newer}, this one knows {formats.current(path)}): update the addon on this machine."
            )
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
            write_json_atomic(path, box["data"], attempts=io_attempts)
        elif box["action"] == "to_delete":
            try:
                retry_shared_io(os.remove, path, attempts=io_attempts)
            except FileNotFoundError:
                pass
            except OSError as e:
                # Swallowed (callers never expected a raise), but logged.
                log("WARNING", "JSON_writing", f"Could not delete {path}: {e}")
    finally:
        if not read_only:
            release_lock(path, machine_id)
