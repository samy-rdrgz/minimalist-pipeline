"""Draw the add-on's coloured marks into icons/*.png -- Blender colours no
icon of its own (see NOTES.md, "Coloured marks"). The snapshot page's
keyframe diamonds and post-its, in its dark-theme colours
(templates/snapshot/page.css). Pure Python:

    python3 tools/make_icons.py
"""

import math
import struct
import zlib
from pathlib import Path

SIZE = 64
SAMPLES = 4  # per side, per pixel: the edges smoothed
OUT = Path(__file__).resolve().parent.parent / "icons"

# The snapshot page's dark theme (templates/snapshot/page.css).
DONE = (0x00, 0xD4, 0xA3)
WIP = (0xE1, 0x96, 0x58)
RING = (0x9A, 0x9D, 0xA4)
VAL = (0xA2, 0x1F, 0xF0)
SUP = (0xD7, 0xB4, 0xFB)
RTK = (0xC9, 0x44, 0x52)
RTK_T = (0x99, 0x16, 0x16)
WHITE = (0xFF, 0xFF, 0xFF)
INK = (0x3B, 0x16, 0x80)
GREY = (0x8C, 0x8F, 0x96)

C = SIZE / 2
H = 15.5  # the diamond's half side: a keyframe, as the page's
RAD = 6.5  # its corners
W = 4  # an outline's width


def _diamond_dist(x, y, h=H, r=RAD):
    """Signed distance to the rounded square turned 45 degrees."""
    u = ((x - C) + (y - C)) / math.sqrt(2)
    v = ((x - C) - (y - C)) / math.sqrt(2)
    qx, qy = abs(u) - h + r, abs(v) - h + r
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def diamond(h=H):
    return lambda x, y: _diamond_dist(x, y, h) <= 0


def outline(width=W, gap=None):
    """The diamond's outline; gap: (from, to) degrees left open."""

    def inside(x, y):
        if not -width <= _diamond_dist(x, y) <= 0:
            return False
        if gap:
            a = math.degrees(math.atan2(C - y, x - C)) % 360
            return not gap[0] <= a <= gap[1]
        return True

    return inside


def lower_half(x, y):
    return y >= C and _diamond_dist(x, y) <= 0


def segment(ax, ay, bx, by, width):
    def inside(x, y):
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(x - ax - t * dx, y - ay - t * dy) <= width / 2

    return inside


def triangle(points):
    (ax, ay), (bx, by), (cx, cy) = points

    def side(px, py, qx, qy, x, y):
        return (qx - px) * (y - py) - (qy - py) * (x - px)

    def inside(x, y):
        s = (side(ax, ay, bx, by, x, y), side(bx, by, cx, cy, x, y), side(cx, cy, ax, ay, x, y))
        return all(v >= 0 for v in s) or all(v <= 0 for v in s)

    return inside


def rect(x0, y0, x1, y1, r=4):
    def inside(x, y):
        qx = abs(x - (x0 + x1) / 2) - (x1 - x0) / 2 + r
        qy = abs(y - (y0 + y1) / 2) - (y1 - y0) / 2 + r
        return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r <= 0

    return inside


def check(width=5):
    """A ✓ in the diamond."""
    a, b = segment(C - 8, C + 1, C - 2, C + 7, width), segment(C - 2, C + 7, C + 9, C - 6, width)
    return lambda x, y: a(x, y) or b(x, y)


# The reworked diamond: open on its top-left edge (135 degrees), the
# stroke's end an arrowhead -- clockwise, as the page's.
_GAP = (122, 150)
_TIP = (C - 15.5, C - 3)  # where the stroke ends, left of the gap
_ARROW = triangle([(_TIP[0] - 7, _TIP[1] + 4), (_TIP[0] + 6, _TIP[1] + 4), (_TIP[0] - 1, _TIP[1] - 8)])

# name -> its layers, drawn in order: (colour, shape).
MARKS = {
    # A department's state, as the page's keyframe diamonds.
    "todo": [(RING, outline())],
    "wip": [(WIP, outline()), (WIP, lower_half)],
    "rework": [(WIP, outline(gap=_GAP)), (WIP, _ARROW)],
    "done": [(DONE, diamond())],
    # Validated: by a role (sup), by the top one (prod).
    "valid": [(SUP, diamond()), (INK, check())],
    "done_top": [(VAL, diamond()), (WHITE, check())],
    # The stages: waiting on an earlier one (a clock in the diamond), to
    # redo -- to rework, to check -- (the diamond an eye, its pupil).
    "waiting": [(RING, outline()), (RING, segment(C, C, C, C - 10, 4)), (RING, segment(C, C, C + 8, C, 4))],
    "to_redo": [(WIP, outline()), (WIP, lambda x, y: math.hypot(x - C, y - C) <= 6.5)],
    # A department not required for the file.
    "none": [(GREY, segment(C - 9, C, C + 9, C, 4))],
    # Entries, as the page's post-its: a retake from a validation role
    # (red), from the team (outlined); a note under a role (violet).
    "rtk": [(RTK, rect(8, 18, 56, 46, 6))],
    "team": [(RTK, lambda x, y: rect(8, 18, 56, 46, 6)(x, y) and not rect(13, 23, 51, 41, 3)(x, y))],
    "role": [(VAL, rect(8, 18, 56, 46, 6))],
}


def render(layers) -> bytes:
    rows = []
    step = 1 / SAMPLES
    for py in range(SIZE):
        row = bytearray([0])  # filter: none
        for px in range(SIZE):
            r = g = b = a = 0.0
            for colour, shape in layers:
                hits = sum(
                    shape(px + (i + 0.5) * step, py + (j + 0.5) * step)
                    for i in range(SAMPLES)
                    for j in range(SAMPLES)
                )
                cover = hits / SAMPLES**2
                if cover:
                    # Over what's below.
                    out = cover + a * (1 - cover)
                    r = (colour[0] * cover + r * a * (1 - cover)) / out
                    g = (colour[1] * cover + g * a * (1 - cover)) / out
                    b = (colour[2] * cover + b * a * (1 - cover)) / out
                    a = out
            row += bytes((round(r), round(g), round(b), round(a * 255)))
        rows.append(bytes(row))
    return b"".join(rows)


def png(pixels: bytes) -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels, 9)) + chunk(b"IEND", b"")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, layers in MARKS.items():
        (OUT / f"{name}.png").write_bytes(png(render(layers)))
    print(f"{len(MARKS)} marks in {OUT}")


if __name__ == "__main__":
    main()
