"""Update links (lib/relink.py): the plan, a locked file left, the run
read back -- Blender stood in for by a script that copies the file.

    python3 tests/test_relink.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def _blend(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"BLENDER-v400")


def main() -> None:
    import importlib

    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    config = importlib.import_module(f"{pkg.__name__}.lib.config")
    relink = importlib.import_module(f"{pkg.__name__}.lib.relink")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "proj"
        (root / "config").mkdir(parents=True)
        (root / "config" / "project_config.json").write_text(json.dumps({
            "naming": {"sequence": {"prefix": "sq", "digits": 3}, "shot": {"prefix": "sh", "digits": 3},
                       "version": {"prefix": "v", "digits": 3}},
            "structure": {"asset_prefixes": ["ch"], "library_prefixes": []},
            "tags": ["stable", "approved"],
        }), encoding="utf-8")
        config.set_daemon_active_project_root(root)
        config.ConfigCache.invalidate()

        # The naming knows the tag, whatever the project lists.
        p = config.parse_filename("sq010_sh010_v004-updatelink.blend")
        assert p and p["tag"] == "updatelink" and int(p["number"]) == 4, p
        assert config.parse_filename("sq010_sh010_v004-approved.blend")["tag"] == "approved"

        bob = root / "assets" / "ch" / "ch_bob"
        for n in (1, 2):
            _blend(bob / f"ch_bob_v00{n}-stable.blend")
        shot = root / "shots" / "sq010" / "sh010"
        _blend(shot / "sq010_sh010_v002.blend")
        _blend(shot / "sq010_sh010_v003.blend")
        (shot / ".pipeline").mkdir()
        (shot / ".pipeline" / "v003.wipmeta").write_text(json.dumps({
            "file": "shots/sq010/sh010/sq010_sh010_v003.blend", "created_at": "2026-11-16T10:00:00+01:00",
            "linked": [{"file": "assets/ch/ch_bob/ch_bob_v001-stable.blend"}],
        }), encoding="utf-8")

        plan = relink.relink_plan(root, shot)
        assert not plan["error"], plan
        assert plan["source"].name == "sq010_sh010_v003.blend"
        assert plan["out"].name == "sq010_sh010_v004-updatelink.blend", plan["out"]
        assert plan["mapping"] == [(str(bob / "ch_bob_v001-stable.blend"), str(bob / "ch_bob_v002-stable.blend"))]
        assert plan["linked"] == [{"file": "assets/ch/ch_bob/ch_bob_v002-stable.blend"}]

        # Up to date: nothing to do.
        assert relink.relink_plan(root, bob)["error"]

        # Someone working in it: left.
        lock = shot / ".sq010_sh010_v003.blend.lock"
        lock.write_text(json.dumps({"machine_id": "x", "at": time.time()}), encoding="utf-8")
        assert "open to work on" in relink.relink_plan(root, shot)["error"]
        lock.unlink()

        # The run: Blender stood in for by a copy, then poll() reads it back.
        fake = Path(d) / "fake_blender.py"
        fake.write_text(
            "import json,shutil,sys\n"
            "src, req = sys.argv[1], sys.argv[2]\n"
            "r = json.load(open(req))\n"
            "shutil.copy(src, r['out'])\n"
            "json.dump({'status': 'ok', 'message': '1 link(s)'}, open(req, 'w'))\n",
            encoding="utf-8",
        )
        relink.blender_command = lambda script, args, blend=None, factory=False: [sys.executable, str(fake), str(blend), str(args[0])]
        made = []
        relink.create_wipmeta = lambda **kw: made.append(kw)
        res = relink.start(root, [shot])
        assert res["started"] == ["sh010"], res
        # Asked twice while it runs: not started again.
        assert relink.start(root, [shot])["skipped"][0][1] == "already updating"
        for _ in range(100):
            if relink.poll():
                break
            time.sleep(0.05)
        st = relink.states()["shots/sq010/sh010"]
        assert st["state"] == "done", st
        out = shot / "sq010_sh010_v004-updatelink.blend"
        assert out.is_file()
        assert made and made[0]["filepath"] == out and made[0]["creation_mode"] == "relink", made
        assert made[0]["linked"] == [{"file": "assets/ch/ch_bob/ch_bob_v002-stable.blend"}]
        # The source untouched; no request file left behind.
        assert (shot / "sq010_sh010_v003.blend").read_bytes() == b"BLENDER-v400"

        # The next one numbers after it, from the -updatelink.
        (shot / ".pipeline" / "v004-updatelink.wipmeta").write_text(json.dumps({
            "linked": [{"file": "assets/ch/ch_bob/ch_bob_v001-stable.blend"}]}), encoding="utf-8")
        assert relink.relink_plan(root, shot)["out"].name == "sq010_sh010_v005-updatelink.blend"

        # A failure says why.
        fake.write_text(
            "import json,sys\njson.dump({'status': 'error', 'message': 'not found: ch_bob_v002-stable.blend'}, open(sys.argv[2], 'w'))\n",
            encoding="utf-8",
        )
        relink._jobs.clear()
        relink.start(root, [shot])
        for _ in range(100):
            if relink.poll():
                break
            time.sleep(0.05)
        st = relink.states()["shots/sq010/sh010"]
        assert st["state"] == "failed" and "not found" in st["message"], st
    print("relink: ok")


if __name__ == "__main__":
    main()
