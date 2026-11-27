"""The renders the live page offers to watch (lib/monitoring/live.py
_versions()): newest first by render_history.json, never by the folders'
own times -- folders copied or pasted are written anew -- without Blender.

    python3 tests/test_live_versions_order.py
"""

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    live = importlib.import_module(f"{fake_bpy.load().__name__}.lib.monitoring.live")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        owner = root / "shots" / "sq010" / "sh010"
        (owner / ".pipeline").mkdir(parents=True)
        renders = root / "renders" / "sq010" / "sh010"
        names = ["v001_001", "v002_001", "v002_002", "v003_001", "v004_001"]
        for k, name in enumerate(names):
            (renders / name).mkdir(parents=True)
            (renders / name / f"sq010_sh010_{name}.mp4").write_bytes(b"x")
        # Pasted: their times the reverse of the renders' order.
        for k, name in enumerate(names):
            t = 2_000_000_000 - k * 1000
            os.utime(renders / name, (t, t))

        def entry(name, at):
            return {
                "status": "finished",
                "completed_at": at,
                "output_path": f"renders/sq010/sh010/{name}/sq010_sh010_{name.split('_')[0]}.#####",
            }

        history = {
            "entries": [
                entry("v001_001", "2026-11-01T10:00:00"),
                entry("v002_001", "2026-11-02T10:00:00"),
                entry("v002_002", "2026-11-03T10:00:00"),
                # Re-rendered without a new increment: its latest finish counts.
                entry("v001_001", "2026-11-05T10:00:00"),
                {"status": "failed", "completed_at": "2026-11-09T10:00:00", "output_path": "renders/sq010/sh010/v003_001/x.#####"},
            ]
        }
        (owner / ".pipeline" / "render_history.json").write_text(json.dumps(history))

        got = [r["folder"] for r in live._versions(root, "shot", owner, "v")[""]]
        # v004_001 and v003_001 unknown to the history: after v002_002, the newest
        # known one their names come after -- v001_001 rendered again since, first.
        assert got == ["v001_001", "v004_001", "v003_001", "v002_002", "v002_001"], got

        # No history at all: by name, newest version and increment first.
        (owner / ".pipeline" / "render_history.json").unlink()
        got = [r["folder"] for r in live._versions(root, "shot", owner, "v")[""]]
        assert got == ["v004_001", "v003_001", "v002_002", "v002_001", "v001_001"], got
    print("live versions order: ok")


if __name__ == "__main__":
    main()
