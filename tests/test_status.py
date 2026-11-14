"""The state engine (lib/status.py), without Blender: each state from
its facts, the shares done. Grows with phase 3 (Waiting, To redo, On hold).

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
    # Each session by its own date: anim ticked Monday, the stable Tuesday,
    # another session saving Wednesday without ticking it -- not worked since.
    tracking = importlib.import_module(status.__name__.rsplit(".", 1)[0] + ".tracking")
    from datetime import datetime, timezone
    tuesday = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    meta = {"file": "a_v005.blend", "edited_at": "2026-11-11T12:00:00+00:00", "edited_by": "tom",
            "departments_worked": {
                "s1": {"departments": ["anim"], "saved_at": "2026-11-09T12:00:00+00:00", "by": "léa"},
                "s2": {"departments": [], "saved_at": "2026-11-11T12:00:00+00:00", "by": "tom"}}}
    assert tracking._worked_departments([meta], tuesday) == {}, "a later save counted anim"
    meta["departments_worked"]["s2"]["departments"] = ["fx"]
    assert tracking._worked_departments([meta], tuesday) == {"fx": [{"file": "a_v005.blend", "by": "tom"}]}
    # Before Migrate old data: a bare list, the file's date.
    old = {"file": "b.blend", "edited_at": "2026-11-11T12:00:00+00:00", "departments_worked": {"x": ["anim"]}}
    assert list(tracking._worked_departments([old], tuesday)) == ["anim"]
    # Stages: Waiting and To redo.
    deps, stages = status.parse_departments("Layout > anim > fx, light > render")
    assert deps == ["Layout", "anim", "fx", "light", "render"], deps
    assert stages == {"layout": 1, "anim": 2, "fx": 3, "light": 3, "render": 4}, stages
    assert status.departments_text(deps, stages) == "Layout > anim > fx, light > render"
    assert status.parse_departments("layout, anim,render") == (["layout", "anim", "render"], {})
    assert status.departments_text(["layout", "anim"], {}) == "layout, anim"
    assert status.parse_departments("") == ([], {})
    stages = status.parse_departments("layout > anim > fx, light")[1]
    base = {"departments_required": ["layout", "anim", "fx", "light"],
            "validated_departments": {"layout": True}, "worked_departments": {},
            "started_departments": ["anim"],
            "stable_info": {"created_at": "2026-11-09T10:00:00+00:00"}, "stable_worked": []}
    rtk = {"type": "rtk", "done": False, "departments": ["layout"], "created_at": "2026-11-10T09:00:00+00:00"}
    f = status.stage_flags(dict(base, entries=[rtk]), stages)
    assert f["anim"] == {"waiting": "layout RTK"}, f
    assert f["fx"] == {"waiting": "anim not started"} or f["fx"]["waiting"] == "layout RTK", f
    # fx's nearest earlier stage first: anim (started) then layout's RTK.
    assert f["fx"]["waiting"] == "layout RTK" and "layout" not in f, f
    # The RTK closed Tuesday, anim's last session Monday: to redo.
    closed = dict(rtk, done=True, done_at="2026-11-11T09:00:00+00:00")
    facts = dict(base, entries=[closed], last_worked_at={"anim": "2026-11-10T08:00:00+00:00"})
    f = status.stage_flags(facts, stages)
    assert f["anim"]["to_redo"] == "layout changed on 11/11" and "waiting" not in f["anim"], f
    assert "to_redo" not in f.get("fx", {}), "fx not started: never to redo"
    # Saved after, or Still done: up to date.
    later = dict(facts, last_worked_at={"anim": "2026-11-12T08:00:00+00:00"})
    assert "anim" not in status.stage_flags(later, stages)
    synced = dict(facts, departments_synced={"anim": {"at": "2026-11-12T08:00:00+00:00", "by": "léa"}})
    assert "anim" not in status.stage_flags(synced, stages)
    # Changed before the latest stable it was started at: the stable holds it.
    old = dict(base, entries=[dict(closed, done_at="2026-11-08T09:00:00+00:00")])
    assert "anim" not in status.stage_flags(old, stages), status.stage_flags(old, stages)
    # The latest stable made with layout worked, anim started before it.
    restable = dict(base, entries=[], stable_worked=["layout"])
    assert status.stage_flags(restable, stages)["anim"]["to_redo"] == "layout changed on 09/11"
    # No stages: nothing.
    assert status.stage_flags(dict(base, entries=[rtk]), {}) == {}
    # On hold / Cancelled: no stages flags, the marker read only when valid.
    held = dict(base, entries=[rtk], omit={"state": "on_hold", "by": "x", "reason": "edit"})
    assert status.omitted(held)["state"] == "on_hold" and status.stage_flags(held, stages) == {}
    assert status.omitted(dict(base, omit={"state": "nope"})) is None and status.omitted(base) is None
    print("OK: status")


if __name__ == "__main__":
    main()
