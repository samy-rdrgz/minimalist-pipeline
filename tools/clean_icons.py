"""Blender's icons (SVGs exported from Inkscape, white) into the snapshot
page's: templates/snapshot/icons/<name>.svg, their Inkscape data and ids
gone, their white the text's colour (currentColor). The page takes those
it names (lib/snapshot_page.py icon_sprite()). See NOTES.md, "Snapshot
page v3".

    python3 tools/clean_icons.py [source folder, default trailers/icons]
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "templates" / "snapshot" / "icons"

_DROP = [
    re.compile(r"<sodipodi:namedview\b[^>]*?>.*?</sodipodi:namedview>", re.S),
    re.compile(r"<sodipodi:namedview\b[^>]*/>", re.S),
    re.compile(r"<inkscape:[^>]*/>", re.S),
    re.compile(r"\s(?:id|inkscape:[\w-]+|sodipodi:[\w-]+|xmlns:\w+)=\"[^\"]*\""),
]
_WHITE = re.compile(r"(fill|stroke)(=\"|:)\s*#(?:fff|ffffff)\b", re.I)


def clean(svg: str) -> str:
    """One icon: <svg viewBox="..."> and its shapes, nothing else."""
    for rx in _DROP:
        svg = rx.sub("", svg)
    svg = _WHITE.sub(lambda m: f"{m[1]}{m[2]}currentColor", svg)
    view = re.search(r"viewBox=\"([^\"]+)\"", svg)
    inner = re.search(r"<svg\b[^>]*>(.*)</svg>", svg, re.S)
    if not view or not inner:
        raise ValueError("no viewBox or no content")
    body = re.sub(r">\s+<", "><", inner[1].strip())
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view[1]}">{body}</svg>\n'


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "trailers" / "icons"
    OUT.mkdir(exist_ok=True)
    n = 0
    for path in sorted(source.glob("*.svg")):
        name = path.stem.removeprefix("blender_icon_")
        (OUT / f"{name}.svg").write_text(clean(path.read_text()))
        n += 1
    print(f"{n} icons in {OUT}")


if __name__ == "__main__":
    main()
