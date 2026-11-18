"""Migrate old data (lib/migration.py) on a made-up project in the old
forms, without Blender: what each step completes, the backups, a second
run finding nothing, and a stable already half renamed (departments_done).

    python3 tests/test_migration.py
"""

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def main() -> None:
    import importlib

    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    core = importlib.import_module(f"{pkg.__name__}.lib.core")
    migration = importlib.import_module(f"{pkg.__name__}.lib.migration")
    core.get_machine_id = lambda *a, **k: "test-machine"  # a MagicMock isn't JSON

    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "proj"
        pipe = root / "assets" / "ch" / "ch_bob" / ".pipeline"
        write(pipe / "tracking.json", {
            "departments_required": ["modeling", "shading"],
            "entries": [
                # Before 1.1.0: one "department".
                {"id": "e1", "type": "rtk", "department": "modeling", "text": "x",
                 "done": False, "created_at": "2026-10-01T10:00:00"},
                {"id": "e2", "type": "note", "departments": ["shading"], "text": "y",
                 "created_at": "2026-10-01T11:00:00+02:00"},
            ],
        })
        # Before 1.1.9: no departments_started, the earlier validations not
        # carried (approvals_previous only).
        write(pipe / "ch_bob_v001-stable_001.stablemeta", {
            "file": "ch_bob_v001-stable_001.blend", "created_at": "2026-10-02T10:00:00",
            "created_from": "ch_bob_v001.blend",
            "departments_validated": {"modeling": True},
            "approvals": {"modeling": {"prod": {"by": "ana", "at": "2026-10-02T11:00:00"}}},
        })
        write(pipe / "ch_bob_v002-stable_001.stablemeta", {
            "file": "ch_bob_v002-stable_001.blend", "created_at": "2026-10-05T10:00:00",
            "created_from": "ch_bob_v002.blend",
            "departments_validated": {"modeling": True, "shading": True},
            "approvals": {"shading": {"prod": {"by": "ana", "at": "2026-10-05T11:00:00"}}},
            "approvals_previous": {"modeling": {"prod": {
                "by": "ana", "at": "2026-10-02T11:00:00", "file": "ch_bob_v001-stable_001.blend"}}},
        })
        # Worked on shading only between the two stables.
        write(pipe / "ch_bob_v002.wipmeta", {
            "file": "ch_bob_v002.blend", "edited_at": "2026-10-04T10:00:00",
            "departments_worked": {"s1": ["shading"]},
        })

        plan = migration.plan_migration(root)
        assert plan["owners"] == 1, plan
        changes = {Path(f["path"]).name: f["changes"] for f in plan["files"]}
        assert "entry departments" in changes["tracking.json"], changes
        for name in ("ch_bob_v001-stable_001.stablemeta", "ch_bob_v002-stable_001.stablemeta"):
            assert "stable: departments started" in changes[name], changes
            assert "stable: validations carried" in changes[name], changes
            assert "dates with their offset" in changes[name], changes
            assert "stable: departments_done" in changes[name], changes
        assert changes["ch_bob_v002.wipmeta"] == ["sessions with their date", "dates with their offset"], changes

        result = migration.apply_migration(root, plan)
        assert not result["errors"] and result["written"] == len(plan["files"]), result
        backup = Path(result["backup"])
        assert (backup / "assets/ch/ch_bob/.pipeline/tracking.json").is_file()
        old = json.loads((backup / "assets/ch/ch_bob/.pipeline/tracking.json").read_text())
        assert old["entries"][0]["department"] == "modeling"  # the copy as it was

        tracking = json.loads((pipe / "tracking.json").read_text())
        e1, e2 = tracking["entries"]
        assert e1["departments"] == ["modeling"] and "department" not in e1, e1
        assert e1["created_at"][19:] and e2["created_at"] == "2026-10-01T11:00:00+02:00", tracking
        s1 = json.loads((pipe / "ch_bob_v001-stable_001.stablemeta").read_text())
        s2 = json.loads((pipe / "ch_bob_v002-stable_001.stablemeta").read_text())
        # Renamed (2.0), read as found before: the started departments above
        # came from departments_validated.
        assert s1["departments_done"] == {"modeling": True} and "departments_validated" not in s1, s1
        assert s2["departments_done"] == {"modeling": True, "shading": True} and "departments_validated" not in s2, s2
        assert s1["departments_started"] == ["modeling"], s1
        assert s2["departments_started"] == ["modeling", "shading"], s2
        assert s2["departments_worked"] == ["shading"], s2
        assert s1["approvals_carried"] is True and s2["approvals_carried"] is True
        # Modeling not worked since v001-stable: its validation carried.
        carried = s2["approvals"]["modeling"]["prod"]
        assert carried["carried_from"] == "ch_bob_v001-stable_001.blend" and carried["by"] == "ana", s2
        assert core.parse_iso(s1["created_at"]).utcoffset() is not None
        wip = json.loads((pipe / "ch_bob_v002.wipmeta").read_text())
        session = wip["departments_worked"]["s1"]
        assert session["departments"] == ["shading"] and session["saved_at"] == wip["edited_at"], wip

        again = migration.plan_migration(root)
        assert again["files"] == [], again["files"]

        # Both names on one stable (validated by a build reading the new
        # one before the project was migrated): the new one wins.
        both = {"departments_validated": {"modeling": True, "shading": False}, "departments_done": {"shading": True}}
        assert migration._migrate_done(both)
        assert both == {"departments_done": {"modeling": True, "shading": True}}, both
        assert not migration._migrate_done(both)
        assert migration.migration_done({"data_migrations": {"2.0": {}}})
        assert not migration.migration_done({"data_migrations": {"1.2": {}}})  # a 2.0 build's earlier run: offered again
    print("OK: migration")


if __name__ == "__main__":
    main()
