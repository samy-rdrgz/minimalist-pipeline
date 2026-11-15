"""Blender's own icons, tinted: a few of its SVGs (trailers/icons) drawn
white on black by a headless Firefox, their light read as coverage, then
written in a colour as the add-on's marks (icons/<name>.png, 64 px, the
icon's whole frame -- the same size as Blender's own beside them). See
NOTES.md, "Coloured marks".

    python3 tools/tint_icons.py
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_icons import OUT, SIZE, VAL, png  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "trailers" / "icons"
# mark name -> (Blender's icon, colour)
TINTED = {
    "box_role": ("checkbox_dehlt", VAL),
    "check_role": ("checkmark", VAL),  # as CHECKMARK, a done one
    "dot_role": ("layer_used", VAL),
}
# Blender's icon cell, in its SVGs' units: each SVG is cropped to its
# drawing (checkbox 1200, layer_used 800) and centred in it -- a mark's
# PNG fills the cell, so the SVG is put back in the middle of one.
CELL = 1600


def _svg(name: str) -> str:
    """The icon's SVG, white, centred in Blender's icon cell (CELL)."""
    svg = (SOURCE / f"blender_icon_{name}.svg").read_text()
    svg = re.sub(r"<sodipodi:namedview\b.*?</sodipodi:namedview>", "", svg, flags=re.S)
    # Its dimming (an unticked box at 55 %) left out: the colour says enough.
    svg = re.sub(r'\sopacity="[^"]*"', "", svg)
    w, h = (float(v) for v in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups())
    box = f"{-(CELL - w) / 2} {-(CELL - h) / 2} {CELL} {CELL}"
    svg = re.sub(r'viewBox="[^"]+"', f'viewBox="{box}"', svg, count=1)
    return re.sub(r'(height|width)="[\d.]+"', f'\\1="{SIZE}"', svg)


def main() -> None:
    names = list(TINTED)
    html = '<body style="margin:0;background:#000;display:flex">' + "".join(
        f'<div style="width:{SIZE}px;height:{SIZE}px">{_svg(TINTED[n][0])}</div>' for n in names
    ) + "</body>"
    with tempfile.TemporaryDirectory() as tmp:
        page, shot = Path(tmp) / "icons.html", Path(tmp) / "icons.png"
        page.write_text(html)
        profile = Path(tmp) / "profile"
        profile.mkdir()
        for _ in range(2):  # a fresh profile's first run may exit early
            subprocess.run(
                ["firefox", "--headless", "--profile", str(profile), "--no-remote",
                 f"--window-size={SIZE * len(names)},{SIZE}", "--screenshot", str(shot), page.as_uri()],
                capture_output=True, timeout=90,
            )
            if shot.exists():
                break
        from PIL import Image

        im = Image.open(shot).convert("L")
    for i, n in enumerate(names):
        colour = TINTED[n][1]
        rows = []
        for y in range(SIZE):
            row = bytearray([0])
            for x in range(SIZE):
                row += bytes((*colour, im.getpixel((i * SIZE + x, y))))
            rows.append(bytes(row))
        (OUT / f"{n}.png").write_bytes(png(b"".join(rows)))
    print(f"{len(names)} tinted icons in {OUT}")


if __name__ == "__main__":
    main()
