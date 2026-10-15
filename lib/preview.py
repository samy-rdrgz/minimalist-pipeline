"""Preview compilation providers: resolve which shots' mp4s go into a block
or sequence preview -- filesystem-only, no bpy needed."""

import re
from pathlib import Path

from .config import ConfigCache, json_get, parse_filename, shots_in_segment


def render_root(project_root: Path, owner_dir: Path) -> Path:
    """Render folder of an asset/shot folder: renders/<seq>/<shot> for a
    shot (no "shots/" level -- every shot reader expects it there),
    renders/assets/<prefix>/<asset> (or library/...) for the rest. Pure
    path work, no disk."""
    project_root, owner_dir = Path(project_root), Path(owner_dir)
    try:
        return project_root / "renders" / owner_dir.relative_to(project_root / "shots")
    except ValueError:
        return project_root / "renders" / owner_dir.relative_to(project_root)


def latest_render_dir(shot_dir: Path, v_prefix: str = "v") -> Path | None:
    """The shot's most recent render increment folder (v004-stable_002...),
    read from the folder names (not mtime). None if never rendered.
    Pure os: thread-safe."""
    pattern = re.compile(
        rf"^{re.escape(v_prefix)}(?P<num>\d+)(?:-[a-z]+)?_(?P<inc>\d+)$"
    )
    candidates = []
    try:
        for d in Path(shot_dir).iterdir():
            if d.is_dir() and (m := pattern.match(d.name)):
                candidates.append((int(m["num"]), int(m["inc"]), d))
    except OSError:
        return None
    return max(candidates)[2] if candidates else None


def latest_shot_mp4(
    project_root: Path, sequence_label: str, shot_label: str, config: dict | None = None
) -> Path | None:
    """The shot's most recently rendered mp4, read from the increment
    folder's own name (not mtime). None if never rendered, or no mp4 yet."""
    config = config if config is not None else ConfigCache.get()
    latest = latest_render_dir(
        project_root / "renders" / sequence_label / shot_label,
        json_get(config, "naming.version.prefix", "v"),
    )
    if latest is None:
        return None
    mp4s = sorted(latest.glob("*.mp4"))
    return mp4s[0] if mp4s else None


def resolve_block_sources(
    filepath: Path, project_root: Path, config: dict | None = None
) -> list[tuple[str, Path]]:
    """(shot_label, mp4) pairs for filepath's own block enumeration, in
    ascending shot order. Skips a shot with no compiled mp4 yet."""
    config = config if config is not None else ConfigCache.get()
    parsed = parse_filename(Path(filepath).name)
    naming = config.get("naming", {})
    if not parsed or not parsed.get("shot") or not naming:
        return []
    sequence_label = f"{naming['sequence']['prefix']}{parsed['sequence']}"
    shot_prefix = json_get(config, "naming.shot.prefix", "sh")
    shot_digits = json_get(config, "naming.shot.digits", 3)

    out = []
    for n in shots_in_segment(parsed["shot"]):
        shot_label = f"{shot_prefix}{n:0{shot_digits}d}"
        mp4 = latest_shot_mp4(project_root, sequence_label, shot_label, config)
        if mp4:
            out.append((shot_label, mp4))
    return out


def resolve_sequence_sources(
    sequence_label: str, project_root: Path, config: dict | None = None
) -> list[tuple[str, Path]]:
    """(shot_label, mp4) pairs for every shot ever rendered in the sequence
    ("sq030"), by shot number."""
    config = config if config is not None else ConfigCache.get()
    shot_prefix = json_get(config, "naming.shot.prefix", "sh")
    sequence_dir = project_root / "renders" / sequence_label
    if not sequence_dir.is_dir():
        return []

    pattern = re.compile(rf"^{re.escape(shot_prefix)}(?P<n>\d+)$")
    found = []
    for d in sequence_dir.iterdir():
        if d.is_dir() and (m := pattern.match(d.name)):
            found.append((int(m["n"]), d.name))
    found.sort()

    out = []
    for _n, shot_label in found:
        mp4 = latest_shot_mp4(project_root, sequence_label, shot_label, config)
        if mp4:
            out.append((shot_label, mp4))
    return out
