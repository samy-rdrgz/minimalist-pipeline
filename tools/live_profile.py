"""What the live page costs the Blender serving it -- a debug script, run
inside Blender (Text Editor > Open this file > Run Script), the live page
open in a browser (or a phone). For DURATION seconds it times, then puts
everything back as it was and writes its report to the console and to a
text block "live_profile_report" (Text Editor):

- Blender's main thread: each turn of the page's timer (live.py _turn())
  and its parts -- the farm read (refresh_step()), the page's data built
  again (_rebuild()), the farm's jobs (_farm_data()). This is what can make
  the interface stutter.
- The project's passes, on their own thread (live.py _read(), every
  READ_EVERY seconds while a page is open): how long, how much CPU.
- The page's requests (server threads): how many, by path, bytes sent
  (after gzip), CPU spent answering. /data waits for news (long poll): its
  wall time is mostly waiting, its CPU time is what it cost.
- Blender's smoothness: a 50 ms probe timer, how late it ran -- a late timer
  is a frozen interface, whatever froze it.
- The process: CPU of every thread together over the window, in % of one
  core.

Run it once with the page open, once with it closed (or IDLE_AFTER
seconds after closing it): the difference is the page's cost. Nothing is
written to the project. Not shipped (tools/ is out of the extension).
"""

import sys
import threading
import time
from urllib.parse import urlparse

import bpy

DURATION = 30.0  # seconds measured
PROBE = 0.05  # the smoothness probe's interval


def _module(suffix):
    for name, mod in list(sys.modules.items()):
        if name.endswith(suffix) and mod is not None:
            return mod
    return None


live = _module(".lib.monitoring.live")
loop = _module(".farm.loop")
if live is None:
    raise RuntimeError("the add-on's live module isn't loaded: is minimalist pipeline enabled?")
if getattr(live, "_mp_profiling", False):
    raise RuntimeError("a profile is already running: wait for its report")
if not live.running():
    print("live_profile: the live page isn't served (Monitoring > Open the live page): measuring anyway")


class Stat:
    """Durations (wall and CPU of the calling thread), in seconds."""

    def __init__(self):
        self.wall, self.cpu = [], []
        self.lock = threading.Lock()

    def add(self, wall, cpu):
        with self.lock:
            self.wall.append(wall)
            self.cpu.append(cpu)

    def line(self, name, window):
        w = sorted(self.wall)
        if not w:
            return f"  {name:<28} -"
        n = len(w)
        p95 = w[min(n - 1, int(n * 0.95))]
        return (
            f"  {name:<28} {n:>5} calls  {n / window:6.1f}/s   wall: mean {1000 * sum(w) / n:7.2f} ms"
            f"  p95 {1000 * p95:7.2f}  max {1000 * w[-1]:7.2f}  total {sum(w):6.2f} s"
            f"   cpu total {sum(self.cpu):6.2f} s"
        )


S = {k: Stat() for k in ("turn", "refresh_step", "rebuild", "farm_data", "read", "read_live")}
REQ = {}  # path: [count, bytes, wall, cpu]
REQ_LOCK = threading.Lock()
LAG = []
originals = []


def timed(owner, attr, key):
    """owner.attr wrapped: its time into S[key]."""
    fn = getattr(owner, attr)
    originals.append((owner, attr, fn))

    def wrapper(*a, **k):
        t0, c0 = time.perf_counter(), time.thread_time()
        try:
            return fn(*a, **k)
        finally:
            S[key].add(time.perf_counter() - t0, time.thread_time() - c0)

    setattr(owner, attr, wrapper)


class Counting:
    """A handler's wfile, its bytes counted."""

    def __init__(self, f):
        self.f, self.n = f, 0

    def write(self, b):
        self.n += len(b)
        return self.f.write(b)

    def __getattr__(self, k):
        return getattr(self.f, k)


def path_key(raw):
    p = urlparse(raw).path
    for prefix in ("/media/", "/thumb/"):
        if p.startswith(prefix):
            return prefix + "…"
    return p or "/"


def wrap_handler(cls):
    for verb in ("do_GET", "do_POST"):
        fn = getattr(cls, verb, None)
        if fn is None or getattr(fn, "_mp_prof", False):
            continue
        originals.append((cls, verb, fn))

        def wrapper(self, _fn=fn):
            t0, c0 = time.perf_counter(), time.thread_time()
            self.wfile = Counting(self.wfile)
            try:
                return _fn(self)
            finally:
                key = path_key(self.path)
                with REQ_LOCK:
                    r = REQ.setdefault(key, [0, 0, 0.0, 0.0])
                    r[0] += 1
                    r[1] += self.wfile.n
                    r[2] += time.perf_counter() - t0
                    r[3] += time.thread_time() - c0

        wrapper._mp_prof = True
        setattr(cls, verb, wrapper)


# --- start -----------------------------------------------------------------------

live._mp_profiling = True
timed(live, "_turn", "turn")
timed(live, "_rebuild", "rebuild")
timed(live, "_farm_data", "farm_data")
timed(live, "_read", "read")
timed(live, "read_live", "read_live")
if loop is not None:
    timed(loop, "refresh_step", "refresh_step")
servers = [live._server] + list((live._lan.get("servers") or {}).values())
for srv in [s for s in servers if s is not None]:
    wrap_handler(srv.RequestHandlerClass)

sh = live._shared
v0 = sh.version if sh else 0
t_start, cpu_start = time.perf_counter(), time.process_time()
probe_last = [time.perf_counter()]


def probe():
    now = time.perf_counter()
    LAG.append(max(0.0, now - probe_last[0] - PROBE))  # early: on time
    probe_last[0] = now
    if now - t_start >= DURATION:
        finish()
        return None
    return PROBE


def finish():
    window = time.perf_counter() - t_start
    cpu = time.process_time() - cpu_start
    for owner, attr, fn in reversed(originals):
        setattr(owner, attr, fn)
    live._mp_profiling = False

    lag = sorted(LAG) or [0.0]
    late = [x for x in lag if x > 0.1]
    sh2 = live._shared
    lines = [
        f"Live page cost over {window:.1f} s  (served: {live.running()}, page seen "
        f"{(time.monotonic() - sh2.last_seen) if sh2 else float('nan'):.0f} s ago)",
        "",
        f"Process CPU (every thread): {cpu:.2f} s = {100 * cpu / window:.1f} % of one core",
        "",
        "Blender's main thread (what can freeze the interface):",
        S["turn"].line("page's turn (_turn)", window),
        S["refresh_step"].line("  farm read (refresh_step)", window),
        S["rebuild"].line("  data rebuilt (_rebuild)", window),
        S["farm_data"].line("    farm jobs (_farm_data)", window),
        f"  main thread busy with the page: {100 * sum(S['turn'].wall) / window:.2f} % of the time",
        "",
        "Project passes (own thread, compete for Python's lock):",
        S["read"].line("pass (_read)", window),
        S["read_live"].line("  folders read (read_live)", window),
        "",
        "Requests (server threads):",
    ]
    with REQ_LOCK:
        for path, (n, b, wall, c) in sorted(REQ.items(), key=lambda x: -x[1][1]):
            lines.append(
                f"  {path:<28} {n:>5} req  {n / window:5.1f}/s  sent {b / 1024:9.1f} KB"
                f"  ({b / 1024 / window:7.1f} KB/s)  cpu {c:6.3f} s  wall {wall:7.2f} s"
            )
        if not REQ:
            lines.append("  none (no page open?)")
        total = sum(r[1] for r in REQ.values())
    lines += [
        f"  total sent: {total / 1024:.1f} KB ({total / 1024 / window:.1f} KB/s)",
        "",
        f"Data versions published: {(sh2.version - v0) if sh2 else 0}   (last body {len(sh2.body) / 1024 if sh2 else 0:.1f} KB before gzip)",
        "",
        f"Smoothness (a {int(PROBE * 1000)} ms timer, how late): mean {1000 * sum(lag) / len(lag):.1f} ms,"
        f" p95 {1000 * lag[min(len(lag) - 1, int(len(lag) * 0.95))]:.1f} ms, max {1000 * lag[-1]:.1f} ms,"
        f" {len(late)} times over 100 ms",
    ]
    report = "\n".join(lines)
    print("\n" + report + "\n")
    text = bpy.data.texts.get("live_profile_report") or bpy.data.texts.new("live_profile_report")
    text.clear()
    text.write(report + "\n")


bpy.app.timers.register(probe, first_interval=PROBE)
print(f"live_profile: measuring for {DURATION:.0f} s -- use the page (and Blender) as usual; the report follows.")
