"""The snapshot page's sources put together (lib/snapshot_page.py
render_page()): the demo fixture rendered, every part listed is there and every file of css/ and js/
is listed, the page has no placeholder left, every word T() says has
its French (js/i18n/fr.js), its script parses, and T()
(js/core/01-i18n.js) says the English, the French, values and plurals. The
script's checks need Node; without it they are skipped (said so).

    python3 tests/test_snapshot_page.py
"""

import importlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    page = importlib.import_module(f"{fake_bpy.load().__name__}.lib.snapshot_page")
    for folder, parts in (("css", page.CSS_PARTS), ("js", page.JS_PARTS)):
        base = page.PAGE_DIR / folder
        on_disk = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}
        assert len(set(parts)) == len(parts), f"{folder}: a part listed twice"
        assert set(parts) == on_disk, (folder, sorted(set(parts) ^ on_disk))
    demo = json.loads((Path(__file__).parent / "fixtures" / "snapshot_demo.json").read_text(encoding="utf-8"))
    html = page.render_html(demo)
    assert '"name":"sq990_sh010"' in html, "the fixture's files not in the page"
    assert not re.search(r"\{\{[A-Z0-9_]+\}\}", html), "a placeholder left"
    # Every word the page says has its French (js/i18n/fr.js): the keys of
    # T('...') in the script, the data-t texts and labels of page.html.
    fr_keys = set(re.findall(r"^'((?:[^'\\]|\\.)*)':", (page.PAGE_DIR / "js" / "i18n" / "fr.js").read_text(encoding="utf-8"), re.M))
    script = page._parts("js", [p for p in page.JS_PARTS if not p.startswith("i18n/")])
    script = re.sub(r"/\*.*?\*/|^\s*//[^\n]*", "", script, flags=re.S | re.M)
    used = set(re.findall(r"\bT\('((?:[^'\\]|\\.)*)'", script))
    shell = (page.PAGE_DIR / "page.html").read_text(encoding="utf-8")
    used |= {t.strip().replace("'", "\\'") for t in re.findall(r"data-t>([^<]+)<", shell)}
    missing = sorted(k for k in used if k not in fr_keys)
    assert not missing, f"no French for: {missing}"
    node = shutil.which("node")
    if not node:
        print("OK: snapshot page (Node not found: its script not run)")
        return
    js = "(()=>{\n" + page._parts("js", page.JS_PARTS) + "})();\n"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "page.js"
        src.write_text(js, encoding="utf-8")
        subprocess.run([node, "--check", str(src)], check=True)
        i18n = (page.PAGE_DIR / "js" / "core" / "01-i18n.js").read_text(encoding="utf-8") + (
            page.PAGE_DIR / "js" / "i18n" / "fr.js"
        ).read_text(encoding="utf-8")
        cases = [
            ["en", "Cancel", None, "Cancel"],
            ["fr", "Cancel", None, "Annuler"],
            ["fr", "Not in the dictionary", None, "Not in the dictionary"],
            ["en", "{n} file|{n} files", {"n": 1}, "1 file"],
            ["en", "{n} file|{n} files", {"n": 0}, "0 files"],
            ["fr", "{n} file|{n} files", {"n": 0}, "0 fichier"],
            ["fr", "{n} file|{n} files", {"n": 3}, "3 fichiers"],
            ["en", "Sent to Blender: {what}", {"what": "sq030_sh040"}, "Sent to Blender: sq030_sh040"],
            ["de", "Cancel", None, "Cancel"],
        ]
        run = Path(tmp) / "i18n.js"
        run.write_text(
            "var localStorage={getItem:function(){return null;},setItem:function(){},removeItem:function(){}};\n"
            "var navigator={languages:['de-DE']};\n" + i18n + "\nvar bad=[];\n"
            f"{json.dumps(cases)}.forEach(function(c){{MPI18n.use(c[0]);var got=T(c[1],c[2]||undefined);"
            "if(got!==c[3])bad.push(c[0]+' '+c[1]+' -> '+got);});\n"
            "MPI18n.use(MPI18n.pick({lang:'fr_FR'}));if(MPI18n.lang!=='fr')bad.push('meta.lang not picked: '+MPI18n.lang);\n"
            "if(bad.length){console.error(bad.join('\\n'));process.exit(1);}\n",
            encoding="utf-8",
        )
        subprocess.run([node, str(run)], check=True)
    print("OK: snapshot page")


if __name__ == "__main__":
    main()
