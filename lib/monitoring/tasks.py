"""Work the live page started that runs on after its answer (a push of the
rushes...), said in its footer: started, under way, done or failed. Kept a
while once ended (KEEP_SECONDS), then forgotten. Update links has its own
jobs (lib/relink.py states()), merged in by the page's data (live.py).
Main thread and the push's own timer only: plain dicts. Blender's project
panel says what runs too (running(): Clean old renders, Migrate old data,
the pushes, Update links)."""

import itertools
import time

KEEP_SECONDS = 600
_count = itertools.count(1)
_tasks: dict[int, dict] = {}


# Blender's own words for each kind (the project panel's line while it runs; the page has its own).
WORDS = {"rushes": "Pushing rushes", "relink": "Updating links", "clean": "Cleaning old renders",
         "clean-look": "Looking at old renders", "migration": "Reading old data"}


def start(kind: str, label: str) -> int:
    """A task under way: its id, for end()."""
    tid = next(_count)
    _tasks[tid] = {"kind": kind, "label": label, "state": "running", "message": "", "at": time.time(), "since": time.time()}
    kick()
    return tid


def end(tid: int, ok: bool, message: str = "") -> None:
    t = _tasks.get(tid)
    if t:
        t.update(state="done" if ok else "failed", message=message, at=time.time())


def running() -> list[dict]:
    """What runs now, for Blender's project panel: [{"text", "seconds"}] -- this
    module's tasks and Update links' jobs (lib/relink.py)."""
    clock = time.time()
    out = [
        {"text": " · ".join(x for x in (WORDS.get(t["kind"], t["kind"]), t["label"]) if x), "seconds": clock - t["since"]}
        for _, t in sorted(_tasks.items())
        if t["state"] == "running"
    ]
    try:
        from .. import relink

        out += [{"text": f"{WORDS['relink']} · {j.get('file') or k}", "seconds": None}
                for k, j in relink.states().items() if j.get("state") == "running"]
    except Exception:
        pass
    return out


_redrawing = False


def kick() -> None:
    """A task started: the panels drawn again a few times a second while any
    runs (its ring turning, its seconds), once more after the last one ends."""
    global _redrawing
    if _redrawing:
        return
    try:
        import bpy
    except ImportError:
        return
    _redrawing = True

    def tick():
        global _redrawing
        try:
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()
        except Exception:
            pass
        if running():
            return 0.25
        _redrawing = False
        return None

    try:
        bpy.app.timers.register(tick, first_interval=0.1)
    except Exception:
        _redrawing = False


def states() -> list[dict]:
    """The page's: [{"kind", "label", "state", "message", "at"}], oldest first,
    the ended ones of the last KEEP_SECONDS."""
    clock = time.time()
    for tid in [k for k, t in _tasks.items() if t["state"] != "running" and clock - t["at"] > KEEP_SECONDS]:
        del _tasks[tid]
    return [{k: v for k, v in t.items() if k != "since"} for _, t in sorted(_tasks.items())]
