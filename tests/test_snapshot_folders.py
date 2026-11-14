"""Phase 2: snapshots by month, the videos shared, the reviews kept.

    python3 tests/test_snapshot_folders.py
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import importlib

    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    snap = importlib.import_module(f"{pkg.__name__}.lib.snapshot")
    rev = importlib.import_module(f"{pkg.__name__}.lib.review_import")

    with tempfile.TemporaryDirectory() as d:
        snapshots = Path(d) / "snapshots"
        nov = datetime(2026, 11, 14, 10, tzinfo=timezone.utc)
        month = snap.month_folder(snapshots, nov)
        assert month == snapshots / "2026-11", month
        assert snap.month_folder(snapshots).name == datetime.now().strftime("%Y-%m")

        # Videos: one folder for every month; beside a page saved elsewhere,
        # or at snapshots/'s root (before 1.2).
        page = month / "p_snapshot_2026-11-14_10-00.html"
        assert snap.snapshot_videos_folder(page, snapshots) == snapshots / "videos"
        rel = Path(os.path.relpath(snapshots / "videos", page.parent)).as_posix()
        assert rel == "../videos", rel
        old = snapshots / "p_snapshot_2026-10-01_10-00.html"
        assert snap.snapshot_videos_folder(old, snapshots) == snapshots / "videos"  # beside, as before
        elsewhere = Path(d) / "Desktop" / "2026-11" / "p.html"
        assert snap.snapshot_videos_folder(elsewhere, snapshots) == elsewhere.parent / "videos"
        other = snapshots / "notes" / "p.html"
        assert snap.snapshot_videos_folder(other, snapshots) == other.parent / "videos"

        # Reviews kept by role and by their review date's month.
        downloads = Path(d) / "Downloads"
        downloads.mkdir()

        def review(name, date="2026-10-30", role="sup", rows=()):
            path = downloads / name
            path.write_text(json.dumps({
                "format": rev.REVIEW_JSON_FORMAT, "schema_version": rev.SCHEMA_VERSION, "author": "Ana",
                "role": role, "review_date": date, "rows": list(rows),
            }))
            return path

        a = review("p_review_2026-10-30_sup_ana.json")
        kept = rev.keep_review(a, snapshots, {"role": "sup"})
        assert kept == snapshots / "reviews" / "sup" / "2026-10" / a.name, kept
        assert kept.read_bytes() == a.read_bytes()
        # The same file again: not copied a second time.
        assert rev.keep_review(a, snapshots, {"role": "sup"}) == kept
        assert len(list(kept.parent.iterdir())) == 1
        # Another file under the same name: numbered.
        a.write_text(a.read_text().replace("Ana", "Ana B"))
        second = rev.keep_review(a, snapshots, {"role": "sup"})
        assert second.name == "p_review_2026-10-30_sup_ana_1.json", second
        assert rev.keep_review(a, snapshots, {"role": "sup"}) == second  # same again: found
        # Imported from reviews/ itself: nothing to keep.
        assert rev.keep_review(kept, snapshots, {"role": "sup"}) is None
        # The team, no role, a role with a slash, no readable date (now's month).
        t = review("team.json", role="team")
        assert rev.keep_review(t, snapshots, {"role": "team", "team": True}).parts[-3] == "team"
        n = review("norole.json", role="")
        assert rev.keep_review(n, snapshots, {"role": ""}).parts[-3] == "no-role"
        s = review("slash.json", role="a/b")
        assert rev.keep_review(s, snapshots, {"role": "a/b"}).parts[-3] == "a_b"
        bad = downloads / "bad.json"
        bad.write_text("{not json")
        assert rev.keep_review(bad, snapshots, {"role": "sup"}).parent.name == datetime.now().strftime("%Y-%m")
    print("OK: snapshot folders")


if __name__ == "__main__":
    main()
