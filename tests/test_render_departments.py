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
    # The main render: the highest stage's department, else the newest.
    import json, tempfile
    snapshot = importlib.import_module(f"{pkg}.lib.snapshot")
    root = Path(tempfile.mkdtemp())
    owner = root / "shots" / "sq010" / "sq010_sh010"
    (owner / ".pipeline").mkdir(parents=True)
    entries = []
    for n, (dep, when) in enumerate([("layout", "10"), ("lighting", "11"), ("animation", "12"), ("", "13")], 1):
        out = root / "renders" / "sq010" / "sh010" / f"v00{n}_001"
        out.mkdir(parents=True)
        entries.append({"status": "finished", "department": dep, "completed_at": f"2026-11-{when}T10:00:00+01:00",
                        "output_path": (out / "f_####.png").relative_to(root).as_posix(), "source_file": f"sq010_sh010_v00{n}.blend"})
    (owner / ".pipeline" / "render_history.json").write_text(json.dumps({"entries": entries}))
    stages = {"layout": 1, "animation": 2, "lighting": 3}
    r = snapshot.read_render_state(root, "shot", owner, "v", stages)[0]
    assert r["department"] == "lighting", r
    assert [(o["department"], o["newer"]) for o in r["others"]] == [("animation", True), ("layout", False), ("", True)], r["others"]
    r = snapshot.read_render_state(root, "shot", owner, "v", stages, latest=True)[0]
    assert r["department"] == "", r
    r = snapshot.read_render_state(root, "shot", owner, "v", {})[0]
    assert r["department"] == "animation", r  # no stages: the newest with a department
    print("OK: render departments")


if __name__ == "__main__":
    main()
