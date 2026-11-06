"""Keep the machine out of idle sleep while it's a farm worker: a render
doesn't count as activity for the OS (only keyboard and mouse do), so a
worker could fall asleep mid-render. Idle sleep only -- the screen may still
turn off, the user can still put it to sleep, Windows Update can still
restart it. Best effort: never raises, nothing changes where it can't be
done. See NOTES.md, "Workers: no idle sleep"."""

import os
import shutil
import subprocess
import sys

from ..lib import log

# Windows SetThreadExecutionState flags.
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001

_held = False
_proc: subprocess.Popen | None = None  # macOS / Linux: the inhibitor process


def keep_awake(on: bool) -> None:
    """Hold (on) or release the machine's idle sleep. Called on every change
    of the worker role; acts only on an actual change."""
    global _held
    if bool(on) == _held:
        return
    try:
        if sys.platform == "win32":
            _windows(on)
        elif on:
            _start_inhibitor()
        else:
            _stop_inhibitor()
        _held = bool(on)
    except Exception as e:
        _held = bool(on)  # not retried every tick
        if on:
            log("WARNING", "farm", f"Could not keep this machine out of sleep: {e}")


def _windows(on: bool) -> None:
    """The flag belongs to the calling thread -- Blender's main thread,
    where the role changes -- until reset, or the process ends."""
    import ctypes

    flags = _ES_CONTINUOUS | (_ES_SYSTEM_REQUIRED if on else 0)
    if not ctypes.windll.kernel32.SetThreadExecutionState(flags):
        raise OSError("SetThreadExecutionState refused")


def _start_inhibitor() -> None:
    """macOS caffeinate / Linux systemd-inhibit, tied to Blender's pid: it
    ends with Blender, even after a crash."""
    global _proc
    pid = str(os.getpid())
    if sys.platform == "darwin":
        cmd = ["caffeinate", "-i", "-w", pid]
    elif shutil.which("systemd-inhibit"):
        cmd = [
            "systemd-inhibit",
            "--what=idle:sleep",
            "--who=Minimalist Pipeline",
            "--why=Farm worker",
            "--mode=block",
            "tail",
            f"--pid={pid}",
            "-f",
            "/dev/null",
        ]
    else:
        return  # nothing to ask: as before
    _proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_inhibitor() -> None:
    global _proc
    proc, _proc = _proc, None
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
