"""config/presets/ in folders (lib/presets.py, lib/migration.py): a project
of before 2.0, its presets loose in presets/, read as they are; Migrate old
data moving each into render_shots/, render_assets/ or creation/ (a .json
rewritten there, the departments without one given theirs); the pickers by
kind; a rename following its department's kind; a second run finding
nothing -- without Blender.

    python3 tests/test_presets_layout.py
"""

import importlib
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def main() -> None:
    import fake_bpy

    fake_bpy.install()
    pkg = fake_bpy.load()
    core = importlib.import_module(f"{pkg.__name__}.lib.core")
    core.get_machine_id = lambda *a, **k: "test-machine"  # a MagicMock isn't JSON
    presets = importlib.import_module(f"{pkg.__name__}.lib.presets")
    migration = importlib.import_module(f"{pkg.__name__}.lib.migration")
    farm_ops = importlib.import_module(f"{pkg.__name__}.operators.farm_ops")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "proj"
        folder = root / "config" / "presets"
        (folder / "ffmpeg_presets").mkdir(parents=True)
        (folder / "ffmpeg_presets" / "default.json").write_text("{}")
        (root / "config" / "project_config.json").write_text(json.dumps({
            "shots_departments": ["anim", "lighting"],
            "assets_departments": ["modeling", "lookdev"],
            # Its name gives no department, set for lighting: a shot preset.
            "farm": {"department_presets": {"lookdev": "turntable"}},
        }))
        for name in ("anim_default", "modeling_default", "hd_final", "turntable"):
            (folder / f"{name}.py").write_text(f"# {name}\ndef override(scene, job_data):\n    pass\n")
        (folder / "lookdev_hd.json").write_text(json.dumps({"render.engine": "CYCLES"}))
        (folder / "asset_file_preset.py").write_text("# mine, edited\n")

        # Before the migration: every one read where it is.
        assert set(presets.render_presets(root)) == {"anim_default", "modeling_default", "hd_final", "turntable"}
        assert presets.render_preset_path("modeling_default", root) == folder / "modeling_default.py"
        assert presets.render_preset_path("asset_file_preset", root) is None, "a creation script isn't a render preset"
        assert presets.creation_preset_path("asset", root) == folder / "asset_file_preset.py"
        assert presets.creation_preset_path("shot", root) == folder / "creation" / "shot_file_preset.py"

        plan = migration._plan_presets(root)
        moves = {Path(a).name: Path(b).relative_to(folder).as_posix() for a, b in plan["move"]}
        assert moves == {
            "anim_default.py": "render_shots/anim_default.py",
            "modeling_default.py": "render_assets/modeling_default.py",
            "hd_final.py": "render_shots/hd_final.py",  # no department: shots
            "turntable.py": "render_assets/turntable.py",  # set for lookdev: assets
            "asset_file_preset.py": "creation/asset_file_preset.py",
        }, moves
        assert [Path(b).relative_to(folder).as_posix() for _, b in plan["json"]] == ["render_assets/lookdev_hd.py"]
        assert plan["shot_departments"] == ["lighting"] and plan["asset_departments"] == [], plan
        assert plan["loose"] == ["hd_final", "turntable"], plan["loose"]

        backup = root / "backup"
        errors: list = []
        written = migration._apply_presets(root, plan, backup, errors)
        assert not errors, errors
        assert written == 7, written  # 5 moved, 1 rewritten, lighting_default.py
        left = sorted(p.name for p in folder.iterdir())
        assert left == ["creation", "ffmpeg_presets", "render_assets", "render_shots"], left
        assert sorted(p.name for p in (folder / "render_shots").iterdir()) == ["anim_default.py", "hd_final.py", "lighting_default.py"]
        assert sorted(p.name for p in (folder / "render_assets").iterdir()) == ["lookdev_hd.py", "modeling_default.py", "turntable.py"]
        assert "scene.render.engine = 'CYCLES'" in (folder / "render_assets" / "lookdev_hd.py").read_text()
        assert (folder / "creation" / "asset_file_preset.py").read_text() == "# mine, edited\n"
        assert (backup / "config" / "presets" / "turntable.py").is_file() and (backup / "config" / "presets" / "lookdev_hd.json").is_file()
        assert presets.creation_preset_path("asset", root) == folder / "creation" / "asset_file_preset.py"

        # A second run: nothing.
        again = migration._plan_presets(root)
        assert not again["move"] and not again["json"] and not again["shot_departments"] and not again["asset_departments"], again

        # The pickers, by kind (render_presets() as the farm finds them).
        shot_items = [i[0] for i in farm_ops.pre_render_script_items(root, ["anim", "lighting"], "shot")]
        asset_items = [i[0] for i in farm_ops.pre_render_script_items(root, ["modeling", "lookdev"], "asset")]
        assert shot_items == ["NONE", "anim_default", "hd_final", "lighting_default"], shot_items
        assert asset_items == ["NONE", "lookdev_hd", "modeling_default", "turntable"], asset_items
        assert presets.render_preset_path("hd_final", root) == folder / "render_shots" / "hd_final.py"

        # A department added: its default in its kind's folder, never twice.
        made = presets.install_department_presets(["anim", "fx"], ["modeling", "groom"], root)
        assert made == ["fx_default.py", "groom_default.py"], made
        assert (folder / "render_shots" / "fx_default.py").is_file() and (folder / "render_assets" / "groom_default.py").is_file()
        assert presets.install_department_presets(["anim", "fx"], ["modeling", "groom"], root) == []

        # A rename: into the folder of its new name's department.
        assert presets.preset_rename_problem(root, "hd_final", "modeling_default") == "modeling_default.py already exists."
        presets.rename_preset(root, "hd_final", "lookdev_final", ["anim", "lighting", "modeling", "lookdev"])
        assert (folder / "render_assets" / "lookdev_final.py").is_file() and not (folder / "render_shots" / "hd_final.py").exists()
        # A name giving no department: it stays where it is.
        presets.rename_preset(root, "turntable", "spin", ["anim", "lighting", "modeling", "lookdev"])
        assert (folder / "render_assets" / "spin.py").is_file()
        assert presets.presets_without_department(root, ["anim", "lighting", "modeling", "lookdev", "fx", "groom"]) == ["spin"]

    # The shot preset: its collection, else CAM / SET / ASSETS (never raises).
    class Collection:
        pass

    class Preset:
        def __init__(self, result):
            self.result = result

        def build_collections(self, sequence, shots):
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

    presets.bpy.types.Collection = Collection
    fallback = Collection()
    presets._default_shot_collections = lambda: fallback
    mine = Collection()
    for loaded, expected in (
        (Preset(mine), mine),
        (Preset(RuntimeError("a typo in the script")), fallback),
        (Preset(None), fallback),  # no collection returned
        (presets.PipelineError("Preset script not found"), fallback),  # a project before 2.0
    ):
        def load(which, loaded=loaded):
            assert which == "shot"
            if isinstance(loaded, Exception):
                raise loaded
            return loaded

        presets.load_preset_module = load
        assert presets.shot_collections("sq010", [10, 20]) is expected
    template = (REPO / "templates" / "shot_file_preset.py").read_text(encoding="utf-8")
    assert "def build_collections(sequence: str, shots: list):" in template
    compile(template, "shot_file_preset.py", "exec")

    print("presets layout: ok")


if __name__ == "__main__":
    main()
