"""The dot on a department's diamond (lib/monitoring/status.py
render_freshness(), snapshot.py _render_presets()'s "at"): its own render
started after its latest session, or before -- without Blender.

    python3 tests/test_render_fresh.py
"""

import importlib
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    status = importlib.import_module(f"{pkg.__name__}.lib.monitoring.status")
    snapshot = importlib.import_module(f"{pkg.__name__}.lib.monitoring.snapshot")

    facts = {
        "last_worked_at": {"anim": "2026-11-23T10:00:00+00:00"},
        "stable_info": {"created_at": "2026-11-20T09:00:00+00:00"},
        "stable_worked": ["layout"],
    }
    out = status.render_freshness(facts, {
        "anim": "2026-11-23T11:00:00+00:00",      # after its session: fresh
        "layout": "2026-11-19T12:00:00+00:00",    # before the stable it was worked in
        "lighting": "2026-11-01T12:00:00+00:00",  # never worked since: fresh
        "comp": "",                               # unreadable: left out
    })
    assert out == {
        "anim": {"fresh": True, "at": "2026-11-23T11:00:00+00:00"},
        "layout": {"fresh": False, "at": "2026-11-19T12:00:00+00:00"},
        "lighting": {"fresh": True, "at": "2026-11-01T12:00:00+00:00"},
    }, out
    # Worked again after the render: older.
    later = dict(facts, last_worked_at={"anim": "2026-11-23T12:00:00+00:00"})
    assert status.render_freshness(later, {"anim": "2026-11-23T11:00:00+00:00"})["anim"]["fresh"] is False

    # When the latest finished render of each department started: its end
    # less its duration; a failed one, or one with no department, doesn't count.
    with tempfile.TemporaryDirectory() as tmp:
        owner = Path(tmp)
        (owner / ".pipeline").mkdir()
        entries = [
            {"department": "anim", "status": "finished", "completed_at": "2026-11-23T12:00:00+00:00", "duration_seconds": 3600},
            {"department": "anim", "status": "failed", "completed_at": "2026-11-23T15:00:00+00:00"},
            {"department": "Lighting", "status": "finished", "completed_at": "2026-11-22T08:00:00+00:00"},
            {"department": "", "status": "finished", "completed_at": "2026-11-23T16:00:00+00:00"},
        ]
        (owner / ".pipeline" / "render_history.json").write_text(json.dumps({"entries": entries}))
        at = snapshot._render_presets(owner)["at"]
        assert set(at) == {"anim", "lighting"}, at
        assert datetime.fromisoformat(at["anim"]) == datetime.fromisoformat("2026-11-23T11:00:00+00:00"), at
        assert datetime.fromisoformat(at["lighting"]) == datetime.fromisoformat("2026-11-22T08:00:00+00:00"), at
    print("render fresh: ok")


if __name__ == "__main__":
    main()
