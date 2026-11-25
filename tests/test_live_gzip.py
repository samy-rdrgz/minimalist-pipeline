"""The live page's replies, gzipped (lib/monitoring/live.py _gzip()): the
same bytes back once unzipped, the page compressed to a fraction, the same
body compressed once.

    python3 tests/test_live_gzip.py
"""

import gzip
import importlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    live = importlib.import_module(f"{pkg.__name__}.lib.monitoring.live")
    page = importlib.import_module(f"{pkg.__name__}.lib.monitoring.snapshot_page")

    demo = json.loads((REPO / "tests/fixtures/snapshot_demo.json").read_text(encoding="utf-8"))
    body = page.render_html(demo).encode("utf-8")
    gz = live._gzip(body)
    assert gzip.decompress(gz) == body
    assert len(gz) < len(body) / 3, (len(gz), len(body))
    # Asked again: the one already made.
    assert live._gzip(bytes(body)) is gz
    print("ok", len(body), "->", len(gz))


if __name__ == "__main__":
    main()
