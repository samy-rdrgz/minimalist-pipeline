"""Renders by department (phase 5), without Blender: a preset's
department from its name, the to check entries' keys.

    python3 tests/test_render_departments.py
"""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load().__name__
    status = importlib.import_module(f"{pkg}.lib.status")
    tracking = importlib.import_module(f"{pkg}.lib.tracking")
    deps = ["layout", "look_dev", "look", "animation", "render"]
    for preset, want in {
        "look_dev_hd": "look_dev", "LOOK-x": "look", "animation": "animation",
        "anim": "", "render_final": "render", "renderfarm": "", "": "", None: "",
        "Layout_v2": "layout",
    }.items():
        got = status.preset_department(preset, deps)
        assert got == want, (preset, got, want)
    assert tracking.to_check_key("sh040", "animation") == "sh040#animation"
    assert tracking.to_check_key("", "") == "" and tracking.to_check_key("sh040") == "sh040"
    data = {"to_check": {"sh040": {"render": "r/v1"}, "sh040#animation": {"render": "r/v2", "department": "animation"}, "x": 3}}
    entries = tracking.to_check_entries(data)
    assert [k for k, _ in entries] == ["sh040", "sh040#animation"], entries
    assert entries[0][1]["shot"] == "sh040" and entries[0][1]["department"] == ""
    assert entries[1][1]["shot"] == "sh040" and entries[1][1]["department"] == "animation"
    assert tracking.render_to_check_label("sh040#animation", entries[1][1]) == "sh040 animation v2"
    assert tracking.render_to_check_label("", {"render": "r/v3"}) == "v3"
    print("OK: render departments")


if __name__ == "__main__":
    main()
