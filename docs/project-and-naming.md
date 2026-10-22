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
├── snapshots/
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

New assets/shots can also be created in bulk from a CSV file (top bar menu > "Batch create from CSV"). Each row is built in its own disposable headless Blender process — never the current session — so nothing accumulates between rows (no leftover collections from a previous one) and the artist's own work is never reset or touched. Rows are processed strictly one at a time, never in parallel.

- **Assets**: `prefix`, `name` required; `departments`, `description` optional.
- **Shots**: `sequence`, `shot` required; `frame_start`/`frame_end`/`frame_duration`/`timeline`, `departments`, `description` optional. `shot` can also be a dash-joined block (e.g. `"030-035-040"`, in any order, any digit padding — `"3-10-020"` is just as valid) to create a multi-shot in one row — its shots are then spread evenly across the block instead of landing on one single frame.
  - **Priority when more than one frame column is filled in** (only the first that applies is used, the rest are ignored for that row): `timeline` (exact, e.g. `"1001-1021-1051-1076"` — one start per shot plus the block's end) > `frame_end` > `frame_duration` > `frame_start` alone (config's `default_frame_start` if even that's empty). `frame_end`/`frame_duration` set the block's own end for the auto-spread; without either, it defaults to 20 frames per shot past `frame_start` — never past an explicit `frame_end` though.
- `departments`: comma-separated department names. Falls back to the project's default set if the column is empty/missing; any name not found in the project's actually configured departments is skipped and logged as a warning — never blocks the row.
- A row matching an asset/shot that already exists (same prefix+name, or same sequence+shot) is silently skipped — batch creation never overwrites.

**Example — asset batch CSV:**

```csv
prefix,name,departments,description
ch,bob,"modeling,rigging",Hero character
pr,chair_oak,,Background prop (departments default to the project's asset set)
```

**Example — shot batch CSV:**

```csv
sequence,shot,frame_start,frame_end,frame_duration,timeline,departments,description
sq010,010,1001,1100,,,,Single shot, explicit range
sq010,020,,,,,,Single shot, falls back to project defaults
sq020,"030-035-040",,,,"1001-1021-1051-1076","layout,animation",Multi-shot block, exact per-shot starts
```

A cell left empty just means "use the fallback for that column" (project default departments, default frame start, auto-spread end...) — only `prefix`+`name` (assets) or `sequence`+`shot` (shots) actually have to be filled in on every row.

---

## Data structure: `project_config.json`

Written under a lock and atomically (temp file then rename), like every other pipeline JSON file (see [Design choices](design.md)). One per project, fully editable via "Edit project":

```json
{
  "project_name": "my_project",
  "pipeline_addon_version": "1.1.0",
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
  "thumbnails": {"size": 240},
  "snapshot": {
    "progress": {"wip": 33, "rework": 67, "rtk": 67},
    "schedule": {"start": "2026-09-01", "end": "2027-03-31", "days_off": ["2026-12-25"], "worked_days": [1, 2, 3, 4, 5]}
  },
  "farm": {
    "chunk_size": 5, "stuck_frame_factor": 5, "default_prerender_script": "",
    "max_concurrent_local": 1, "stale_monitor_seconds": 90, "dead_monitor_seconds": 360,
    "auto_archive_hours": 24, "archive_log_days": 14
  }
}
```

**Edit project** (Project panel), two columns of settings -- what each one does:

| Setting | What it does |
|---|---|
| Blender | The project's Blender version: another one shows a warning (below). |
| Resolution, Frame rate, Shot start | New shots' resolution, fps and first frame. |
| Naming | Prefix and digits of sequences, shots, versions and frames: the file names, and how they're read back. |
| Folders, Asset / Library prefixes, Version tags | The project's folder tree, the asset and library kinds, the version tags. |
| Assets / Shots departments | The departments each new asset or shot requires -- and the order every department list follows. |
| Thumbnails | Size of the render thumbnails (snapshot, file details). |
| Snapshot done | How much of a department counts as done in the snapshot: in progress, rework, open RTK. |
| Schedule, Days off, Worked days | The production's dates, for the snapshot's expected progress. |
| Chunk size | Frames per chunk a farm machine takes at a time (see [Rendering](farm.md)). |
| Pre-render | The pre-render script the Render dialog opens on. |
| Stuck frame | How many times its usual time a frame may take before its render is stopped (0 = never). |

The other `farm` keys aren't in the dialog: how many local farm processes at once, when a farm host counts as stale / gone, when finished jobs and their logs are archived / deleted (see [Rendering](farm.md)).

**Blender version**: `blender_version` (set at creation, editable in Edit project) is the Blender the project is made with. Opening the project with another major.minor (5.2 for a 4.5 project -- 4.5.2 vs 4.5.7 doesn't count) shows a red warning popup at startup and on activation, plus a red line in the Project panel: a file saved in a newer Blender may not open, or not look the same, in the project's one. Leave it empty to never warn.

Every prefix, tag, department, and digit count is free to change — this is the file that rebuilds the naming regex and folder routing on every change. `pipeline_addon_version` is written/refreshed on every project creation or edit — no automatic migration logic yet, just enough to know later which addon version last touched a given config.

---

**See also**: [Versions: wip and stable](versions.md) · [Interface](interface.md) for the panel these actions live in.
