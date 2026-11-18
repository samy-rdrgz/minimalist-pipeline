"""Read a .blend's libraries and linked data, and write a copy with its
library paths changed -- without Blender: no file opened, so a scene of
several GB is read in a moment, from any thread.

A .blend is a header then a sequence of blocks (code, length, old address,
struct index, count); its DNA1 block describes every struct. Only the few
blocks wanted are read -- libraries (LI), linked data placeholders (ID),
local data (an ID's own code) -- the rest is skipped (seek). A compressed
file (gzip, zstd) can't be skipped through: it is read whole. Pure stdlib
(+ zstandard, bundled with Blender, for zstd files). See NOTES.md,
"Reading a .blend without Blender"."""

import gzip
import os
import re
import shutil
import struct
import threading
from pathlib import Path


class BlendError(Exception):
    pass


class _Stream:
    """A .blend, plain, gzip or zstd, its position in the uncompressed data."""

    def __init__(self, path: Path):
        self.raw = open(path, "rb", buffering=4 << 20)  # one read per 4 MB on a share
        magic = self.raw.read(4)
        self.raw.seek(0)
        self.kind = "plain"
        if magic[:2] == b"\x1f\x8b":
            self.f, self.kind = gzip.GzipFile(fileobj=self.raw), "gzip"
        elif magic == b"\x28\xb5\x2f\xfd":
            self.f, self.kind = _zstd_reader(self.raw), "zstd"
        else:
            self.f = self.raw
        self.pos = 0

    def read(self, n):
        b = self.f.read(n)
        self.pos += len(b)
        return b

    def skip(self, n):
        if self.kind == "plain":
            self.f.seek(n, 1)
            self.pos += n
            return
        while n > 0:
            b = self.f.read(min(n, 4 << 20))
            if not b:
                break
            n -= len(b)
            self.pos += len(b)

    def close(self):
        self.raw.close()


def _zstd_reader(raw):
    try:
        import zstandard  # bundled with Blender

        return zstandard.ZstdDecompressor().stream_reader(raw, read_across_frames=True)
    except ImportError:
        pass
    try:
        from compression import zstd  # Python 3.14+

        return zstd.ZstdFile(raw)
    except ImportError:
        raise BlendError("compressed with zstd, no zstd reader here")


class _Head:
    __slots__ = ("code", "sdna", "old", "length", "nr", "pos", "data")

    def __init__(self, code, sdna, old, length, nr, pos):
        self.code, self.sdna, self.old, self.length, self.nr, self.pos, self.data = code, sdna, old, length, nr, pos, None


def _header(s: _Stream):
    """(header bytes, endian, pointer size, BHead format, large BHead)."""
    head = s.read(12)
    if head[:7] != b"BLENDER":
        raise BlendError("not a .blend")
    if head[7:9].isdigit():  # Blender 5: BLENDER17-01v0500, 64-bit lengths
        head += s.read(int(head[7:9]) - 12)
        return head, "<", 8, "<4siqqq", True
    ptr = 8 if head[7:8] == b"-" else 4
    e = "<" if head[8:9] == b"v" else ">"
    return head, e, ptr, e + "4si" + ("Q" if ptr == 8 else "I") + "ii", False


def _next(s: _Stream, fmt: str, large: bool):
    size = struct.calcsize(fmt)
    h = s.read(size)
    if len(h) < size:
        return None
    if large:
        code, sdna, old, length, nr = struct.unpack(fmt, h)
    else:
        code, length, old, sdna, nr = struct.unpack(fmt, h)
    if length < 0:
        raise BlendError("unreadable block header")
    return _Head(code, sdna, old, length, nr, s.pos)


def _parse_sdna(d: bytes, ptr: int, e: str) -> dict:
    """{struct index: (name, size, {field: (offset, size)})}, top-level fields."""
    p = 0

    def tag(t):
        nonlocal p
        if d[p:p + 4] != t:
            raise BlendError("unexpected DNA layout")
        p += 4

    def align():
        nonlocal p
        p = (p + 3) & ~3

    def cstrings(n):
        nonlocal p
        out = []
        for _ in range(n):
            q = d.index(b"\0", p)
            out.append(d[p:q].decode("latin-1"))
            p = q + 1
        return out

    tag(b"SDNA")
    tag(b"NAME")
    n = struct.unpack_from(e + "i", d, p)[0]
    p += 4
    names = cstrings(n)
    align()
    tag(b"TYPE")
    n = struct.unpack_from(e + "i", d, p)[0]
    p += 4
    types = cstrings(n)
    align()
    tag(b"TLEN")
    tlen = struct.unpack_from(e + "%dh" % n, d, p)
    p += 2 * n
    align()
    tag(b"STRC")
    ns = struct.unpack_from(e + "i", d, p)[0]
    p += 4
    structs = {}
    for i in range(ns):
        t, nf = struct.unpack_from(e + "hh", d, p)
        p += 4
        off, fields = 0, {}
        for _ in range(nf):
            ft, fn = struct.unpack_from(e + "hh", d, p)
            p += 4
            name = names[fn]
            mul = 1
            for m in re.findall(r"\[(\d+)\]", name):
                mul *= int(m)
            size = (ptr if name.startswith("*") or name.startswith("(*") else tlen[ft]) * mul
            fields.setdefault(re.split(r"[\[)]", name.lstrip("*(").lstrip("*"))[0], (off, size))
            off += size
        structs[i] = (types[t], tlen[t] or off, fields)
    return structs


_DNA: dict = {}  # header -> structs: the files saved by one Blender share it
_DNA_LOCK = threading.Lock()


def _is_id(code: bytes) -> bool:
    """An ID block's code: its two letters then two zero bytes (OB, MA, LI, ID...)."""
    return code[2:] == b"\0\0"


class Blend:
    """What read() found: .libraries [{"old", "raw" (bytes as stored), "pos",
    "size", "direct"}], .linked {library old address: {ID names}} (e.g.
    "OBbob", type prefix included), .local {ID names} (the file's own data),
    .kind ("plain", "gzip", "zstd")."""

    def __init__(self):
        self.libraries, self.linked, self.local, self.kind = [], {}, set(), "plain"


def read(path: Path) -> Blend:
    """A .blend's libraries, linked and local data names. Any thread."""
    s = _Stream(Path(path))
    try:
        head, e, ptr, fmt, large = _header(s)
        key = (head, ptr)
        with _DNA_LOCK:
            structs = _DNA.get(key)
        heads, dna_raw = [], None
        while True:
            h = _next(s, fmt, large)
            if h is None or h.code == b"ENDB":
                break
            if h.code == b"DNA1":
                dna_raw = s.read(h.length)
                continue
            if h.code == b"LI\0\0":
                h.data = s.read(h.length)
            elif _is_id(h.code):
                # The ID part only: its name and library pointer sit in its first bytes.
                h.data = s.read(min(h.length, 512))
                s.skip(h.length - len(h.data))
            else:
                s.skip(h.length)
            heads.append(h)
        if dna_raw is None:
            raise BlendError("no DNA1 block")
        if structs is None:
            structs = _parse_sdna(dna_raw, ptr, e)
            with _DNA_LOCK:
                _DNA[key] = structs
        out = Blend()
        out.kind = s.kind
        order = "little" if e == "<" else "big"
        for h in heads:
            if h.data is None:
                continue
            name_t, _size, fields = structs.get(h.sdna, ("", 0, {}))
            if h.code == b"LI\0\0":
                f = fields.get("filepath")
                if not f:
                    f = fields.get("name")
                    f = f if f and f[1] >= 256 else None
                if not f:
                    continue
                raw = h.data[f[0]:f[0] + f[1]].split(b"\0", 1)[0]
                parent = fields.get("parent")
                direct = not parent or int.from_bytes(h.data[parent[0]:parent[0] + ptr], order) == 0
                out.libraries.append({"old": h.old, "raw": raw, "pos": h.pos + f[0], "size": f[1], "direct": direct})
                continue
            # An ID: its own data, or a placeholder of linked data (code ID).
            idf = fields.get("id")
            base = idf[0] if idf and name_t != "ID" else 0
            idfields = fields if name_t == "ID" else structs.get(_id_index(structs), ("", 0, {}))[2]
            nf, lf = idfields.get("name"), idfields.get("lib")
            if not nf or not lf:
                continue
            name = h.data[base + nf[0]:base + nf[0] + nf[1]].split(b"\0", 1)[0].decode("utf-8", "replace")
            lib = int.from_bytes(h.data[base + lf[0]:base + lf[0] + ptr], order)
            if not name:
                continue
            if lib:
                out.linked.setdefault(lib, set()).add(name)
            else:
                out.local.add(name)
        return out
    finally:
        s.close()


def _id_index(structs: dict) -> int:
    for k, v in structs.items():
        if v[0] == "ID":
            return k
    return -1


def resolve(raw: bytes, here: Path) -> Path:
    """A path as Blender stores it ("//" relative to the file's folder)."""
    s = raw.decode("utf-8", "replace")
    if s.startswith("//"):
        return Path(os.path.normpath(os.path.join(here, s[2:].replace("\\", "/"))))
    return Path(os.path.normpath(s))


def write_copy(src: Path, dst: Path, paths: dict) -> None:
    """Copy src to dst with some library paths changed: {position in the
    uncompressed data: (field size, new path bytes)}. A compressed file is
    written uncompressed (the file keeps its "compress" setting: Blender
    compresses it again on its next save)."""
    src, dst = Path(src), Path(dst)
    tmp = dst.with_name(dst.name + ".part")
    s = _Stream(src)
    try:
        if s.kind == "plain":
            s.close()
            shutil.copyfile(src, tmp)
        else:
            with open(tmp, "wb", buffering=4 << 20) as out:
                while True:
                    b = s.read(4 << 20)
                    if not b:
                        break
                    out.write(b)
    finally:
        s.close()
    with open(tmp, "r+b") as fh:
        for pos, (size, nb) in paths.items():
            if len(nb) >= size:
                raise BlendError(f"path too long: {nb[:60]!r}")
            fh.seek(pos)
            fh.write(nb + b"\0" * (size - len(nb)))
    os.replace(tmp, dst)
