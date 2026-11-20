"""Render here (farm/local.py): a farm job of one machine. Written straight
into actives/ ("local": its machine, only it assigned), never the farm's
own job id; the farm host leaves another machine's alone, the machine's
own pass moves only its own; a machine kept for its renders ("local_only")
gets no farm render, and nobody else's; a viewport render, one chunk, its
history tagged and kept out of the presets' pace.

    python3 tests/test_local_render.py
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
    lib = importlib.import_module(f"{pkg.__name__}.lib")
    monitor = importlib.import_module(f"{pkg.__name__}.farm.monitor")
    queue = importlib.import_module(f"{pkg.__name__}.farm.queue")
    dispatch = importlib.import_module(f"{pkg.__name__}.farm.dispatch")
    workers = importlib.import_module(f"{pkg.__name__}.farm.workers")
    local = importlib.import_module(f"{pkg.__name__}.farm.local")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        actives = root / "actives"
        incoming = root / "incoming"
        paths = {"farm_actives": actives, "farm_incomings": incoming}
        lib.ConfigCache.get_path = classmethod(lambda cls, k: paths[k])
        me, other = "aaaa1111bbbb", "cccc2222dddd"
        for m in (monitor, queue, local, workers):
            m.get_machine_id = lambda: me
        for name in ("core", "session"):
            importlib.import_module(f"{pkg.__name__}.lib.{name}").get_machine_id = lambda context=None: "testmachine0"
        monitor.to_relative = local.to_relative = lambda p: str(p)
        monitor.render_department = lambda f, p: ""
        blend = "shots/sq010/sq010_sh010/sq010_sh010_v003.blend"

        # Written straight into actives/, queued, this machine only.
        job_id = monitor.job_request(blend, user="lea", prerender_script="fast", local=me)
        data = json.loads((actives / f"{job_id}.json").read_text())
        assert data["local"] == me and data["assigned_machines"] == [me], data
        assert data["stage_history"][-1]["stage"] == "queued" and not list(incoming.glob("*")), data
        # Never the farm's id, nor a viewport render's.
        farm_name = monitor.job_request(blend, user="lea", prerender_script="fast")
        vp = monitor.job_request(blend, user="lea", prerender_script="fast", local=me, viewport=True)
        assert len({job_id, Path(farm_name).stem, vp}) == 3
        assert json.loads((actives / f"{vp}.json").read_text())["viewport"] is True
        # The same render here under way: refused.
        try:
            monitor.job_request(blend, user="lea", prerender_script="fast", local=me)
            raise AssertionError("a second render here of the same file went through")
        except lib.PipelineError:
            pass
        assert {d["job_id"] for d in local.local_jobs_in_flight(me)} == {job_id, vp}

        # Another machine's render here: the host leaves it, its own pass doesn't.
        theirs = monitor.job_request("shots/sq010/sq010_sh020/sq010_sh020_v001.blend", user="tom", local=other)
        for name in (job_id, vp, theirs):
            p = actives / f"{name}.json"
            j = json.loads(p.read_text())
            j["stage_history"].append({"stage": "split_finished", "at": "2026-11-20T10:00:00+01:00"})
            p.write_text(json.dumps(j))
        queue.idle_machines = lambda: {}
        queue.ensure_preset_pace = lambda r: None
        queue.construct_split_history = lambda data: None
        queue.discard_job_log = lambda i: None
        queue.mark_stage = lambda path, stage: _mark(path, stage)

        def _mark(path, stage):
            j = json.loads(Path(path).read_text())
            j["stage_history"].append({"stage": stage, "at": "x"})
            Path(path).write_text(json.dumps(j))

        def stage(name):
            return json.loads((actives / f"{name}.json").read_text())["stage_history"][-1]["stage"]

        queue.scan_queue(root, local=True)  # this machine's pass: its own only
        assert stage(job_id) == "archived" and stage(vp) == "archived" and stage(theirs) == "split_finished"
        for m in (monitor, queue, local, workers):
            m.get_machine_id = lambda: "eeee3333ffff"  # the farm host, elsewhere
        queue.scan_queue(root)
        assert stage(theirs) == "split_finished", "the host moved another machine's render here on"

        # Kept for its own renders: no host sends it a farm render; its own, yes.
        idle = {me: {"local_only": True}, other: {}}
        assert dispatch.machines_for({}, idle) == [other]
        assert dispatch.machines_for({"local": me, "assigned_machines": [me]}, idle) == [me]
        workers.scan_requests = lambda kind: {}
        workers.scan_workers = lambda: {me: {"status": "idle", "local_only": True, "farm_protocol": workers.FARM_PROTOCOL},
                                        other: {"status": "idle", "farm_protocol": workers.FARM_PROTOCOL}}
        workers.get_machine_id = lambda: "eeee3333ffff"
        assert set(workers.idle_machines()) == {other}  # another host: never it
        workers.get_machine_id = lambda: me
        assert set(workers.idle_machines()) == {me, other}  # its own pass: itself

        # History: tagged; a viewport render's pace kept out.
        entries, paces = [], []
        queue.append_render_history = lambda f, e: entries.append(e)
        queue.note_preset_pace = lambda e: paces.append(e)
        base = {"job_id": "j", "user": "lea", "render_mode": "all", "filepath": blend,
                "stage_history": [{"stage": "queued", "at": "2026-11-20T10:00:00+01:00"}]}
        queue.construct_history(base | {"local": me, "viewport": True}, "finished")
        queue.construct_history(base | {"local": me}, "finished")
        queue.construct_history(base, "finished")
        assert [e.get("tags") for e in entries] == [["local", "viewport"], ["local"], None], entries
        assert len(paces) == 2
        loop = importlib.import_module(f"{pkg.__name__}.farm.loop")
        h = [{"status": "finished", "seconds_per_frame": 1.0, "prerender_script": "fast", "tags": ["local", "viewport"]},
             {"status": "finished", "seconds_per_frame": 9.0, "prerender_script": "fast", "tags": ["local"]}]
        assert loop.history_pace(h, "fast")["seconds_per_frame"] == 9.0
    print("OK: local render")


if __name__ == "__main__":
    main()
