"""A farm job's machines for the live page's detail (lib/monitoring/live.py
_per_machine()): each one's pace and the frame it's on -- without Blender.

    python3 tests/test_live_job_pace.py
"""

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    live = importlib.import_module(f"{fake_bpy.load().__name__}.lib.monitoring.live")

    cache = {
        "workers": {"a": {"user": "sam", "machine": "PC-01"}, "b": {"machine": "PC-02"}},
        "claims": {"j1": {"0": {"machine": "a", "frame_in_progress": 905}, "1": {"machine": "c", "frame_in_progress": None}}},
    }
    job = {"job_id": "j1", "stage": "render_start", "machines": ["a", "b"], "machine_seconds": {"a": 8.2, "b": 11.7}}
    assert live._per_machine(cache, job) == [
        {"name": "sam (PC-01)", "pace": 8.2, "frame": 905},
        {"name": "PC-02", "pace": 11.7, "frame": None},
        {"name": "c", "pace": None, "frame": None},
    ], live._per_machine(cache, job)
    # Not rendering any more: its paces, no frame in progress.
    done = dict(job, stage="finished")
    assert [m["frame"] for m in live._per_machine(cache, done)] == [None, None]
    assert live._per_machine(cache, {"job_id": "j2", "stage": "queued"}) == []
    print("live job pace: ok")


if __name__ == "__main__":
    main()
