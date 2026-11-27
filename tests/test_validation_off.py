"""A project without validation (Project settings › Validation unticked,
"validation": false): no role at all, its roles kept for when it's ticked
again; the page told so (val_on) -- without Blender.

    python3 tests/test_validation_off.py
"""

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load().__name__
    config = importlib.import_module(f"{pkg}.lib.config")
    page = importlib.import_module(f"{pkg}.lib.monitoring.snapshot_page")
    roles = [{"name": "sup", "level": 1}, {"name": "prod", "level": 2}]
    assert [r["name"] for r in config.validation_roles({"validation_roles": roles})] == ["sup", "prod"]
    assert config.validation_roles({"validation_roles": roles, "validation": False}) == []
    # Absent: on, as before 2.1.
    assert config.validation_roles({"validation_roles": roles, "validation": True})
    meta = page.page_data({"meta": {"validation_on": False}, "shots": [], "assets": [], "notes": []})["meta"]
    assert meta["val_on"] is False and meta["roles"] == [], meta
    assert page.page_data({"meta": {}, "shots": [], "assets": [], "notes": []})["meta"]["val_on"] is True
    print("validation off: ok")


if __name__ == "__main__":
    main()
