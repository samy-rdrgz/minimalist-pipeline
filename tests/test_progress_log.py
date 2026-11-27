"""The progress over time (lib/monitoring/progress_log.py): a point's
figures from a snapshot, a day written once for the same figures, and the
day of the project's last change before today (its newest .pipeline).

    python3 tests/test_progress_log.py
"""

import importlib
import json
import os
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
    core = importlib.import_module(f"{pkg.__name__}.lib.core")
    core.get_machine_id = lambda *a, **k: "test-machine"
    pl = importlib.import_module(f"{pkg.__name__}.lib.monitoring.progress_log")

    snap = {
        "meta": {"progress": {"shot": 0.5, "asset": None}, "validation": {"shot": 0.25, "asset": None}},
        "shots": [
            {"departments": {"anim": "done"}, "scores": {"anim": 1.0}, "validated": {"anim": True}},
            {"departments": {"anim": "wip"}, "scores": {"anim": 0.5}, "validated": {"anim": False}},
            {"departments": {"anim": "done"}, "scores": {"anim": 1.0}, "validated": {"anim": True}, "omit": "on_hold"},
        ],
        "assets": [],
    }
    f = pl.figures(snap)
    assert f["shots"]["done"] == 0.5 and f["shots"]["departments"]["anim"] == {
        "done": 0.75, "validated": 0.5, "states": {"todo": 0, "wip": 1, "done": 0, "val": 1}}, f
    # Files by state (Breakdown): the one set aside out of them.
    assert f["shots"]["states"] == {"todo": 0, "wip": 1, "done": 0, "val": 1}, f["shots"]

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        assert pl.record(root, "2026-11-13", f)
        assert not pl.record(root, "2026-11-13", f)  # same figures: nothing written
        data = json.loads(pl.path_of(root).read_text(encoding="utf-8"))
        assert data["format_version"] and list(data["days"]) == ["2026-11-13"], data

        # The last change before today: Friday's, not Monday's.
        for name, day in (("ch_a", "2026-11-13"), ("ch_b", "2026-11-16")):
            p = root / "assets" / "ch" / name / ".pipeline"
            p.mkdir(parents=True)
            (p / "tracking.json").write_text("{}", encoding="utf-8")
            t = datetime.fromisoformat(day + "T18:00:00").timestamp()
            os.utime(p, (t, t))
        assert pl._last_change_day(root, "2026-11-16") == "2026-11-13"
        assert pl._last_change_day(root, "2026-11-17") == "2026-11-16"
    print("OK: progress log")


if __name__ == "__main__":
    main()
