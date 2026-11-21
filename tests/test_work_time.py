"""A file's logged work time, shown at the bottom of the page's file panel.

    python3 tests/test_work_time.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def _line(filepath: str, seconds: float, saved=True) -> str:
    entry = {"action": "session_end", "filepath": filepath, "duration_seconds": seconds}
    if saved is not None:
        entry["saved"] = saved
    return json.dumps(entry) + "\n"


def main() -> None:
    import importlib

    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    tracking = importlib.import_module(f"{pkg.__name__}.lib.monitoring.tracking")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "proj"
        logs = root / "config" / "logs"
        (logs / "archives").mkdir(parents=True)
        log = logs / "sessions_log.jsonl"
        sh = "shots/sq010/sh010"
        log.write_text(
            _line(f"{sh}/sq010_sh010_v001.blend", 600)
            + _line(f"{sh}/sq010_sh010_v002.blend", 300)
            # Never saved: someone looking, not work.
            + _line(f"{sh}/sq010_sh010_v002.blend", 5000, saved=False)
            # Before "saved" was logged: counts.
            + _line("assets/chars/c_hero/c_hero_v003.blend", 120, saved=None)
            # An absolute path under this root: the same folder.
            + _line(str(root / sh / "sq010_sh010_v003.blend"), 100)
            + "not json\n",
            encoding="utf-8",
        )
        (logs / "archives" / "sessions_log_2026-10.jsonl").write_text(
            _line(f"{sh}/sq010_sh010_v001.blend", 1000), encoding="utf-8"
        )
        key = os.path.normcase(sh)
        totals = tracking.work_times(root)
        assert totals[key] == 2000, totals
        assert totals[os.path.normcase("assets/chars/c_hero")] == 120, totals

        # Unchanged log: the cached totals, not read again.
        assert tracking.work_times(root) is totals

        # A session ended: read again, the archives kept.
        time.sleep(0.01)
        with open(log, "a", encoding="utf-8") as f:
            f.write(_line(f"{sh}/sq010_sh010_v003.blend", 50))
        os.utime(log, (time.time() + 5, time.time() + 5))
        assert tracking.work_times(root)[key] == 2050

        # No log at all: nothing, no error.
        assert tracking.work_times(Path(d) / "none") == {}
    print("work time: ok")


if __name__ == "__main__":
    main()
