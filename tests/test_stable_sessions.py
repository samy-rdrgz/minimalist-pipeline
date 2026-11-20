"""A -stable file saved in place (Save anyway on a stable, which has no
.wipmeta): its session in its .stablemeta's "sessions" -- who, when, the
departments ticked --, its own "departments_worked" (the state engine's)
left as it was. A wip version's still in its .wipmeta.

    python3 tests/test_stable_sessions.py
"""

import importlib
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    core = importlib.import_module(f"{pkg.__name__}.lib.core")
    core.get_machine_id = lambda *a, **k: "test-machine"
    tracking = importlib.import_module(f"{pkg.__name__}.lib.monitoring.tracking")
    tracking.get_machine_id = core.get_machine_id
    tracking.get_user = lambda *a, **k: "samy"

    with tempfile.TemporaryDirectory() as d:
        owner = Path(d) / "assets" / "ch" / "ch_bob"
        pipe = owner / ".pipeline"
        pipe.mkdir(parents=True)
        stable = owner / "ch_bob_v005-stable.blend"
        meta = pipe / "v005-stable.stablemeta"
        meta.write_text(json.dumps({"departments_done": {"rig": True}, "departments_worked": ["rig"]}), encoding="utf-8")
        read = lambda: json.loads(meta.read_text(encoding="utf-8"))  # noqa: E731

        assert not tracking.saved_in_place(stable)
        tracking.wipmeta_touch(stable)  # its Save anyway
        m = read()
        mine = m["sessions"][tracking._session_id()]
        assert mine["by"] == "samy" and mine["departments"] == [] and mine["saved_at"], m
        assert m["departments_worked"] == ["rig"] and m["edited_by"] == "samy", m
        assert tracking.saved_in_place(stable)

        tracking.wipmeta_add_work(stable, ["rig", "shading"])  # Working on, ticked
        assert read()["sessions"][tracking._session_id()]["departments"] == ["rig", "shading"]
        tracking._session_worked_cache.clear()
        assert tracking.get_session_worked_departments(stable) == ["rig", "shading"]
        assert read()["departments_worked"] == ["rig"]

        # A wip version: its .wipmeta's "sessions" (2.0), the 1.x name
        # "departments_worked" kept beside it, equal (lib/monitoring/legacy.py).
        wip = owner / "ch_bob_v006.blend"
        # A 1.x's session there already, under the old name only.
        old = {"departments": ["anim"], "saved_at": "2026-11-01T10:00:00+01:00", "by": "lea"}
        (pipe / "v006.wipmeta").write_text(json.dumps({"linked": [], "departments_worked": {"1_other": old}}), encoding="utf-8")
        tracking.wipmeta_add_work(wip, ["rig"], linked_libs=[])
        w = json.loads((pipe / "v006.wipmeta").read_text(encoding="utf-8"))
        assert w["sessions"][tracking._session_id()]["departments"] == ["rig"], w
        assert w["sessions"]["1_other"] == old, w
        assert w["departments_worked"] == w["sessions"], w
        # The 1.x saves again (its key only): read as it wrote it.
        w["departments_worked"]["1_other"] = dict(old, departments=["anim", "fx"])
        assert sorted(d for s in tracking.worked_sessions(w) for d in s["departments"]) == ["anim", "fx", "rig"]
    print("OK: stable sessions")


if __name__ == "__main__":
    main()
