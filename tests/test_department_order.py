"""Departments in the project's order (lib/config.py ordered_departments()):
a file's own kind's list first -- a department named in both lists (an
asset "lighting" and a shot "lighting") at its place in the shots' for a
shot, not first because the assets' come first -- without Blender.

    python3 tests/test_department_order.py
"""

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    config = importlib.import_module(f"{pkg.__name__}.lib.config")
    tracking = importlib.import_module(f"{pkg.__name__}.lib.monitoring.tracking")

    project = {
        "assets_departments": ["modeling", "texturing", "lighting"],
        "shots_departments": ["layout", "animation", "lighting", "render"],
    }
    config.ConfigCache.get = classmethod(lambda cls: project)
    required = ["render", "lighting", "animation", "layout"]
    assert config.ordered_departments(required, "shots") == ["layout", "animation", "lighting", "render"]
    assert config.ordered_departments(["lighting", "texturing", "modeling"], "assets") == ["modeling", "texturing", "lighting"]
    # No kind: the assets' first, then the shots' (an entry's departments).
    assert config.ordered_departments(["render", "modeling"]) == ["modeling", "render"]
    # One the project doesn't list: after them, as given.
    assert config.ordered_departments(["fx", "layout"], "shots") == ["layout", "fx"]

    assert tracking.owner_kind(Path("/p/shots/sq010/sh010")) == "shots"
    assert tracking.owner_kind(Path("/p/assets/ch/ch_bob")) == "assets"
    assert tracking.owner_kind(Path("/p/library/mat/mat_wood")) == "assets"
    status = tracking._status_from_raw({
        "tracking": {"departments_required": required},
        "last_stable": {}, "wipmetas": [], "started": [], "kind": "shots",
    })
    assert status["departments_required"] == ["layout", "animation", "lighting", "render"], status["departments_required"]
    assert [i[0] for i in status["departments_items"]] == ["layout", "animation", "lighting", "render"]

    print("department order: ok")


if __name__ == "__main__":
    main()
