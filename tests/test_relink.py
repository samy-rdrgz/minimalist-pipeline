"""Update links (lib/relink.py, lib/blendfile.py): the plan, a locked file
left, the run -- on made-up .blend files written here (header, a few ID
blocks, libraries, the DNA describing them: what Blender's own files hold,
reduced to what's read), no Blender.

A shot links ch_bob v001-stable and pr_lamp v001-stable; ch_bob has a v002
still holding what the shot links, pr_lamp a v002 that lost it. The run
writes sq010_sh010_v004-relink.blend repointed to ch_bob v002 only, keeps
the lamp (said), leaves the source untouched.

    python3 tests/test_relink.py
"""

import json
import struct
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

# The made-up DNA: ID {*next, *prev, *newid, *lib, name[66]},
# Library {ID id, filepath[1024], *parent}, Object / Collection {ID id}.
PTR = 8
TYPES = ["char", "int", "ID", "Library", "Object", "Collection"]
NAMES = ["*next", "*prev", "*newid", "*lib", "name[66]", "id", "filepath[1024]", "*parent"]
ID_SIZE = 4 * PTR + 66
TLEN = [1, 4, ID_SIZE, ID_SIZE + 1024 + PTR, ID_SIZE, ID_SIZE]
STRUCTS = [
    (2, [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)]),  # 0: ID
    (3, [(2, 5), (0, 6), (0, 7)]),                  # 1: Library
    (4, [(2, 5)]),                                  # 2: Object
    (5, [(2, 5)]),                                  # 3: Collection
]


def _dna() -> bytes:
    def pad(b):
        return b + b"\0" * (-len(b) % 4)

    out = b"SDNA" + b"NAME" + struct.pack("<i", len(NAMES)) + pad(b"".join(n.encode() + b"\0" for n in NAMES))
    out += b"TYPE" + struct.pack("<i", len(TYPES)) + pad(b"".join(t.encode() + b"\0" for t in TYPES))
    out += b"TLEN" + pad(struct.pack("<%dh" % len(TLEN), *TLEN))
    out += b"STRC" + struct.pack("<i", len(STRUCTS))
    for t, fields in STRUCTS:
        out += struct.pack("<hh", t, len(fields)) + b"".join(struct.pack("<hh", *f) for f in fields)
    return out


def _id(name: str, lib: int = 0) -> bytes:
    return struct.pack("<QQQQ", 0, 0, 0, lib) + name.encode().ljust(66, b"\0")


def _block(code: bytes, sdna: int, old: int, data: bytes) -> bytes:
    return struct.pack("<4siQii", code, len(data), old, sdna, 1) + data


def blend(path: Path, local: list[str], libs: list[tuple[str, list[str]]] = ()) -> None:
    """local: its own data ("OBbob"); libs: (path as stored, names linked from it)."""
    body = b""
    for i, name in enumerate(local):
        body += _block(name[:2].encode() + b"\0\0", 2 if name.startswith("OB") else 3, 0x1000 + i, _id(name))
    for i, (fp, names) in enumerate(libs):
        old = 0x9000 + i * 0x100
        body += _block(b"LI\0\0", 1, old, _id("LI" + Path(fp).name) + fp.encode().ljust(1024, b"\0") + struct.pack("<Q", 0))
        for k, name in enumerate(names):
            body += _block(b"ID\0\0", 0, old + 1 + k, _id(name, lib=old))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"BLENDER-v402" + body + _block(b"DNA1", 0, 0, _dna()) + _block(b"ENDB", 0, 0, b""))


def wait(relink) -> None:
    for _ in range(200):
        if relink.poll():
            return
        time.sleep(0.02)
    raise AssertionError("relink never finished")


def main() -> None:
    import importlib

    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    config = importlib.import_module(f"{pkg.__name__}.lib.config")
    relink = importlib.import_module(f"{pkg.__name__}.lib.relink")
    blendfile = importlib.import_module(f"{pkg.__name__}.lib.blendfile")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "proj"
        (root / "config").mkdir(parents=True)
        (root / "config" / "project_config.json").write_text(json.dumps({
            "naming": {"sequence": {"prefix": "sq", "digits": 3}, "shot": {"prefix": "sh", "digits": 3},
                       "version": {"prefix": "v", "digits": 3}},
            "structure": {"asset_prefixes": ["ch", "pr"], "library_prefixes": []},
            "tags": ["stable", "approved"],
        }), encoding="utf-8")
        config.set_daemon_active_project_root(root)
        config.ConfigCache.invalidate()

        # The naming knows the tag (and its first name), whatever the project lists.
        for tag in ("relink", "updatelink"):
            p = config.parse_filename(f"sq010_sh010_v004-{tag}.blend")
            assert p and p["tag"] == tag and int(p["number"]) == 4, p
        assert config.parse_filename("sq010_sh010_v004-approved.blend")["tag"] == "approved"

        bob, lamp = root / "assets" / "ch" / "ch_bob", root / "assets" / "pr" / "pr_lamp"
        blend(bob / "ch_bob_v001-stable.blend", ["GRbob", "OBbob"])
        blend(bob / "ch_bob_v002-stable.blend", ["GRbob", "OBbob", "OBhat"])
        blend(lamp / "pr_lamp_v001-stable.blend", ["GRlamp", "OBlamp"])
        blend(lamp / "pr_lamp_v002-stable.blend", ["GRlight"])  # the lamp renamed: lost
        shot = root / "shots" / "sq010" / "sh010"
        blend(shot / "sq010_sh010_v002.blend", ["OBcam"])
        src = shot / "sq010_sh010_v003.blend"
        blend(src, ["OBcam"], [
            ("//../../../assets/ch/ch_bob/ch_bob_v001-stable.blend", ["GRbob", "OBbob"]),
            ("//../../../assets/pr/pr_lamp/pr_lamp_v001-stable.blend", ["GRlamp"]),
        ])
        (shot / ".pipeline").mkdir()
        (shot / ".pipeline" / "v003.wipmeta").write_text(json.dumps({
            "file": "shots/sq010/sh010/sq010_sh010_v003.blend", "created_at": "2026-11-16T10:00:00+01:00",
            "linked": [{"file": "assets/ch/ch_bob/ch_bob_v001-stable.blend"}, {"file": "assets/pr/pr_lamp/pr_lamp_v001-stable.blend"}],
        }), encoding="utf-8")
        before = src.read_bytes()

        # The snapshot has the links too (its Links tab): the shot links bob and the lamp, each a newer stable.
        from importlib import import_module
        snap = import_module(relink.__name__.rsplit(".", 1)[0] + ".snapshot")
        for owner in (shot, bob, lamp):
            (owner / ".pipeline").mkdir(exist_ok=True)
            (owner / ".pipeline" / "tracking.json").write_text("{}", encoding="utf-8")
        links = snap.read_snapshot_data(root, None, "v")["live"]
        mine = links[str(shot)]
        assert mine["key"] == "shots/sq010/sh010", mine
        assert sorted((l["key"], l["file"], l["newer"]) for l in mine["links"]) == [
            ("assets/ch/ch_bob", "ch_bob_v001-stable.blend", "ch_bob_v002-stable.blend"),
            ("assets/pr/pr_lamp", "pr_lamp_v001-stable.blend", "pr_lamp_v002-stable.blend"),
        ], mine

        # Read straight from the file.
        b = blendfile.read(src)
        assert [l["raw"].decode().rsplit("/", 1)[1] for l in b.libraries] == ["ch_bob_v001-stable.blend", "pr_lamp_v001-stable.blend"]
        assert b.local == {"OBcam"} and sorted(map(sorted, b.linked.values())) == [["GRbob", "OBbob"], ["GRlamp"]], b.linked

        plan = relink.relink_plan(root, shot)
        assert not plan["error"], plan
        assert plan["source"] == src and plan["out"].name == "sq010_sh010_v004-relink.blend", plan["out"]
        assert len(plan["mapping"]) == 2, plan["mapping"]

        # Up to date: nothing to do.
        assert relink.relink_plan(root, bob)["error"]

        # Someone working in it: left.
        lock = shot / ".sq010_sh010_v003.blend.lock"
        lock.write_text(json.dumps({"machine_id": "x", "at": time.time()}), encoding="utf-8")
        assert "open to work on" in relink.relink_plan(root, shot)["error"]
        lock.unlink()

        made = []
        relink.create_wipmeta = lambda **kw: made.append(kw)
        res = relink.start(root, [shot])
        assert res["started"] == ["sh010"], res
        wait(relink)
        st = relink.states()["shots/sq010/sh010"]
        assert st["state"] == "done" and "pr_lamp_v001-stable.blend kept" in st["message"], st
        out = shot / "sq010_sh010_v004-relink.blend"
        got = blendfile.read(out)
        assert [l["raw"].decode() for l in got.libraries] == [
            "//../../../assets/ch/ch_bob/ch_bob_v002-stable.blend",
            "//../../../assets/pr/pr_lamp/pr_lamp_v001-stable.blend",  # kept: v002 has no lamp
        ], got.libraries
        assert got.linked == b.linked and got.local == b.local  # only a path moved
        assert len(out.read_bytes()) == len(before) and src.read_bytes() == before  # the source untouched
        assert made and made[0]["filepath"] == out and made[0]["creation_mode"] == "relink", made
        assert made[0]["linked"] == [{"file": "assets/ch/ch_bob/ch_bob_v002-stable.blend"},
                                     {"file": "assets/pr/pr_lamp/pr_lamp_v001-stable.blend"}], made[0]["linked"]

        # Nothing it can move (every new stable lost data): failed, said why, nothing written.
        out.unlink()
        relink._jobs.clear()
        blend(bob / "ch_bob_v002-stable.blend", ["GRother"])
        relink.start(root, [shot])
        wait(relink)
        st = relink.states()["shots/sq010/sh010"]
        assert st["state"] == "failed" and "has no bob" in st["message"], st
        assert not out.exists()
    print("relink: ok")


if __name__ == "__main__":
    main()
