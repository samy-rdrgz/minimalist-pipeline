"""The snapshot page's component sheet (templates/snapshot/kit/): every
component drawn by the page's own CSS and render functions, measured in
the browser, with an audit of what falls outside the size tokens. Built
from the same parts as the page (lib/snapshot_page.py CSS_PARTS /
JS_PARTS), without its events and its start. Not part of the addon.

    python3 tools/snapshot_kit.py [data.json, default tests/fixtures/snapshot_demo.json] [out.html]
"""

import importlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parent.parent


def tokens(css: str) -> dict:
    """The tokens of 10-tokens.css: colours (dark, light) and sizes."""
    i = css.index(':root[data-ui="light"]')
    dark, light = css[:i], css[i:]
    lv = dict(re.findall(r"(--[\w-]+):\s*([^;]+);", light))
    color, size = [], []
    for line in dark.split("\n"):
        cm = re.search(r"/\*(.*?)\*/", line)
        c = cm.group(1).strip() if cm else ""
        for n, v in re.findall(r"(--[\w-]+):\s*([^;]+);", line):
            v = v.strip()
            if re.match(r"#|rgba?\(", v):
                color.append({"n": n, "dark": v, "light": lv.get(n, ""), "c": c})
            elif re.match(r"--(sp-|h-|u$|r$|r-|fs|unit)", n):
                size.append({"n": n, "v": v, "c": c})
    return {"color": color, "size": size}


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    page = importlib.import_module(f"{fake_bpy.load().__name__}.lib.snapshot_page")
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "tests" / "fixtures" / "snapshot_demo.json"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("snapshot_kit.html")
    data = page.page_data(json.loads(src.read_text(encoding="utf-8")))
    # The farm as the live page adds it (lib/live.py _farm_data()): the demo's.
    data["farm"] = json.loads((REPO / "tests" / "fixtures" / "snapshot_demo_farm.json").read_text(encoding="utf-8"))
    kit = page.PAGE_DIR / "kit"
    parts = [p for p in page.JS_PARTS if not p.startswith("desktop/29") and p != "boot.js"]
    js = page._parts("js", parts) + "\n/* ==== kit/kit.js ==== */\n" + (kit / "kit.js").read_text(encoding="utf-8")
    shell = (page.PAGE_DIR / "page.html").read_text(encoding="utf-8")
    own = shell[shell.index("<svg width=\"0\""):shell.index("</svg>") + 6]
    logo = (page.PAGE_DIR / "logo.svg").read_text(encoding="utf-8")
    own = own.replace("{{LOGO_VB}}", page._VIEWBOX.search(logo)[1]).replace("{{LOGO_PATH}}", page._PATH.search(logo)[1])
    css = page._parts("css", page.CSS_PARTS)
    html = (
        (kit / "kit.html").read_text(encoding="utf-8")
        .replace("{{CSS}}", css)
        .replace("{{KITCSS}}", (kit / "kit.css").read_text(encoding="utf-8"))
        .replace("{{SPRITE}}", own + page.icon_sprite(shell + js))
        .replace("{{JS}}", js)
        .replace("{{TOKENS}}", json.dumps(tokens(css), ensure_ascii=False))
        .replace("{{DATA}}", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    )
    out.write_text(html, encoding="utf-8")
    print(out, len(html))


if __name__ == "__main__":
    main()
