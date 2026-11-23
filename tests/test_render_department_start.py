"""The Render dialog's first department (operators/farm_ops.py
furthest_department()): the furthest along -- the latest stage, then the
latest in the project's order -- of the file's kind's departments worked
since its latest stable, worked at it or done there; "" for a file with
none -- without Blender.

    python3 tests/test_render_department_start.py
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
    farm_ops = importlib.import_module(f"{pkg.__name__}.operators.farm_ops")

    project = {
        "assets_departments": ["modeling", "texturing", "rigging"],
        "shots_departments": ["layout", "animation", "fx", "lighting"],
        # layout > animation, fx > lighting
        "department_stages": {"shots": {"layout": 1, "animation": 2, "fx": 2, "lighting": 3}},
    }
    farm_ops.ConfigCache.get = classmethod(lambda cls: project)
    status = {}
    farm_ops.TrackingStatusCache.get = classmethod(lambda cls, fp, *a, **k: status)
    shot = "/p/shots/sq010/sh010/sq010_sh010_v004.blend"

    # The example: layout worked in the stable, layout and animation done there.
    status.update(stable_worked=["layout"], validated_departments={"layout": True, "animation": True}, worked_departments={})
    assert farm_ops.furthest_department(shot) == "animation"
    # Lighting worked since (a session): further along.
    status["worked_departments"] = {"lighting": [{}]}
    assert farm_ops.furthest_department(shot) == "lighting"
    # Two at the same stage: the latest in the project's order.
    status.update(stable_worked=[], validated_departments={"fx": True, "animation": True}, worked_departments={})
    assert farm_ops.furthest_department(shot) == "fx"
    # Nothing worked nor done: none (the last render's then, in invoke()).
    status.clear()
    assert farm_ops.furthest_department(shot) == ""
    # No stages: the project's order alone; an asset's own departments only.
    project.pop("department_stages")
    status.update(validated_departments={"modeling": True, "rigging": True, "lighting": True})
    assert farm_ops.furthest_department("/p/assets/ch/ch_bob/ch_bob_v002.blend") == "rigging"
    assert farm_ops.furthest_department("") == ""

    print("render department start: ok")


if __name__ == "__main__":
    main()
