"""The project's config checked off Blender's thread (lib/config.py
ConfigCache.get()): on the main thread, once its time is up, the cached
config answered and its file's date read on a thread of its own -- a change
read at the next check; on another thread, or with nothing cached, at once.
And the live page's server quiet on a page gone mid-answer (live.py
_Server.handle_error()).

    python3 tests/test_config_stat.py
"""

import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    config = importlib.import_module(f"{pkg.__name__}.lib.config")
    live = importlib.import_module(f"{pkg.__name__}.lib.monitoring.live")
    C = config.ConfigCache

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        f = root / "config.json"
        f.write_text(json.dumps({"v": 1}))
        config.get_active_project_root = lambda: root
        config.get_config_filepath = lambda: f
        config.read_project_config = lambda r: json.loads(f.read_text())
        C.invalidate()

        assert C.get() == {"v": 1}  # nothing cached: read at once
        f.write_text(json.dumps({"v": 2}))
        os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))
        C._checked_at = -1e9  # its time up
        assert C.get() == {"v": 1}  # main thread: the cache answered, the date read apart
        C._stat_job.join()
        C._checked_at = -1e9
        assert C.get() == {"v": 2}  # the next check: the change read

        # Another thread: at once, as before.
        f.write_text(json.dumps({"v": 3}))
        os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 20))
        C._checked_at = -1e9
        out = []
        t = threading.Thread(target=lambda: out.append(C.get()))
        t.start()
        t.join()
        assert out == [{"v": 3}], out
        C.invalidate()

    # A page gone while answered: nothing in the console.
    srv = live._Server.__new__(live._Server)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        try:
            raise ConnectionAbortedError(10053, "aborted")
        except ConnectionAbortedError:
            srv.handle_error(None, ("127.0.0.1", 1))
    assert err.getvalue() == "", err.getvalue()
    print("ok")


if __name__ == "__main__":
    main()
