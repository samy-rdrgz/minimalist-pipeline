"""The form each kind of project file is written in, as a number in the
file itself: "format_version". Stamped by write_json_atomic() (so by
locked_json() too) on every JSON object it writes whose name is listed
here; checked on every locked write: a file a newer addon wrote, in a
form this one doesn't know, is never rewritten by it (that would drop
what it doesn't know) -- PipelineError, the artist told to update.

A file without the key was written before 2.0: version 0, the form
lib/migration.py brings to 1. Bump a kind's number when its form changes
in a way an older addon would misread, and teach migration the step.

Pure stdlib: farm workers and background threads read it too."""

import re
from pathlib import Path

KEY = "format_version"

# kind: (file name pattern, version this addon writes)
FORMATS: dict[str, tuple[str, int]] = {
    "project_config": (r"project_config\.json", 1),
    "tracking": (r"tracking\.json", 1),
    "stablemeta": (r".+\.stablemeta", 1),
    "wipmeta": (r".+\.wipmeta", 1),
    "render_history": (r"render_history\.json", 1),
    "preset_pace": (r"preset_pace\.json", 1),
    "rushes": (r"rushes\.json", 1),
    "session": (r"\.session_\d+\.json", 1),
    "farm_worker": (r"worker_[0-9a-f-]+\.json", 1),
}

_COMPILED = [(k, re.compile(r"(^|/)" + p + r"\Z"), v) for k, (p, v) in FORMATS.items()]


def kind_of(path) -> str | None:
    """The kind of project file path is, None if not one listed."""
    name = Path(path).as_posix()
    for kind, rx, _v in _COMPILED:
        if rx.search(name):
            return kind
    return None


def current(path) -> int | None:
    """The version this addon writes path in, None if not a listed kind."""
    kind = kind_of(path)
    return FORMATS[kind][1] if kind else None


def version_of(data) -> int:
    """The version data was written in: 0 before 2.0 (no key)."""
    if isinstance(data, dict):
        try:
            return int(data.get(KEY) or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def stamp(path, data):
    """data with its kind's version, for writing to path (an object of a
    listed kind; anything else as it is)."""
    v = current(path)
    if v is None or not isinstance(data, dict):
        return data
    if data.get(KEY) == v:
        return data
    return {KEY: v, **{k: val for k, val in data.items() if k != KEY}}


def too_new(path, data) -> int | None:
    """The version data has if a newer addon wrote it (more than this one
    knows for path's kind), else None."""
    v = current(path)
    got = version_of(data)
    return got if v is not None and got > v else None
