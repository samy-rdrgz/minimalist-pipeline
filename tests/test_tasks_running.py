"""Work under way in the background (lib/monitoring/tasks.py): what
Blender's project panel says while it runs, the page's list without its
start time -- without Blender.

    python3 tests/test_tasks_running.py
"""

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    tasks = importlib.import_module(f"{fake_bpy.load().__name__}.lib.monitoring.tasks")
    tasks.kick = lambda: None  # no timers here
    a = tasks.start("clean", "12")
    b = tasks.start("rushes", "sq010")
    texts = [t["text"] for t in tasks.running()]
    assert texts == ["Cleaning old renders · 12", "Pushing rushes · sq010"], texts
    assert all(t["seconds"] >= 0 for t in tasks.running())
    tasks.end(a, True, "done")
    assert [t["text"] for t in tasks.running()] == ["Pushing rushes · sq010"]
    tasks.end(b, False, "refused")
    assert tasks.running() == []
    states = tasks.states()
    assert [s["state"] for s in states] == ["done", "failed"] and all("since" not in s for s in states), states
    print("tasks running: ok")


if __name__ == "__main__":
    main()
