"""Our reader threads, held still while the main thread runs a window
operator: bpy.ops releases Python's GIL for the operator's length, and
window_new() & co. crashed Blender (EXCEPTION_ACCESS_VIOLATION in
python311.dll, on the thread) with a project scan running alongside. See
NOTES.md, "Monitoring crash: a thread during window_new()"."""

import threading
import time
from contextlib import contextmanager

_cond = threading.Condition()
_active = 0  # reader threads inside background_work()
_parked = 0  # of those, waiting in checkpoint()
_pauses = 0  # threads_paused() depth (bring_monitoring_to_front() nests one)

# How long the main thread waits for the readers to stop -- one listing on
# a slow share. Past it, the operator runs anyway: Blender never freezes.
PAUSE_TIMEOUT = 2.0


def _on_main_thread() -> bool:
    return threading.current_thread() is threading.main_thread()


@contextmanager
def background_work():
    """Around a reader thread's whole run: counted, so threads_paused()
    knows whom to wait for. Stops at a pause before it starts."""
    global _active
    with _cond:
        _active += 1
    try:
        checkpoint()
        yield
    finally:
        with _cond:
            _active -= 1
            _cond.notify_all()


def checkpoint() -> None:
    """In a reader's loops (a folder listed, a file read): wait here while
    the main thread runs a window operator. No-op on the main thread -- the
    one pausing -- and when nothing is paused (one read, no lock)."""
    global _parked
    if not _pauses or _on_main_thread():
        return
    with _cond:
        _parked += 1
        _cond.notify_all()
        while _pauses:
            _cond.wait()
        _parked -= 1


@contextmanager
def threads_paused(timeout: float = PAUSE_TIMEOUT):
    """Main thread, around a bpy.ops call that opens, closes or reloads
    windows: every reader thread parked at a checkpoint (or done) first,
    for timeout at most."""
    global _pauses
    with _cond:
        _pauses += 1
        deadline = time.monotonic() + timeout
        while _parked < _active:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            _cond.wait(left)
    try:
        yield
    finally:
        with _cond:
            _pauses -= 1
            _cond.notify_all()
