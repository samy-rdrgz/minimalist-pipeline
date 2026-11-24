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


class Worker:
    """One job at a time on a thread kept alive between jobs. start() only
    hands the job over: creating a thread makes the caller wait until it
    runs, tens of ms on Blender's thread with Cycles on every core (the live
    page's profile, a farm read every 2 s). Idle IDLE_EXIT seconds, the
    thread ends (an add-on reloaded leaves none behind); the next start()
    makes another. The job runs inside background_work() (counted: false, a
    job that never reaches a checkpoint() -- not waited for by
    threads_paused()). The caller polls take() (a bpy.app.timers tick)."""

    IDLE_EXIT = 30.0

    def __init__(self, name: str, counted: bool = True):
        self.name, self.counted = name, counted
        self._cond = threading.Condition()
        self._job = None  # (fn, args), handed over, not yet picked up
        self._running = False
        self._thread = None
        self._result = None
        self.started_at = 0.0

    def busy(self) -> bool:
        with self._cond:
            return self._job is not None or self._running

    def start(self, fn, *args) -> None:
        with self._cond:
            self._result = None
            self.started_at = time.monotonic()
            self._job = (fn, args)
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, daemon=True, name=self.name)
                self._thread.start()  # once in a while: the thread then stays
            self._cond.notify_all()

    def take(self):
        """("ok", value) / ("error", exc) once the job finished, else None."""
        with self._cond:
            if self._job is not None or self._running or self._result is None:
                return None
            result, self._result = self._result, None
            return result

    def wait(self, timeout: float | None = None) -> bool:
        """Until the job handed over is done (tests). False at the timeout."""
        with self._cond:
            return self._cond.wait_for(lambda: self._job is None and not self._running, timeout)

    def _loop(self) -> None:
        while True:
            with self._cond:
                if self._job is None and not self._cond.wait_for(lambda: self._job is not None, self.IDLE_EXIT):
                    self._thread = None  # idle: gone, under the lock -- start() makes another
                    return
                (fn, args), self._job = self._job, None
                self._running = True
            try:
                if self.counted:
                    with background_work():
                        result = ("ok", fn(*args))
                else:
                    result = ("ok", fn(*args))
            except Exception as e:  # reported by take()
                result = ("error", e)
            with self._cond:
                self._result = result
                self._running = False
                self._cond.notify_all()
