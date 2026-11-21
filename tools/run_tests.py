"""Run every tests/test_*.py, each in its own Python (the fake bpy and the
addon loaded fresh), and say which failed. Exit code 1 if any did.

    python3 tools/run_tests.py
"""

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    failed = []
    for test in sorted((REPO / "tests").glob("test_*.py")):
        start = time.monotonic()
        run = subprocess.run([sys.executable, str(test)], cwd=REPO, capture_output=True, text=True)
        took = time.monotonic() - start
        ok = run.returncode == 0
        print(f"{'ok  ' if ok else 'FAIL'} {test.name} ({took:.1f} s)")
        if not ok:
            failed.append(test.name)
            print(run.stdout[-3000:] + run.stderr[-3000:])
    print(f"\n{len(failed)} failed: {', '.join(failed)}" if failed else "\nall passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
