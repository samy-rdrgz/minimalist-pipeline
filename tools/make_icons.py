"""Draw the add-on's coloured marks into icons/*.png -- Blender colours no
icon of its own (see NOTES.md, "Coloured marks"). The snapshot page's
marks and dark-theme colours (templates/snapshot/page.css). Pure Python:

    python3 tools/make_icons.py
"""

import math
import struct
import zlib
from pathlib import Path

SIZE = 64
SAMPLES = 4  # per side, per pixel: the edges smoothed
OUT = Path(__file__).resolve().parent.parent / "icons"

GREEN = (0x7D, 0xC4, 0x86)
AMBER = (0xE4, 0xAE, 0x4F)
RED = (0xF3, 0x6B, 0x6B)
GREY = (0x93, 0x92, 0x8B)
VIOLET = (0xC7, 0xA4, 0xF4)
ORANGE = (0xFF, 0xAB, 0x76)
BLUE = (0x9F, 0xAD, 0xFF)

C = SIZE / 2
R = 22  # a mark's radius: Blender's own icons keep a margin too


def disc(r, cx=C, cy=C):
    return lambda x, y: math.hypot(x - cx, y - cy) <= r


def ring(r, width):
    return lambda x, y: r - width <= math.hypot(x - C, y - C) <= r


def half(r):
    return lambda x, y: x <= C and math.hypot(x - C, y - C) <= r


def segment(ax, ay, bx, by, width):
    def inside(x, y):
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(x - ax - t * dx, y - ay - t * dy) <= width / 2

    return inside


def arc(r, width, start, end):
    """A ring from start to end degrees, counter-clockwise from 3 o'clock."""

    def inside(x, y):
        a = math.degrees(math.atan2(C - y, x - C)) % 360
        return start <= a <= end and r - width <= math.hypot(x - C, y - C) <= r

    return inside


def triangle(points):
    (ax, ay), (bx, by), (cx, cy) = points

    def side(px, py, qx, qy, x, y):
        return (qx - px) * (y - py) - (qy - py) * (x - px)

    def inside(x, y):
        s = (side(ax, ay, bx, by, x, y), side(bx, by, cx, cy, x, y), side(cx, cy, ax, ay, x, y))
        return all(v >= 0 for v in s) or all(v <= 0 for v in s)

    return inside


def _arrow_head():
    """The to_redo arc's head: at its end (3 o'clock), pointing on
    counter-clockwise, into the gap."""
    mid = R - 2.5
    px, py = C + mid, C
    return triangle([(px + 8, py + 1), (px - 8, py + 1), (px, py - 10)])


# name -> its layers, drawn in order: (colour, shape).
MARKS = {
    # A department's state, as the page's .m marks.
    "todo": [(GREY, ring(R, 4))],
    "wip": [(AMBER, ring(R, 4)), (AMBER, half(R))],
    "done": [(GREEN, disc(R))],
    "rework": [(GREEN, ring(R, 5)), (AMBER, disc(9))],
    # Validated by the top role: done, in the validation's violet ring.
    "done_top": [(VIOLET, ring(R + 6, 4)), (GREEN, disc(R - 3))],
    # The stages (lib/status.py stage_flags()).
    "waiting": [(BLUE, ring(R, 4)), (BLUE, segment(C, C, C, C - 14, 4)), (BLUE, segment(C, C, C + 10, C, 4))],
    "to_redo": [(ORANGE, arc(R, 5, 60, 360)), (ORANGE, _arrow_head())],
    # Entries: a retake, under a validation role, by the team.
    "rtk": [(RED, disc(R - 4))],
    "role": [(VIOLET, disc(R - 4))],
    "team": [(ORANGE, disc(R - 4))],
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
