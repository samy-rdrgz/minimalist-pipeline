"""Work the live page started that runs on after its answer (a push of the
rushes...), said in its footer: started, under way, done or failed. Kept a
while once ended (KEEP_SECONDS), then forgotten. Update links has its own
jobs (lib/relink.py states()), merged in by the page's data (live.py).
Main thread and the push's own timer only: plain dicts."""

import itertools
import time

KEEP_SECONDS = 600
_count = itertools.count(1)
_tasks: dict[int, dict] = {}


def start(kind: str, label: str) -> int:
    """A task under way: its id, for end()."""
    tid = next(_count)
    _tasks[tid] = {"kind": kind, "label": label, "state": "running", "message": "", "at": time.time()}
    return tid


def end(tid: int, ok: bool, message: str = "") -> None:
    t = _tasks.get(tid)
    if t:
        t.update(state="done" if ok else "failed", message=message, at=time.time())


def states() -> list[dict]:
    """The page's: [{"kind", "label", "state", "message", "at"}], oldest first,
    the ended ones of the last KEEP_SECONDS."""
    clock = time.time()
    for tid in [k for k, t in _tasks.items() if t["state"] != "running" and clock - t["at"] > KEEP_SECONDS]:
        del _tasks[tid]
    return [dict(t) for _, t in sorted(_tasks.items())]
