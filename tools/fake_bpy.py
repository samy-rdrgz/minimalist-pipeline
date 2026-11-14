"""Import the whole addon without Blender: every bpy* / mathutils / gpu...
module a MagicMock, bpy.types a module whose every attribute is an empty
class (so `class X(bpy.types.Panel)` works). Catches broken imports and
names missing from the __init__ files.

    python3 tools/fake_bpy.py            # from the repository's root

Also imported by tests/ (install(), load())."""

import importlib
import os
import pkgutil
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parent.parent
_MODULES = [
    "bpy", "bpy.props", "bpy.utils", "bpy.utils.previews", "bpy.utils.units", "bpy.app",
    "bpy.app.handlers", "bpy.app.timers", "bpy.ops", "bpy.path", "bpy_extras",
    "bpy_extras.io_utils", "mathutils", "gpu", "gpu_extras", "gpu_extras.batch", "blf", "bmesh",
]


class _Types(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = type(name, (), {})
        setattr(self, name, cls)
        return cls


def install() -> None:
    """The fake modules in sys.modules."""
    for m in _MODULES:
        sys.modules.setdefault(m, MagicMock())
    sys.modules["bpy"].types = sys.modules["bpy.types"] = _Types("bpy.types")
    sys.modules["bpy"].app.version = (4, 2, 0)


def load(path: Path = REPO, name: str = "minimalist_pipeline"):
    """The addon at path imported as the package name (through a symlink in
    a temporary folder)."""
    install()
    pkg_dir = Path(tempfile.gettempdir()) / "mp_fake_bpy"
    pkg_dir.mkdir(exist_ok=True)
    link = pkg_dir / name
    if not link.exists():
        os.symlink(path, link)
    if str(pkg_dir) not in sys.path:
        sys.path.insert(0, str(pkg_dir))
    return importlib.import_module(name)


if __name__ == "__main__":
    pkg = load()
    n = 0
    for mi in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        if ".templates" not in mi.name and ".tests" not in mi.name and ".tools" not in mi.name:
            importlib.import_module(mi.name)
            n += 1
    print(f"OK: {n} modules, {len(getattr(pkg, 'classes', ()))} classes")
