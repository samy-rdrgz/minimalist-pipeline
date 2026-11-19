"""1C: dates with their offset, without Blender (tools/fake_bpy.py).

    python3 tests/test_dates.py          # several time zones: see main()
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def run() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    core = sys.modules[f"{pkg.__name__}.lib.core"]
    migration = sys.modules[f"{pkg.__name__}.lib.migration"]
    tracking = sys.modules[f"{pkg.__name__}.lib.monitoring.tracking"]
    tz = os.environ.get("TZ", "")

    # now(): local, with its offset, read back as written.
    stamp = core.now()
    assert stamp[-6] in "+-" and stamp[-3] == ":", stamp
    assert core.parse_iso(stamp).tzinfo is not None
    assert core.now(False).tzinfo is not None

    # parse_iso(): every form aware, absent / unreadable None.
    naive = core.parse_iso("2026-11-14T10:03:00")
    assert naive.tzinfo is not None and (naive.hour, naive.minute) == (10, 3), naive
    other = core.parse_iso("2026-11-14T10:03:00+09:00")
    assert other == datetime(2026, 11, 14, 1, 3, tzinfo=timezone.utc), other
    assert other.utcoffset() == naive.utcoffset()  # shown in this machine's zone
    epoch = core.parse_iso(1_700_000_000)
    assert epoch.timestamp() == 1_700_000_000
    for empty in (None, "", "garbage", True, False):
        assert core.parse_iso(empty) is None, empty
    # The calendar's ends: no overflow whatever the zone.
    assert core.parse_iso("0001-01-01T00:00:00") is not None
    assert core.parse_iso(core.EARLIEST.isoformat()) is not None
    assert core.parse_iso(core.EARLIEST.isoformat()) < naive < core.LATEST
    # An old date and a new one compared: no TypeError.
    assert (naive < other) == (naive.timestamp() < other.timestamp())

    # Ordered by time, never by text: 10:00 in Karachi is before 06:00 UTC.
    early, late = "2026-11-14T10:00:00+05:00", "2026-11-14T06:00:00+00:00"
    assert sorted([late, early]) == [late, early]  # text: wrong
    assert sorted([late, early], key=core.time_key) == [early, late]
    assert core.time_key("") == float("-inf") and core.time_key(None) == float("-inf")
    # Daylight saving's repeated hour (Paris, 25/10/2026): 02:30 summer time
    # is before 02:10 winter time.
    a, b = "2026-10-25T02:30:00+02:00", "2026-10-25T02:10:00+01:00"
    assert sorted([b, a], key=core.time_key) == [a, b]
    assert core.parse_iso(b) - core.parse_iso(a) == timedelta(minutes=40)

    # seconds_since(): epoch heartbeats and ISO times alike.
    assert abs(core.seconds_since(time.time() - 30) - 30) < 2
    assert abs(core.seconds_since(core.now()) - 0) < 2
    nine = (datetime.now(timezone.utc) - timedelta(seconds=90)).astimezone(timezone(timedelta(hours=9)))
    assert abs(core.seconds_since(nine.isoformat()) - 90) < 2, "a heartbeat from Tokyo"
    assert core.seconds_since("") is None

    # local_time(): this machine's hour, never the text cut.
    shown = core.local_time("2026-11-14T10:03:00+09:00")
    assert shown == f"{other:%Y-%m-%d %H:%M}", shown
    assert core.local_time("") == "" and core.local_time("bad") == "bad"
    assert core.local_time("2026-11-14T10:03:00") == "2026-11-14 10:03"

    # file_time(): an mtime comparable with the dates read.
    assert core.file_time(time.time()) > naive
    assert core.file_time(1e20) is None

    # The migration: every naive date and time given this machine's offset,
    # a day alone and an aware date left as they are.
    data = {
        "created_at": "2026-11-14T10:03:00",
        "edited_at": "2026-11-14T10:03:00.250000",
        "done_at": "2026-11-14T10:03:00+09:00",
        "day": "2026-11-14",
        "text": "2026-11-14T10:03:00 is in a note",
        "entries": [{"at": "2026-07-01T12:00:00"}, "2026-01-01T00:00"],
    }
    assert migration._migrate_dates(data) == 4
    assert core.parse_iso(data["created_at"]) == naive
    assert data["created_at"].startswith("2026-11-14T10:03:00") and len(data["created_at"]) == 25
    assert data["edited_at"].startswith("2026-11-14T10:03:00.250000")
    assert data["done_at"] == "2026-11-14T10:03:00+09:00"
    assert data["day"] == "2026-11-14" and data["text"].endswith("note")
    # Summer and winter: each date its own offset (Paris: +02:00, then +01:00).
    if tz == "Europe/Paris":
        assert data["entries"][0]["at"].endswith("+02:00"), data
        assert data["entries"][1].endswith("+01:00"), data
        assert data["created_at"].endswith("+01:00"), data
    assert migration._migrate_dates(data) == 0  # once only

    # A folder's status from mixed dates: an old wipmeta (naive), a stable
    # written in another zone -- no TypeError, the order by time.
    with tempfile.TemporaryDirectory() as d:
        owner = Path(d) / "assets" / "chr" / "chr_bob"
        pipe = owner / ".pipeline"
        pipe.mkdir(parents=True)
        (pipe / "tracking.json").write_text(json.dumps({
            "departments_required": ["modeling", "shading"],
            "entries": [
                {"id": "a1", "type": "rtk", "text": "x", "done": False,
                 "created_at": "2026-11-14T09:00:00+09:00", "departments": ["modeling"]},
                {"id": "a2", "type": "rtk", "text": "y", "done": False,
                 "created_at": "2026-11-13T23:30:00", "departments": ["modeling"]},
            ],
        }))
        stable_at = datetime.now(timezone.utc) - timedelta(hours=2)
        (pipe / "chr_bob_v002-stable_001.stablemeta").write_text(json.dumps({
            "file": "chr_bob_v002-stable_001.blend",
            "created_at": stable_at.astimezone(timezone(timedelta(hours=-5))).isoformat(),
            "departments_done": {"modeling": True},
            "departments_started": ["modeling"],
        }))
        (pipe / "chr_bob_v003.wipmeta").write_text(json.dumps({
            "file": "chr_bob_v003.blend",
            "edited_at": (stable_at + timedelta(hours=1)).astimezone().replace(tzinfo=None).isoformat(timespec="seconds"),
            "departments_worked": {"me": ["shading"]},
        }))
        raw = tracking._collect_folder(owner)
        assert raw and raw["last_stable"]["file"].endswith("stable_001.blend"), raw
        status = tracking._status_from_raw(raw)
        assert status["last_saved_at"], status
        # Saved an hour after a stable written five hours behind UTC: worked since.
        assert list(status["worked_departments"]) == ["shading"], status
    print(f"OK: dates ({tz or 'system zone'})")


def main() -> int:
    if os.environ.get("_DATES_CHILD"):
        run()
        return 0
    failed = 0
    for tz in ("Europe/Paris", "America/New_York", "Asia/Tokyo", "UTC"):
        env = dict(os.environ, TZ=tz, _DATES_CHILD="1")
        done = subprocess.run([sys.executable, __file__], env=env)
        failed += done.returncode != 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
