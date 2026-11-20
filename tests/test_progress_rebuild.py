"""The days before the progress log, rebuilt by Migrate old data
(progress_log.rebuild()): an asset's history -- made, worked, a stable,
validated, a retake opened then closed -- read back day by day, each day
as it stood that evening; a day nothing changed holding the day before's;
a day already logged kept as logged.

    python3 tests/test_progress_rebuild.py
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
    pl = importlib.import_module(f"{pkg.__name__}.lib.monitoring.progress_log")
    migration = importlib.import_module(f"{pkg.__name__}.lib.migration")

    tz = "+01:00"
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "config").mkdir()
        (root / "config" / "project_config.json").write_text(
            json.dumps({"validation_roles": [{"name": "prod", "level": 1}]}), encoding="utf-8"
        )
        pipe = root / "assets" / "ch" / "ch_bob" / ".pipeline"
        pipe.mkdir(parents=True)

        def write(name, data):
            (pipe / name).write_text(json.dumps(data), encoding="utf-8")

        write("tracking.json", {
            "file_name": "ch_bob", "created_at": f"2026-10-01T10:00:00{tz}",
            "departments_required": ["modeling"],
            "entries": [{
                "id": "r1", "type": "rtk", "text": "bigger nose", "author": "ana",
                "created_at": f"2026-10-06T10:00:00{tz}", "departments": ["modeling"],
                "done": True, "done_at": f"2026-10-08T10:00:00{tz}",
            }],
        })
        write("ch_bob_v001.wipmeta", {
            "file": "ch_bob_v001.blend", "created_at": f"2026-10-01T10:00:00{tz}",
            "edited_at": f"2026-10-02T18:00:00{tz}",
            "sessions": {"s1": {"departments": ["modeling"], "saved_at": f"2026-10-02T18:00:00{tz}", "by": "lea"}},
        })
        write("ch_bob_v001-stable.stablemeta", {
            "file": "ch_bob_v001-stable.blend", "created_at": f"2026-10-03T12:00:00{tz}",
            "departments_done": {"modeling": True}, "departments_started": ["modeling"],
            "departments_worked": ["modeling"], "approvals_carried": True,
            "approvals": {"modeling": {"prod": {"by": "ana", "at": f"2026-10-05T11:00:00{tz}"}}},
        })
        # A day the log holds already: kept as logged.
        pl.record(root, "2026-10-04", {"shots": {}, "assets": {"done": 0.42}})

        plan = migration.plan_migration(root)
        assert plan["counts"].get("progress: days rebuilt"), plan["counts"]
        folders = plan["progress"]
        n = pl.rebuild(root, folders, {"validation_roles": [{"name": "prod", "level": 1}]}, today="2026-10-10")
        days = pl.days(root)
        assert n == 8 and len(days) == 9, (n, list(days))
        done = {k: v["assets"]["done"] for k, v in days.items()}
        val = {k: v["assets"].get("validated") for k, v in days.items()}
        assert done["2026-10-01"] == 0, done  # made, nothing worked
        assert 0 < done["2026-10-02"] < 1, done  # worked: in progress
        assert done["2026-10-03"] == 1 and val["2026-10-03"] == 0, (done, val)  # a stable, done
        assert done["2026-10-04"] == 0.42 and "rebuilt" not in days["2026-10-04"]  # as logged
        assert val["2026-10-05"] == 1 and val["2026-10-06"] == 1, val  # validated
        assert done["2026-10-06"] < 1 and done["2026-10-07"] == done["2026-10-06"], done  # a retake open
        assert done["2026-10-08"] == 1 and done["2026-10-09"] == 1, done  # closed
        assert days["2026-10-09"]["rebuilt"] is True
        # Nothing left to rebuild: the plan says so.
        assert pl.rebuild(root, folders, {}, today="2026-10-10") == 0
    print("OK: progress rebuilt")


if __name__ == "__main__":
    main()
