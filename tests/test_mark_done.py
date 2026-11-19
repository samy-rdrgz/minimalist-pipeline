"""A department marked done on the latest stable, no new version
(lib/tracking.py set_department_done(), the review's "done" action): done
written in place (both keys, 2.0 and 1.x), started kept, undone taking its
validations there with it; nothing written when already as asked; refused
without a stable. And the review action read back.

    python3 tests/test_mark_done.py
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
    config = importlib.import_module(f"{pkg.__name__}.lib.config")
    tracking = importlib.import_module(f"{pkg.__name__}.lib.tracking")
    review_import = importlib.import_module(f"{pkg.__name__}.lib.review_import")
    errors = importlib.import_module(f"{pkg.__name__}.lib.errors")
    core = importlib.import_module(f"{pkg.__name__}.lib.core")
    core.get_machine_id = lambda *a, **k: "test-machine"  # a MagicMock isn't JSON
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "proj"
        (root / "config").mkdir(parents=True)
        (root / "config" / "project_config.json").write_text(json.dumps({
            "naming": {"version": {"prefix": "v", "digits": 3}},
            "structure": {"asset_prefixes": ["ch"], "library_prefixes": []},
            "tags": ["stable"],
        }), encoding="utf-8")
        config.set_daemon_active_project_root(root)
        config.ConfigCache.invalidate()
        owner = root / "assets" / "ch_bob"
        (owner / ".pipeline").mkdir(parents=True)
        blend = owner / "ch_bob_v002.blend"

        try:
            tracking.set_department_done(blend, "rig", True)
            raise AssertionError("no stable: refused")
        except errors.PipelineError:
            pass

        meta = owner / ".pipeline" / "v001-stable.stablemeta"
        meta.write_text(json.dumps({
            "file": str(owner / "ch_bob_v001-stable.blend"), "created_at": "2026-11-01T10:00:00+01:00",
            "departments_done": {"modeling": True}, "departments_started": ["modeling"],
            "approvals": {"modeling": {"prod": {"by": "léa", "at": "x"}}},
        }), encoding="utf-8")
        read = lambda: json.loads(meta.read_text(encoding="utf-8"))  # noqa: E731

        assert tracking.set_department_done(blend, "rig", True)
        m = read()
        assert m["departments_done"] == {"modeling": True, "rig": True}, m
        assert m["departments_validated"] == m["departments_done"], m  # the 1.x key beside it
        assert m["departments_started"] == ["modeling", "rig"], m
        assert not tracking.set_department_done(blend, "rig", True)  # as asked already

        assert tracking.set_department_done(blend, "modeling", False)
        m = read()
        assert m["departments_done"]["modeling"] is False and "modeling" not in m.get("approvals", {}), m
        assert "modeling" in m["departments_started"], m

        # The review's action, as the page writes it.
        a = review_import._action({"type": "done", "file": "ch_bob", "department": "Rig", "done": True})
        assert a == {"type": "done", "file": "ch_bob", "department": "rig", "done": True}, a
        a = review_import._action({"type": "done", "file": "ch_bob", "department": "rig", "done": False})
        assert a["done"] is False, a
        assert review_import._action({"type": "done", "file": "ch_bob"}) is None

        # A note's words changed by the page (the review's "edit"), its author kept.
        (owner / ".pipeline" / "tracking.json").write_text(json.dumps({"entries": [
            {"id": "a1b2c", "type": "note", "text": "too dark", "author": "léa", "departments": []}]}), encoding="utf-8")
        assert tracking.set_entry_text(blend, "a1b2c", " too dark, the left side ", "léa")
        e = json.loads((owner / ".pipeline" / "tracking.json").read_text(encoding="utf-8"))["entries"][0]
        assert e["text"] == "too dark, the left side" and e["author"] == "léa" and e["edited_by"] == "léa", e
        assert not tracking.set_entry_text(blend, "a1b2c", "too dark, the left side", "léa")
        assert review_import._action({"type": "edit", "file": "ch_bob", "id": "a1b2c", "text": ""}) is None
        assert review_import._action({"type": "delete", "file": "ch_bob", "id": "a1b2c"}) == {"type": "delete", "file": "ch_bob", "id": "a1b2c"}
    print("ok")


if __name__ == "__main__":
    main()
