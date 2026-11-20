"""The live page's first read in batches (lib/monitoring/live.py): the
reader's pass told its progress folder by folder, the first read's batches
published as it goes (after FIRST_BATCH, then every BATCH_EVERY), a later
pass none; the page told a batch is partial (meta "reading").

    python3 tests/test_live_batches.py
"""

import importlib
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    live = importlib.import_module(f"{pkg.__name__}.lib.monitoring.live")
    page = importlib.import_module(f"{pkg.__name__}.lib.monitoring.snapshot_page")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        names = []
        for top, group, n in (("shots", "sq010", 4), ("assets", "ch", 3)):
            for i in range(n):
                name = f"{group}_{i:03d}"
                pipe = root / top / group / name / ".pipeline"
                pipe.mkdir(parents=True)
                (pipe / "tracking.json").write_text(json.dumps({"file_name": name}), encoding="utf-8")
                names.append(name)

        seen = []
        out, changed = live.read_live(root, {}, {}, "v", on_progress=lambda o, done, total: seen.append((len(o), done, total)))
        assert changed and len(out) == 7, out.keys()
        assert [s[1] for s in seen] == list(range(7)) and {s[2] for s in seen} == {7}, seen
        assert all(n <= done for n, done, _ in seen), seen  # what's read so far, never ahead

        # The first read: batches published (the clock made to run: one a folder).
        clock = [0.0]
        monotonic = live.time.monotonic  # the time module's: put back below
        live.time.monotonic = lambda: clock.__setitem__(0, clock[0] + 1.5) or clock[0]
        live._reader.update(partial=None, progress=None, result=None)
        batches = []
        real = live.read_live

        def spying(*a, on_progress=None, **k):
            def hook(o, done, total):
                on_progress(o, done, total)
                if live._reader["partial"] is not None:
                    batches.append(live._reader["partial"][2:])
                    live._reader["partial"] = None
            return real(*a, on_progress=hook if on_progress else None, **k)

        live.read_live = spying
        live.work_times = lambda r: {}
        live._rushes_by_name = lambda r: {}
        live._read(root, {}, {}, "v", None, first=True)
        assert batches and all(t == 7 for _, t in batches), batches
        assert live._reader["progress"] == (6, 7), live._reader["progress"]
        assert live._reader["result"] is not None and len(live._reader["result"][1]) == 7

        live.time.monotonic = monotonic
        # A later pass: no batch.
        batches.clear()
        live._read(root, live._reader["result"][1], {}, "v", None, first=False)
        assert not batches, batches

        # The page's meta: a batch says so, a whole read doesn't.
        meta = page._meta({"meta": {"reading": {"done": 3, "total": 7}, "presence": [{"user": "lea"}]}})
        assert meta["reading"] == {"done": 3, "total": 7} and meta["presence"] == [{"user": "lea"}], meta
        assert "reading" not in page._meta({"meta": {}})
    print("OK: live batches")


if __name__ == "__main__":
    main()
