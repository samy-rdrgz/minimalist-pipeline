"""The live page's actions (lib/monitoring/live.py): a pending job removed
from the Farm tab (the page doesn't say it's pending: its file in
incomings/ does -- before, the removal always failed); a job id that
isn't one refused before it names a path; a sequence's preview refused
for a name that climbs out of shots/; an action that raises answered all
the same (before, its request waited the whole minute); what Blender
never turned to answered when the page stops, not applied on its next start.

    python3 tests/test_live_actions.py
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
    live = importlib.import_module(f"{pkg.__name__}.lib.monitoring.live")
    config = importlib.import_module(f"{pkg.__name__}.lib.config")
    core = importlib.import_module(f"{pkg.__name__}.lib.core")
    core.get_machine_id = lambda *a, **k: "test-machine"
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        config.get_active_project_root = lambda: root
        live.get_active_project_root = lambda: root
        config.ConfigCache._path_cache.clear()
        incomings = config.ConfigCache.get_path("farm_incomings")
        incomings.mkdir(parents=True)
        (incomings / "job_abc123.json").write_text(json.dumps({"job_id": "job_abc123"}), encoding="utf-8")

        # Removed while pending: the page sends no "value".
        out = live._farm_action({"action": "remove", "job_id": "job_abc123"})
        assert out == {"ok": True}, out
        assert not (incomings / "job_abc123.json").exists()

        # Not a job's id: refused before any path is made of it.
        (root / "config" / "project_config.json").write_text("{}", encoding="utf-8")
        for bad in ("../../project_config", "job_../x", "job_a/b", "x"):
            out = live._farm_action({"action": "priority", "job_id": bad, "value": 5})
            assert out["ok"] is False and "no job" in out["error"], (bad, out)
        assert (root / "config" / "project_config.json").read_text() == "{}"

        # A priority that isn't a number: said, not raised.
        actives = config.ConfigCache.get_path("farm_actives")
        actives.mkdir(parents=True)
        (actives / "job_def456.json").write_text("{}", encoding="utf-8")
        out = live._farm_action({"action": "priority", "job_id": "job_def456", "value": None})
        assert out["ok"] is False, out

        # A preview of "..": not a sequence.
        (root / "shots" / "sq010").mkdir(parents=True)
        for bad in ("..", ".", "sq010/..", "..\\sq010", ""):
            out = live._farm_submit("preview", {"sequence": bad})
            assert out["ok"] is False and "no sequence" in out["error"], (bad, out)

        # An action that raises: answered, the turn's other actions applied.
        sh = live._Shared(root, "token")
        live._shared = sh
        boom, after = live._Pending({}, "open"), live._Pending({}, "play")
        live._open = lambda raw: 1 / 0
        live._play = lambda raw: {"ok": True}
        live._actions.put(boom)
        live._actions.put(after)
        try:
            live._turn(sh)
        except Exception:
            pass  # later steps of the turn need more of Blender than the fake has
        assert boom.done.is_set() and boom.result["ok"] is False, boom.result
        assert after.done.is_set() and after.result == {"ok": True}, after.result

        # Stopped with an action never turned to: answered, then gone.
        class Server:
            def shutdown(self):
                pass

            def server_close(self):
                pass

        stale = live._Pending({"action": "cancel", "job_id": "job_def456"}, "farm")
        live._actions.put(stale)
        live._server = Server()
        live._shared = sh
        assert live.stop()
        assert stale.done.is_set() and stale.result["ok"] is False, stale.result
        assert live._actions.empty()
    print("OK: live page actions")


if __name__ == "__main__":
    main()
