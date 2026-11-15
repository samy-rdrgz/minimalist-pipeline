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
VAL = (0x8C, 0x54, 0x8C)
SUP = (0xC9, 0xA1, 0xC9)
RTK = (0xC9, 0x44, 0x52)
RTK_T = (0x99, 0x16, 0x16)
WHITE = (0xFF, 0xFF, 0xFF)
INK = (0x3D, 0x23, 0x40)
GREY = (0x8C, 0x8F, 0x96)
CYAN = (0x00, 0xC3, 0xC3)  # the farm rendering (the brief keeps it for that)

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
_GAP = (118, 150)


def _edge_point(angle):
    """Where the outline's middle (2 px in) crosses angle (degrees, y up)
    on the top-left edge."""
    dx, dy = math.cos(math.radians(angle)), -math.sin(math.radians(angle))
    t = -(H - W / 2) * math.sqrt(2) / (dx + dy)
    return C + dx * t, C + dy * t


# The arrowhead: from the stroke's end (the gap's lower side), pointing
# along the edge, up and right -- clockwise -- into the gap.
_END = _edge_point(_GAP[1])
_D, _N = (1 / math.sqrt(2), -1 / math.sqrt(2)), (1 / math.sqrt(2), 1 / math.sqrt(2))
_ARROW = triangle([
    (_END[0] - _D[0] + _N[0] * 5.5, _END[1] - _D[1] + _N[1] * 5.5),
    (_END[0] - _D[0] - _N[0] * 5.5, _END[1] - _D[1] - _N[1] * 5.5),
    (_END[0] + _D[0] * 7.5, _END[1] + _D[1] * 7.5),
])

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
    # The farm's jobs, Project monitoring's Farm column and Farm
    # monitoring: submitted, queued (a clock), between two steps (half),
    # rendering (full), failed (red, a cross), finished and to check (an eye).
    "job_pending": [(RING, outline()), (RING, lambda x, y: math.hypot(x - C, y - C) <= 3.5)],
    "job_queued": [(CYAN, outline()), (CYAN, segment(C, C, C, C - 10, 4)), (CYAN, segment(C, C, C + 8, C, 4))],
    "job_waiting": [(CYAN, outline()), (CYAN, lower_half)],
    "job_running": [(CYAN, diamond())],
    "job_failed": [(RTK, diamond()), (WHITE, segment(C - 6, C - 6, C + 6, C + 6, 4.5)), (WHITE, segment(C - 6, C + 6, C + 6, C - 6, 4.5))],
    "job_check": [(DONE, outline()), (DONE, lambda x, y: math.hypot(x - C, y - C) <= 6.5)],
    # A retake on no department, as the page's post-it.
    "rtk": [(RTK, rect(8, 18, 56, 46, 6))],
}


# An open retake on a department: its state's mark smaller, raised, the
# retake's red post-it under it -- one icon, as the page's diamond and its
# post-it (Project monitoring's cells: a mark beside it cut the words).
def _moved(shape, scale=0.7, dy=-9):
    return lambda x, y: shape(C + (x - C) / scale, C + (y - C - dy) / scale)


_POSTIT = rect(13, 47, 51, 61, 3.5)
for _state in ("todo", "wip", "rework", "done", "valid", "done_top", "waiting", "to_redo"):
    MARKS[f"{_state}_rtk"] = [(col, _moved(shape)) for col, shape in MARKS[_state]] + [(RTK, _POSTIT)]

# A note's dot when written under a validation role: violet, as the
# page's review colour (its tick boxes: Blender's own, tinted --
# tools/tint_icons.py).
MARKS["dot_role"] = [(VAL, lambda x, y: math.hypot(x - C, y - C) <= 9)]


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
