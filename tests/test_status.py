"""The state engine (lib/status.py), without Blender: each state from
its facts, the shares done. Grows with phase 3 (Waiting, To redo, Omit).

    python3 tests/test_status.py
"""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    status = importlib.import_module(f"{fake_bpy.load().__name__}.lib.status")
    facts = {
        "validated_departments": {"layout": True, "anim": True},
        "worked_departments": {"anim": [{}], "fx": [{}]},
        "started_departments": ["light"],
    }
    expected = {"layout": "done", "anim": "rework", "fx": "wip", "light": "wip", "comp": "todo"}
    for d, state in expected.items():
        assert status.department_state(facts, d) == state, (d, status.department_state(facts, d))
    assert set(status.STATE_LABELS) == {"todo", "wip", "done", "rework"}
    w = status.progress_weights({"snapshot": {"progress": {"wip": 150, "rework": "x"}}})
    assert w == {"wip": 100, "rework": 67, "rtk": 67}, w
    w = status.PROGRESS_WEIGHTS
    assert status.department_score("done", False, w) == 1.0
    assert status.department_score("done", True, w) == 0.67
    assert status.department_score("todo", False, w) == 0
    item = {"scores": {"a": 1.0, "b": 0.0}, "departments": {"a": "done", "b": "todo"},
            "general_rtk": True, "rtk_departments": []}
    assert abs(status.file_progress(item, w) - (1.0 - 0.33) / 2) < 1e-9
    assert status.file_progress({"scores": {}}, w) is None
    print("OK: status")


if __name__ == "__main__":
    main()
