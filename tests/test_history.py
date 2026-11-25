"""A folder's history (lib/monitoring/history.py): its versions oldest
first -- made from which, saved last by whom, their sessions (a 1.x's
under the old name too), a stable's done departments, validations and
conflict -- and its renders latest first, a split job's line left out.
Who has which file open now (the live page's presence()).

    python3 tests/test_history.py
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
    history = importlib.import_module(f"{pkg.__name__}.lib.monitoring.history")
    with tempfile.TemporaryDirectory() as d:
        owner = Path(d) / "ch_bob"
        pipe = owner / ".pipeline"
        pipe.mkdir(parents=True)

        def write(name, data):
            (pipe / name).write_text(json.dumps(data), encoding="utf-8")

        write("ch_bob_v002.wipmeta", {
            "file": "ch_bob_v002.blend", "created_at": "2026-10-04T10:00:00+02:00", "created_from": "ch_bob_v001-stable.blend",
            "edited_at": "2026-10-05T18:00:00+02:00", "edited_by": "tom",
            "departments_worked": {"1_m": {"departments": ["rig"], "saved_at": "2026-10-05T18:00:00+02:00", "by": "tom"}},
        })
        write("ch_bob_v001.wipmeta", {
            "file": "ch_bob_v001.blend", "created_at": "2026-10-01T10:00:00+02:00", "edited_by": "lea",
            "sessions": {"1_m": {"departments": ["modeling"], "saved_at": "2026-10-02T18:00:00+02:00", "by": "lea"}},
        })
        write("ch_bob_v001-stable.stablemeta", {
            "file": "ch_bob_v001-stable.blend", "created_at": "2026-10-03T10:00:00+02:00", "created_from": "ch_bob_v001.blend",
            "departments_validated": {"modeling": True, "rig": False},
            "approvals": {"modeling": {"prod": {"by": "ana", "at": "2026-10-03T12:00:00+02:00"}}},
            "conflict_warning": "v000 worked apart", "note": "rig v2, cam rescaled",
        })
        write("render_history.json", {"entries": [
            {"completed_at": "2026-10-03T12:00:00+02:00", "status": "finished", "department": "modeling",
             "prerender_script": "modeling_default", "frame_range_rendered": [1, 10], "user": "lea",
             "duration_seconds": 120, "machines_used": ["a", "b"], "output_path": "/p/renders/assets/ch/ch_bob/v001-stable_001/ch_bob_v001-stable.#####"},
            {"completed_at": "2026-10-03T12:00:00+02:00", "status": "split"},
            {"completed_at": "2026-10-05T12:00:00+02:00", "status": "failed", "user": "tom", "output_path": ""},
        ]})
        h = history.file_history(owner)
        files = [v["file"] for v in h["versions"]]
        assert files == ["ch_bob_v001", "ch_bob_v001-stable", "ch_bob_v002"], files
        v1, st, v2 = h["versions"]
        assert v1["sessions"] == [{"by": "lea", "at": "2026-10-02T18:00:00+02:00", "departments": ["modeling"]}], v1
        assert v2["from"] == "ch_bob_v001-stable" and v2["sessions"][0]["departments"] == ["rig"], v2  # a 1.x's name read
        assert v2["saved_by"] == "tom" and not v2["stable"], v2
        assert st["stable"] and st["done"] == ["modeling"] and st["approvals"] == {"modeling": ["prod"]}, st
        assert st["conflict"] == "v000 worked apart", st
        assert st["note"] == "rig v2, cam rescaled" and v1["note"] == "", (st, v1)  # a version's note, none said
        assert [r["status"] for r in h["renders"]] == ["failed", "finished"], h["renders"]
        r = h["renders"][1]
        assert r["folder"] == "v001-stable_001" and r["machines"] == 2 and r["preset"] == "modeling_default", r

    # Who has which file open (live.presence()): a session pinged lately,
    # its file's name; a stale one (crashed, closed) left out.
    import datetime as dt

    live = importlib.import_module(f"{pkg.__name__}.lib.monitoring.live")
    with tempfile.TemporaryDirectory() as d:
        sessions = Path(d) / "config" / ".sessions"
        sessions.mkdir(parents=True)
        fresh = dt.datetime.now().astimezone().isoformat()
        (sessions / ".session_1.json").write_text(json.dumps({
            "user": "lea", "machine": "a1b2c3d4", "uuid": "a1b2c3d4-x", "filepath": "S:\\proj\\assets\\ch\\ch_bob\\ch_bob_v002.blend",
            "last_ping": fresh, "saved": True}), encoding="utf-8")
        (sessions / ".session_2.json").write_text(json.dumps({
            "user": "tom", "machine": "99ff00aa", "filepath": "/p/x_v001.blend", "last_ping": "2026-01-01T10:00:00+01:00"}), encoding="utf-8")
        assert live.presence(Path(d)) == [{"user": "lea", "machine": "a1b2c3d4", "uuid": "a1b2c3d4-x", "file": "ch_bob_v002", "saved": True}]

    # Its shot open in another Blender (session.open_elsewhere()): any version,
    # another machine's mount; this Blender's own and a stale one left out.
    session = importlib.import_module(f"{pkg.__name__}.lib.session")
    with tempfile.TemporaryDirectory() as d:
        sessions = Path(d) / "config" / ".sessions"
        sessions.mkdir(parents=True)
        fresh = dt.datetime.now().astimezone().isoformat()
        for i, (user, pid, uuid, fp, ping) in enumerate([
            ("lea", 11, "aaaa1111", "S:\\proj\\assets\\ch\\ch_bob\\ch_bob_v003.blend", fresh),
            ("me", 22, "bbbb2222", "/p/assets/ch/ch_bob/ch_bob_v002.blend", fresh),  # this Blender
            ("tom", 33, "cccc3333", "/p/assets/ch/ch_bob/ch_bob_v001.blend", "2026-01-01T10:00:00+01:00"),
            ("ana", 44, "dddd4444", "/p/assets/ch/ch_ann/ch_ann_v001.blend", fresh),
        ]):
            (sessions / f".session_{i}.json").write_text(json.dumps({
                "user": user, "pid": pid, "uuid": uuid, "machine": uuid[:4], "filepath": fp, "last_ping": ping}), encoding="utf-8")
        got = session.open_elsewhere("/mnt/x/assets/ch/ch_bob/ch_bob_v002.blend", root=Path(d), pid=22, machine="bbbb2222")
        assert got == [{"user": "lea", "machine": "aaaa", "file": "ch_bob_v003.blend"}], got
        assert session.elsewhere_text(got) == "lea (aaaa, ch_bob_v003.blend)"
    print("OK: history")


if __name__ == "__main__":
    main()
