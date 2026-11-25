"""The farm host's own worker and the setups (farm/queue.py scan_queue()):
with other workers, held back from new renders while a job waits for its
setup (they get set-up jobs); alone, it renders a set-up job first -- the
first video sooner -- but never beside a setup running -- without Blender.

    python3 tests/test_farm_host_alone.py
"""

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

ME = "host-uuid"


def job(job_id, stage, priority=10):
    return Path(f"/q/{job_id}.json"), {
        "job_id": job_id, "priority": priority, "submitted_at": job_id,
        "stage_history": [{"stage": stage}],
    }


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    q = importlib.import_module(f"{pkg.__name__}.farm.queue")
    setup = importlib.import_module(f"{pkg.__name__}.farm.setup")

    calls = []
    state = {"jobs": [], "workers": {}, "slot": False}
    q.get_machine_id = lambda: ME
    q.ensure_preset_pace = lambda root: None
    q.ConfigCache.get = classmethod(lambda cls: {})
    q.ConfigCache.get_path = classmethod(lambda cls, name: Path("/q"))
    q.read_active_jobs = lambda d: list(state["jobs"])
    q.this_instance_is_worker = lambda: True
    q.scan_workers = lambda: state["workers"]
    q.idle_machines = lambda: {ME: {"status": "idle"}}
    q.local_slot_busy = lambda: state["slot"]
    q.local_render_running = lambda: False
    q.machines_for = lambda data, idle, with_left=False: list(idle)
    def dispatch(path, idle, root):
        # As the real one: the machines it sends taken out of idle.
        calls.append(("render", path.stem, sorted(idle)))
        idle.clear()

    q.render_dispatch = dispatch
    setup.run_render_setup = lambda job_id, config: calls.append(("setup", job_id))

    def tick():
        calls.clear()
        q.scan_queue(Path("/proj"))
        return list(calls)

    me_worker = {ME: {"farm_protocol": q.FARM_PROTOCOL}}
    other = {"other-uuid": {"farm_protocol": q.FARM_PROTOCOL}}

    # Alone: A set up, B waiting for its setup -> A rendered on the host now,
    # B's setup once it's free (not beside the render).
    state.update(jobs=[job("a", "setup_finished", 20), job("b", "queued")], workers=dict(me_worker))
    assert tick() == [("render", "a", [ME])], calls
    # Alone, the host rendering (not idle): the setup waits.
    q.idle_machines = lambda: {}
    state.update(jobs=[job("a", "render_start", 20), job("b", "queued")])
    assert tick() == [], calls
    q.idle_machines = lambda: {ME: {"status": "idle"}}
    # Alone, a setup running: no render beside it.
    state.update(jobs=[job("a", "setup_finished", 20), job("b", "setup_start")])
    assert tick() == [], calls
    # Alone, B's setup started this tick (higher priority): A waits for the next.
    state.update(jobs=[job("b", "queued", 30), job("a", "setup_finished", 20)])
    assert tick() == [("setup", "b")], calls

    # Another worker: the host held back while a setup waits (the old rule).
    state.update(jobs=[job("a", "setup_finished", 20), job("b", "queued")], workers=me_worker | other)
    out = tick()
    assert ("render", "a", [ME]) not in out and ("setup", "b") in out, out
    # A machine kept for its own renders, or on another protocol, isn't one.
    state["workers"] = me_worker | {"x": {"farm_protocol": q.FARM_PROTOCOL, "local_only": True}, "y": {"farm_protocol": 1}}
    assert ("render", "a", [ME]) in tick(), calls

    print("farm host alone: ok")


if __name__ == "__main__":
    main()
