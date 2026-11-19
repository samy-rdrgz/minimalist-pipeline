"""The form each kind of project file is written in, in the file itself:
"format_version", the addon version that form came with ("2.0"). Not
bumped with every release: only when a kind's form changes in a way an
older addon would misread -- then to that release's version, and
lib/migration.py taught the step. Stamped by write_json_atomic() (so by
locked_json() too) on every JSON object it writes whose name is listed
here; checked on every locked write: a file a newer addon wrote, in a
form this one doesn't know, is never rewritten by it (that would drop
what it doesn't know) -- PipelineError, the artist told to update.

A file without the key was written by a 1.x: "1.x", read as (1,).

Pure stdlib: farm workers and background threads read it too."""

import re
from pathlib import Path

KEY = "format_version"

# kind: (file name pattern, version this addon writes)
FORMATS: dict[str, tuple[str, str]] = {
    "project_config": (r"project_config\.json", "2.0"),
    "tracking": (r"tracking\.json", "2.0"),
    "stablemeta": (r".+\.stablemeta", "2.0"),
    "wipmeta": (r".+\.wipmeta", "2.0"),
    "render_history": (r"render_history\.json", "2.0"),
    "preset_pace": (r"preset_pace\.json", "2.0"),
    "rushes": (r"rushes\.json", "2.0"),
    "session": (r"\.session_\d+\.json", "2.0"),
    "farm_worker": (r"worker_[0-9a-f-]+\.json", "2.0"),
}

_COMPILED = [(k, re.compile(r"(^|/)" + p + r"\Z"), v) for k, (p, v) in FORMATS.items()]


def kind_of(path) -> str | None:
    """The kind of project file path is, None if not one listed."""
    name = Path(path).as_posix()
    for kind, rx, _v in _COMPILED:
        if rx.search(name):
            return kind
    return None


def _key(v) -> tuple:
    """A version ("2.0", "2.3.1", or the 1.x's none) as comparable numbers."""
    try:
        return tuple(int(p) for p in str(v).split(".")) if v else (1,)
    except ValueError:
        return (1,)


def current(path) -> str | None:
    """The version this addon writes path in, None if not a listed kind."""
    kind = kind_of(path)
    return FORMATS[kind][1] if kind else None


def version_of(data) -> str:
    """The version data was written in: "1.x" if no key."""
    v = data.get(KEY) if isinstance(data, dict) else None
    return str(v) if v else "1.x"


def stamp(path, data):
    """data with its kind's version, for writing to path (an object of a
    listed kind; anything else as it is)."""
    v = current(path)
    if v is None or not isinstance(data, dict):
        return data
    if data.get(KEY) == v:
        return data
    return {KEY: v, **{k: val for k, val in data.items() if k != KEY}}


def too_new(path, data) -> str | None:
    """The version data has if a newer addon wrote it (a form this one
    doesn't know for path's kind), else None."""
    v = current(path)
    if v is None or not isinstance(data, dict) or not data.get(KEY):
        return None
    got = version_of(data)
    return got if _key(got) > _key(v) else None
