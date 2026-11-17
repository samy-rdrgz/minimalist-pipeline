"""Blender's theme as the snapshot page's colours (lib/snapshot_theme.py):
a fake theme's fields read, the derived ones computed, a theme whose text
wouldn't read refused, and the page given them (meta.theme).

    python3 tests/test_snapshot_theme.py
"""

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load().__name__
    th = importlib.import_module(f"{pkg}.lib.snapshot_theme")
    page = importlib.import_module(f"{pkg}.lib.snapshot_page")
    assert th.hex_color((1, 0.5, 0, 1)) == "#ff8000"
    assert th.shade("#000000", 0.5) == "#808080" and th.shade("#ffffff", -0.5) == "#808080"
    assert round(th.contrast("#000000", "#ffffff"), 1) == 21.0
    grey = (0.17, 0.17, 0.17, 1.0)
    theme = NS(
        properties=NS(space=NS(back=grey, header=(0.15, 0.15, 0.15), text=(0.7, 0.7, 0.7))),
        user_interface=NS(wcol_regular=NS(inner=(0.33, 0.33, 0.33, 1), inner_sel=(0.28, 0.45, 0.7, 1), text=(0.9, 0.9, 0.9), text_sel=(1, 1, 1), outline=(0.24, 0.24, 0.24))),
    )

    def get(path):
        node = theme
        for part in path.split("."):
            node = getattr(node, part, None)
            if node is None:
                return None
        return tuple(node)

    v = th.theme_vars(get)
    assert v["--area"] == "#2b2b2b" and v["--sel"] == "#4773b2", v
    assert v["--btn-hi"] == th.shade(v["--btn"], 0.06) and "--canvas" not in v
    theme.user_interface.wcol_regular.text = (0.2, 0.2, 0.2)
    assert th.theme_vars(get) == {}, "dark text on a dark ground: refused"
    demo = json.loads((Path(__file__).parent / "fixtures" / "snapshot_demo.json").read_text(encoding="utf-8"))
    demo["meta"]["theme"] = v
    assert page.page_data(demo)["meta"]["theme"] == v
    print("OK: snapshot theme")


if __name__ == "__main__":
    main()
