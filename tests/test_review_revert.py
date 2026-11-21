"""A review's import undone (lib/monitoring/review_revert.py): the files it
may touch read before, what differs after written to a .revert.json, put
back where nothing changed since -- a note added taken out, a value set
back, a deleted note back; one edited since, or a value changed again, left.

    python3 tests/test_review_revert.py
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
    rr = importlib.import_module(f"{pkg.__name__}.lib.monitoring.review_revert")
    ri = importlib.import_module(f"{pkg.__name__}.lib.monitoring.review_import")
    tracking = importlib.import_module(f"{pkg.__name__}.lib.monitoring.tracking")
    errors = importlib.import_module(f"{pkg.__name__}.lib.errors")

    with tempfile.TemporaryDirectory() as d:
        owner = Path(d) / "assets" / "ch_bob"
        pipe = owner / ".pipeline"
        pipe.mkdir(parents=True)
        blend = owner / "ch_bob_v002.blend"
        ri._review_file = lambda name: blend  # the project's lookup, without a project
        rr_tracking = pipe / "tracking.json"
        meta = pipe / "v001-stable.stablemeta"
        old_note = {"id": "aaaa1", "type": "note", "text": "keep me", "author": "léa"}
        gone = {"id": "bbbb2", "type": "rtk", "text": "deleted by the review", "author": "sam"}
        rr_tracking.write_text(json.dumps({"entries": [old_note, gone], "assignees": {"rig": ["léa"]}}), encoding="utf-8")
        meta.write_text(json.dumps({"departments_done": {"rig": False}, "approvals": {}}), encoding="utf-8")
        review = {"author": "sam", "role": "prod", "actions": [{"type": "note", "file": "ch_bob"}]}

        before = rr.state_before(review)
        # The import's effects.
        t = json.loads(rr_tracking.read_text(encoding="utf-8"))
        t["entries"] = [old_note, {"id": "cccc3", "type": "rtk", "text": "new one", "author": "sam"},
                        {"id": "dddd4", "type": "note", "text": "new two", "author": "sam"}]
        t["assignees"]["rig"] = ["sam"]
        rr_tracking.write_text(json.dumps(t), encoding="utf-8")
        meta.write_text(json.dumps({"departments_done": {"rig": True}, "approvals": {"rig": {"prod": {"by": "sam"}}}}), encoding="utf-8")
        changes = rr.changes_since(before)
        kept = Path(d) / "review_sam.json"
        undo = rr.write_revert(kept, review, changes)
        assert undo.name == "review_sam.revert.json", undo
        s = rr.summary(rr.read_revert(undo))
        assert (s["entries_added"], s["entries_removed"], s["values"]) == (2, 1, 3), s

        # Since: dddd4 edited by someone, so it stays.
        t = json.loads(rr_tracking.read_text(encoding="utf-8"))
        t["entries"][2]["text"] = "new two, edited"
        rr_tracking.write_text(json.dumps(t), encoding="utf-8")

        out = rr.apply_revert(undo, "léa")
        t = json.loads(rr_tracking.read_text(encoding="utf-8"))
        ids = [e["id"] for e in t["entries"]]
        assert "cccc3" not in ids and "dddd4" in ids and "bbbb2" in ids and "aaaa1" in ids, ids
        assert t["assignees"]["rig"] == ["léa"], t
        m = json.loads(meta.read_text(encoding="utf-8"))
        assert m["departments_done"]["rig"] is False and "rig" not in m["approvals"], m
        assert len(out["skipped"]) == 1 and out["put_back"] == 5, out
        try:
            rr.apply_revert(undo, "léa")
            raise AssertionError("reverted twice")
        except errors.PipelineError:
            pass
        assert tracking  # imported fine from its new place
    print("OK: review revert")


if __name__ == "__main__":
    main()
