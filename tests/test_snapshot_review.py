"""The snapshot page's review, there and back: changes made in the page
(its A.* actions, as a click makes them) written as the review's file,
read by lib/monitoring/review_import.py read_review() without losing one; kept
across a reload; loaded back into the page (fromActions()) as the same
actions. Needs Node and Playwright (a browser); skipped without them.

    python3 tests/test_snapshot_review.py
"""

import importlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

SCRIPT = r"""
const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();const p=await b.newPage();const errs=[];
p.on('pageerror',e=>errs.push(e.message));
await p.goto('file://'+process.argv[2]);
const out=await p.evaluate(()=>{const {S,items,A,reviewFile}=MPPage;S.review={name:'Léa',role:'prod'};
  const it=items.find(i=>i.name==='sq030_sh060'),j=items.find(i=>i.name==='sq030_sh040');
  const [d1,d2]=Object.keys(j.states);A.validate(j,d1);A.note(j,{type:'rtk',dept:d2,text:'the ball goes through',frames:'f12-23'});
  A.note(it,{type:'note',dept:null,text:'nice',frames:'f4'});const n=j.notes.find(x=>!x.closed);A.reply(j,n.id,'fixed it');A.fixed(j,n.id);
  A.note(it,{type:'todo',dept:null,text:'clean the keys'});const c=it.notes.find(x=>x.done&&x.type!=='note');if(c)A.fixed(it,c.id,true);
  A.still(it,Object.keys(it.states)[0]);A.toggleReq(it,'layout');A.omit(it,'on_hold','client');A.assignToggle(j,d1,'tom');A.desc(j,'New description');
  A.plan({name:'sq030_sh090',g:'sq030',kind:'shot',desc:'new',deps:['layout']});MPPage.refresh();return reviewFile()});
await p.reload();
const kept=await p.evaluate(()=>MPPage.reviewActions());
const back=await p.evaluate(acts=>{const {items,S}=MPPage;items.forEach(it=>{it.mine={};it.myNotes=[];it.myReplies={};it.setAside=undefined;it.req=null;it.assign=null;it.still={};it.fixed={};delete it.descEdit});
  S.planned=[];MPPage.fromActions(acts);return MPPage.reviewActions()},out.actions);
console.log(JSON.stringify({errs,out,kept,back}));await b.close();})();
"""


def main() -> None:
    node = shutil.which("node")
    if not node or subprocess.run([node, "-e", "require('playwright')"], capture_output=True).returncode:
        print("OK: snapshot review (Node or Playwright not found: skipped)")
        return
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load().__name__
    page = importlib.import_module(f"{pkg}.lib.monitoring.snapshot_page")
    review_import = importlib.import_module(f"{pkg}.lib.monitoring.review_import")
    demo = json.loads((Path(__file__).parent / "fixtures" / "snapshot_demo.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        html, js, rv = Path(tmp) / "page.html", Path(tmp) / "run.js", Path(tmp) / "review.json"
        html.write_text(page.render_html(demo), encoding="utf-8")
        js.write_text(SCRIPT, encoding="utf-8")
        res = json.loads(subprocess.run([node, str(js), str(html)], check=True, capture_output=True, text=True).stdout)
        assert not res["errs"], res["errs"]
        out = res["out"]
        types = sorted(a["type"] for a in out["actions"])
        want = ["validate", "unvalidate", "rtk", "note", "todo", "reply", "fixed", "still_done",
                "departments", "assign", "omit", "description", "create"]
        if "reopen" in types:  # a closed retake or to-do in the demo: opened again
            want.append("reopen")
        assert types == sorted(want), types
        rv.write_text(json.dumps(out), encoding="utf-8")
        read = review_import.read_review(rv)
        assert len(read["actions"]) == len(out["actions"]), (len(read["actions"]), out["actions"])
        assert read["author"] == "Léa" and read["role"] == "prod"
        rtk = next(a for a in read["actions"] if a["type"] == "rtk")
        assert rtk["frames"] == (12, 23), rtk
        assert res["kept"] == out["actions"], "the review not kept across a reload"
        key = lambda a: json.dumps(a, sort_keys=True)  # noqa: E731
        assert sorted(map(key, res["back"])) == sorted(map(key, out["actions"])), "not the same once loaded back"
    print("OK: snapshot review")


if __name__ == "__main__":
    main()
