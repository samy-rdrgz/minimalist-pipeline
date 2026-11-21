"""The snapshot and live pages the doc screenshots are taken of (tools/doc_screenshots/README.md).

    python3 tools/doc_screenshots/build_pages.py out.html [live]
"""
import importlib, json, random, sys
from datetime import date, timedelta
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import fake_bpy
fake_bpy.install()
pkg = fake_bpy.load()
page = importlib.import_module(f"{pkg.__name__}.lib.monitoring.snapshot_page")
plog = importlib.import_module(f"{pkg.__name__}.lib.monitoring.progress_log")
live = len(sys.argv) > 2 and sys.argv[2] == "live"
snap = json.loads((REPO / "tests/fixtures/snapshot_demo.json").read_text())
now = plog.figures(snap)
rnd = random.Random(7)
end = date(2026, 11, 16)
N = 70
days = {}
def scale(v, t):
    return None if v is None else round(v * t, 4)
for i in range(N):
    d = end - timedelta(days=N - 1 - i)
    t = ((i + 1) / N) ** 1.4
    pt = {}
    for kind, f in now.items():
        tv = max(0.0, t - 0.15) / 0.85
        pt[kind] = {"done": scale(f["done"], t), "validated": scale(f["validated"], tv),
                    "departments": {dep: {"done": scale(x["done"], min(1, t * (1.1 if j == 0 else 0.95))),
                                          "validated": scale(x["validated"], tv)}
                                    for j, (dep, x) in enumerate(f["departments"].items())}}
    weekend = d.weekday() >= 5
    worked = {}
    if not weekend:
        for kind, f in now.items():
            deps = list(f["departments"])
            worked[kind] = {dep: rnd.randint(0, 3) for dep in deps if rnd.random() < 0.55}
            worked[kind] = {k: v for k, v in worked[kind].items() if v}
    pt["worked"] = worked
    pt["seconds"] = 0 if weekend else rnd.randint(4, 14) * 1800
    pt["people"] = 0 if weekend else rnd.randint(1, 3)
    days[d.isoformat()] = pt
snap["meta"]["history"] = days
sched = importlib.import_module(f"{pkg.__name__}.lib.monitoring.schedule")
raw = {"start": "2026-09-01", "end": "2027-02-26", "days_off": []}
sc = {"start": date(2026, 9, 1), "end": date(2027, 2, 26), "days_off": [], "worked_days": [0, 1, 2, 3, 4]}
snap["meta"]["schedule"] = sched.schedule_progress(sc, end, {"shot": now["shots"]["done"], "asset": now["assets"]["done"]})
data = page.page_data(snap)
data["farm"] = json.loads((REPO / "tests/fixtures/snapshot_demo_farm.json").read_text())
if live:
    data["meta"]["live"] = {"token": "demo", "user": "samyr", "role": "prod", "root": "/projects/alive", "beginner": False, "version": 1}
    data["meta"]["videos"] = {"mode": "live", "base": None, "files": [], "local": "media/demo/renders"}
    data["meta"]["presence"] = [
        {"user": "léa", "machine": "c3d4e5f6", "uuid": "c3d4e5f6a1b2", "file": "sq030_sh040_v005", "saved": True},
        {"user": "samyr", "machine": "0d13d440", "uuid": "0d13d4405afa", "file": "sq900_sh120_v003", "saved": False},
        {"user": "tom", "machine": "9f8e7d6c", "uuid": "9f8e7d6c5b4a", "file": "ch_bob_v004", "saved": True}]
Path(sys.argv[1]).write_text(page.render_page(data), encoding="utf-8")
