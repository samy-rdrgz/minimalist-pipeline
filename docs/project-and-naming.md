# Project structure, naming, batch creation

*[← Documentation index](README.md) · [Version française](project-and-naming_fr.md)*

---

## The project

A project = a folder with `config/project_config.json` at its root. Structure enforced at creation, configurable in the wizard:

```
my_project/
├── config/
│   ├── project_config.json
│   ├── logs/pipeline_log.jsonl, sessions_log.jsonl
│   ├── presets/            ← Python preset for asset collections, ffmpeg presets
│   ├── .sessions/          ← who has what open, right now
│   └── .farm/               ← render queue, workers, monitor.lock
├── refs/
├── assets/
│   └── ch/
│       └── ch_bob/
│           └── .pipeline/   ← tracking.json, .wipmeta, .stablemeta
├── library/
│   └── mat/
│       └── mat_wood-dark/
├── shots/
│   └── sq010/sh010/
├── renders/
└── exports/
```

**Prefix routing**: the file's prefix determines its parent folder, the artist doesn't choose anything. `ch`/`pr`/`env` → `assets/`, `mat`/`gn`/`tech` → `library/`. Both prefix lists are configurable per project.

<br>

## Naming convention

```
{prefix}_{name}_v{number}[-{tag}].blend      # asset / library
{prefix}sq{n}_{prefix}sh{n}_v{number}[-{tag}].blend   # shot
```

- All lowercase. Underscore = structural separator (always 3 segments). Hyphen = words within a segment, and version tag.
- No tag = wip, implicitly.
- The parsing regex isn't hardcoded: it's **rebuilt dynamically from `project_config.json`** (prefixes, digits, allowed tags) on every config change.

A shot's multishot variant (several cuts sharing one file) extends this pattern — see [Shot blocks (multishot)](multishot.md).

<br>

## Batch creation

New assets/shots can also be created in bulk from a CSV file (Project panel's "Batch create from CSV", or the top bar menu). Each row is built in its own disposable headless Blender process — never the current session — so nothing accumulates between rows (no leftover collections from a previous one) and the artist's own work is never reset or touched. Rows are processed strictly one at a time, never in parallel.

- **Assets**: `prefix`, `name` required; `departments`, `description` optional.
- **Shots**: `sequence`, `shot` required; `frame_start`/`frame_end`/`frame_duration`, `departments`, `description` optional (`frame_end` takes precedence over `frame_duration` if both are given; neither touches the scene's own default frame range if omitted).
- `departments`: comma-separated department names. Falls back to the project's default set if the column is empty/missing; any name not found in the project's actually configured departments is skipped and logged as a warning — never blocks the row.
- A row matching an asset/shot that already exists (same prefix+name, or same sequence+shot) is silently skipped — batch creation never overwrites.

---

## Data structure: `project_config.json`

Written under a lock and atomically (temp file then rename), like every other pipeline JSON file (see [Design choices](design.md)). One per project, fully editable via "Edit project":

```json
{
  "project_name": "my_project",
  "pipeline_addon_version": "1.0.2",
  "blender_version": "(4, 2, 0)",
  "resolution": {"x": 1920, "y": 1080},
  "default_fps": 30,
  "default_frame_start": 1001,
  "naming": {
    "sequence": {"prefix": "sq", "digits": 3},
    "shot": {"prefix": "sh", "digits": 3},
    "version": {"prefix": "v", "digits": 3},
    "frame": {"prefix": ".", "digits": 5}
  },
  "structure": {
    "project_folders": ["config", "refs", "assets", "library", "shots", "renders", "exports"],
    "asset_prefixes": ["ch", "pr", "env"],
    "library_prefixes": ["mat", "gn", "tech"]
  },
  "tags": ["stable"],
  "assets_departments": ["modeling", "texturing", "rigging", "tech"],
  "shots_departments": ["layout", "animation", "lighting", "render"],
  "farm": {"max_concurrent_local": 1, "stale_monitor_seconds": 30}
}
```

Every prefix, tag, department, and digit count is free to change — this is the file that rebuilds the naming regex and folder routing on every change. `pipeline_addon_version` is written/refreshed on every project creation or edit — no automatic migration logic yet, just enough to know later which addon version last touched a given config.

---

**See also**: [Versions: wip and stable](versions.md) · [Interface](interface.md) for the panel these actions live in.
