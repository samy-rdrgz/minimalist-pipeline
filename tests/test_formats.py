"""Each project file's "format_version" (lib/formats.py): stamped on every
write of a listed kind, left off anything else; a file a newer addon wrote
never rewritten (PipelineError), still read.

    python3 tests/test_formats.py
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
    formats = importlib.import_module(f"{pkg.__name__}.lib.formats")
    core = importlib.import_module(f"{pkg.__name__}.lib.core")
    errors = importlib.import_module(f"{pkg.__name__}.lib.errors")
    core.get_machine_id = lambda *a, **k: "test-machine"

    assert formats.kind_of("/p/a/.pipeline/tracking.json") == "tracking"
    assert formats.kind_of("/p/a/.pipeline/v003-stable.stablemeta") == "stablemeta"
    assert formats.kind_of("/p/config/project_config.json") == "project_config"
    assert formats.kind_of("/p/config/.farm/queue/actives/abc.json") is None
    assert formats.version_of({"entries": []}) == "1.x"
    assert formats.too_new("/a/tracking.json", {"format_version": "2.0"}) is None
    assert formats.too_new("/a/tracking.json", {"format_version": "2.10"}) == "2.10"

    with tempfile.TemporaryDirectory() as d:
        t = Path(d) / "tracking.json"
        with core.locked_json(t) as box:
            box["data"], box["action"] = {"entries": []}, "to_write"
        got = json.loads(t.read_text(encoding="utf-8"))
        assert got == {"format_version": formats.current(t), "entries": []}, got

        other = Path(d) / "job.json"
        core.write_json_atomic(other, {"a": 1})
        assert json.loads(other.read_text(encoding="utf-8")) == {"a": 1}

        t.write_text(json.dumps({"format_version": "9.0", "entries": [], "new": 1}), encoding="utf-8")
        with core.locked_json(t, read_only=True) as box:
            assert box["data"]["new"] == 1  # still read
        try:
            with core.locked_json(t) as box:
                box["data"], box["action"] = {"entries": []}, "to_write"
            raise AssertionError("a newer addon's file rewritten")
        except errors.PipelineError:
            pass
        assert json.loads(t.read_text(encoding="utf-8"))["new"] == 1
    print("OK: formats")


if __name__ == "__main__":
    main()
