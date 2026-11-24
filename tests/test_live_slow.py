"""The live page's share reads kept a few seconds (lib/monitoring/live.py
_slow()): this Blender's farm roles and the Render form's presets read at
most once per SLOW_TTL, not at each rebuild (twice a second) -- on a slow
share they held Blender's interface; read again once the time is up or the
page's farm action cleared them.

    python3 tests/test_live_slow.py
"""

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    live = importlib.import_module(f"{pkg.__name__}.lib.monitoring.live")

    clock = [100.0]
    real = live.time.monotonic
    live.time.monotonic = lambda: clock[0]
    reads = []

    def read():
        reads.append(clock[0])
        return len(reads)

    live._SLOW.clear()
    assert live._slow("presets", read) == 1
    clock[0] += 1.0
    assert live._slow("presets", read) == 1  # within its time: not read again
    clock[0] += live.SLOW_TTL["presets"]
    assert live._slow("presets", read) == 2  # its time up: read again
    live._SLOW.clear()  # a farm action from the page
    assert live._slow("presets", read) == 3
    assert len(reads) == 3
    live.time.monotonic = real
    print("ok")


if __name__ == "__main__":
    main()
