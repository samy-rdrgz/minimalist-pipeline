"""The farm loop's timer, one per Blender process: a role started again
after the loop stopped (a worker stopped, then added again, Blender left
open) gets a timer again -- in 1.1.10 it didn't, so the worker never
ticked and never took a job. The monitor stopped and launched again while
the worker kept running: still one timer, not two.

    python3 tests/test_farm_loop.py
"""

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


class Timers:
    """bpy.app.timers, enough of it: the functions registered, ticked by hand."""

    def __init__(self):
        self.fns = []

    def register(self, fn, first_interval=0, persistent=False):
        self.fns.append(fn)

    def unregister(self, fn):
        self.fns.remove(fn)

    def is_registered(self, fn):
        return fn in self.fns

    def tick(self):
        for fn in list(self.fns):
            if fn() is None:
                self.fns.remove(fn)


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    loop = importlib.import_module(f"{pkg.__name__}.farm.loop")
    monitor = importlib.import_module(f"{pkg.__name__}.farm.monitor")
    workers = importlib.import_module(f"{pkg.__name__}.farm.workers")
    timers = Timers()
    loop.bpy.app.timers = timers
    roles = {"monitor": False, "worker": False}
    ticks = []
    monitor.is_blender_monitor = lambda: roles["monitor"]
    monitor.monitor_tick = lambda root: ticks.append("monitor")
    workers.is_blender_worker = lambda: roles["worker"]
    workers.worker_tick = lambda: ticks.append("worker")
    root = Path("/project")

    # A worker, then stopped: the loop ends at its next tick.
    roles["worker"] = True
    loop.register_farm_loop(root)
    timers.tick()
    assert ticks == ["worker"] and len(timers.fns) == 1
    roles["worker"] = False
    timers.tick()
    assert timers.fns == [] and loop.get_running_project() is None

    # Added again, Blender left open: ticking again.
    ticks.clear()
    roles["worker"] = True
    loop.register_farm_loop(root)
    timers.tick()
    assert ticks == ["worker"], "a worker started again never ticked"
    assert loop.get_running_project() == root

    # The monitor stopped and launched again, the worker running: one timer.
    roles["monitor"] = True
    loop.register_farm_loop(root)
    assert len(timers.fns) == 1
    loop.set_running_project(None)  # stop_monitor_loop()
    roles["monitor"] = False
    timers.tick()
    roles["monitor"] = True
    loop.register_farm_loop(root)
    assert len(timers.fns) == 1 and loop.get_running_project() == root
    ticks.clear()
    timers.tick()
    assert ticks == ["monitor", "worker"]

    # Another project: the earlier one's timer replaced, not doubled.
    loop.register_farm_loop(Path("/other"))
    assert len(timers.fns) == 1 and timers.fns[0].args[0] == Path("/other")
    print("ok")


if __name__ == "__main__":
    main()
