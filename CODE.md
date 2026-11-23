# Minimalist Pipeline — Code

Blender addon. Lightweight pipeline for solo artists and small teams (2–5).
Python 3.11+, Blender 4.2+ (see README's Installation note -- `UILayout.separator()`'s `type` parameter, used throughout the panels/popups, is the actual floor). No external dependencies beyond stdlib + bpy; FFmpeg optional, called as a program.

The developer's guide: conventions, where things live, the flows that aren't obvious from one file. The user-facing explanation is `README.md` and `docs/`; the reasoning behind each decision, with its history, is `NOTES.md`; working documents (plans, mock-ups) are in `dev/`. Functions are documented where they are -- their docstrings, not here.

---

## Core philosophy

- Structure the file storage, not the artistic workflow
- Interaction pattern: **Detect → Inform → Propose → Execute if validated**
- Never act silently. Never block work.
- Warnings, not blockers. Even on stable files, the artist decides.

---

## Naming convention

```
{prefix}_{name}_v{number}[-{tag}].blend                        # asset / library
{seq_prefix}{n}_{shot_prefix}{n}[-{n}...]_v{number}[-{tag}].blend   # shot (mono, or a multishot block)
```

- Underscore: structural separator only (always 3 segments)
- Hyphen: words within a segment, version tags, **and** joining a block's shot numbers
- All lowercase. No other separators.
- No tag = wip (implicit). `-stable` is the only tag with pipeline behavior.

Examples:
```
ch_bob_v001.blend
ch_bob_v003-stable.blend
ch_small-guy_v001.blend
mat_wood-dark_v004-stable.blend
sq010_sh010_v001.blend
sq040_sh030-040-045-050_v001.blend      # a 4-shot block -- see "Multishot blocks" below
```

Regex is built dynamically from config via `ConfigCache.get_asset_regex()` / `get_shot_regex()` (not a fixed constant — every prefix/digit/tag comes from `project_config.json`). The shot segment matches `\d+(-\d+)*` — a mono-shot is a block of length 1, no separate code path anywhere in the naming layer. `parse_filename()` in `lib/config.py` tries asset regex first, then shot regex.

---

## Folder structure

```
my_project/
├── config/
│   ├── project_config.json
│   ├── logs/pipeline_log.jsonl, sessions_log.jsonl, progress.json  ← progress.json: a point a day (Breakdown › Over time, Activity)
│   ├── presets/                         ← lib/presets.py; before 2.0 all loose here (still read, Migrate old data moves them)
│   │   ├── render_shots/<department>_….py   ← render presets of shot files (their name gives their department)
│   │   ├── render_assets/<department>_….py  ← render presets of asset files
│   │   ├── creation/asset_file_preset.py, shot_file_preset.py  ← user-editable, copied from templates/
│   │   └── ffmpeg_presets/default.json
│   ├── .sessions/.session_{pid}.json    ← active session files
│   └── .farm/
│       ├── monitor.lock
│       ├── workers/worker_{uuid}.json
│       └── queue/{incomings,actives,archives,requests}/, queue/claims/<job_id>/claim_<k>.json
├── refs/
├── assets/
│   └── ch/
│       └── ch_bob/
│           └── .pipeline/               ← tracking.json, {version}.wipmeta, {version}.stablemeta
├── library/
│   └── mat/
│       └── mat_wood-dark/
├── shots/
│   └── sq010/sh010/                     ← a block's own folder is named after its full shot segment (sh030-040-045-050)
├── renders/
│   ├── sq010/
│   │   ├── sh010/{version}_{i}/         ← always per-shot, even for a block: a block's own folder is never used for output
│   │   ├── sh010/sq010_sh010_thumbnail.jpg  ← see NOTES.md "Thumbnails"
│   │   └── _preview/{scope}_{date}.mp4  ← disposable, never authoritative (see "Multishot blocks")
│   └── assets/ch/ch_bob/{version}_{i}/  ← an asset/library render mirrors its source path (render_root())
├── snapshots/<YYYY-MM>/                 ← exported snapshots; snapshots/reviews/<role>/<YYYY-MM>/ the reviews imported (+ .revert.json)
├── editing/rushes/                      ← the videos pushed to the edit (rushes.json: what the edit has)
├── backup/migration-<date>/             ← what Migrate old data changed, as it was
└── exports/
```

Prefix routing: `ch`, `pr`, `env` → `assets/`. `mat`, `gn`, `tech` → `library/`.
Routing logic: `prefix_to_parent_folder()` in `lib/config.py`. All paths resolved via `ConfigCache.get_path(name)` (see the dict in `lib/config.py`) or `to_relative()`/`to_absolute()` — never hand-built.

---

## Project config (`project_config.json`)

```json
{
  "project_name": "my_project",
  "format_version": "2.0.0",
  "blender_version": "(4, 0, 0)",
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
  "farm": {"max_concurrent_local": 1, "stale_monitor_seconds": 30,
           "stuck_frame_factor": 5, "chunk_size": 5,
           "auto_archive_hours": 24, "archive_log_days": 14}
}
```

Access via `ConfigCache.get()` — cached, invalidated on the config file's `st_mtime`, which is re-checked at most every `_VALIDATE_TTL` (2 s): `get()` is hit dozens of times per sidebar redraw (see NOTES.md, "Sidebar redraw: 341 ms…"). Dot-notation helper: `json_get(config, "naming.version.digits", 3)`.

---

## Architecture

```
minimalist_pipeline/
├── __init__.py               # Registration: classes = (*lib.classes, *data_classes,
│                              #   *panel_classes, *operator_classes) -- no shared
│                              #   M_PIPELINE_PT_main wrapper panel anymore, see below
├── addon_data.py              # PipelineProjectItem, PipelineAddonPreferences (has draw())
├── lib/                       # Core logic, package (not a single file anymore)
│   ├── __init__.py            # Re-exports every public symbol; classes = (4 core operators)
│   ├── errors.py              # PipelineError
│   ├── actions.py             # PipelineAction, set/get_pending_action
│   ├── core.py                 # addon_pref, json_get, locked_json, lock primitives, get_machine_id,
│   │                            #   random_display_name, cached_scandir (mtime-cached os.scandir)
│   ├── config.py               # ConfigCache, parse_filename, path helpers, project detection,
│   │                            #   format_shot_segment/shots_in_segment/format_camera_name/parse_camera_name
│   ├── browser.py              # dynamic enum callbacks: file cascade + department pickers
│   ├── batch.py                 # CSV batch creation: parse rows, launch headless per-row subprocess
│   ├── creation.py              # create_asset_file, create_shot_file, resolve_timeline
│   ├── handlers.py             # load_post/exit_pre/save_post/blend_import_post, heartbeat_30s
│   ├── session.py              # sessions, project backup, set_active_project_root
│   ├── libraries.py            # append/link warning logic
│   ├── versioning.py           # get_version_number, save_as
│   ├── presets.py              # asset collection preset; shot scaffolding + camera/marker
│   │                            #   build (build_shot_scene) and read-back (derive_shot_subranges)
│   ├── preview.py               # multishot preview providers: resolve_block_sources,
│   │                            #   resolve_sequence_sources; render_root, render_department
│   ├── saving.py               # WM_OT_safe_save (Ctrl+S override)
│   ├── logs.py                 # log(), read_log_tail()
│   ├── background.py           # reader threads held still while the main thread runs a window
│   ├── blendfile.py            # a .blend's libraries read, a copy written with its paths changed
│   ├── formats.py              # "format_version" in every project file
│   ├── icons.py                # the addon's coloured marks (icons/*.png)
│   ├── migration.py            # Migrate old data: plan_migration() (read only), apply_migration()
│   ├── relink.py               # Update links: a file's outdated links moved to their latest stables
│   ├── render_clean.py         # Clean old renders: which render folders to lighten
│   ├── rushes.py               # editing rushes: videos copied into editing/rushes/
│   ├── sound.py                # a render's sound, mixed down from the shot file
│   ├── thumbnails.py           # one small JPEG per render folder
│   ├── ui.py                   # small drawing blocks shared by panels and windows
│   ├── monitoring/             # what the project says about itself, and where it's shown
│   │   ├── tracking.py         # tracking.json / .wipmeta / .stablemeta, entries (incl. shot tag),
│   │   │                        #   ProjectScan, TrackingStatusCache, copy_entries (§5)
│   │   ├── status.py           # State engine: department_state(), department_score(),
│   │   │                        #   file_progress(), progress_weights(); parse_departments(),
│   │   │                        #   departments_text(), stage_flags()
│   │   ├── schedule.py         # working days, schedule_progress()
│   │   ├── history.py          # a file's Versions and Render history (the page's detail tabs)
│   │   ├── legacy.py           # the 1.x forms still written beside the 2.0 ones
│   │   ├── progress_log.py     # config/logs/progress.json: a point a day, the activity
│   │   ├── snapshot.py         # build_snapshot(): the project's state as one dict
│   │   ├── snapshot_page.py    # page_data(), render_page(): the page from templates/snapshot/
│   │   ├── review_import.py    # import_review(): a review's actions applied
│   │   ├── review_revert.py    # Revert a review: <review>.revert.json written, read back
│   │   ├── live.py             # the live page: its server (127.0.0.1; the network too while a
│   │   │                        #   guest is valid), the reader, the page's actions, the farm tab
│   │   ├── qr.py               # a QR code, pure Python (a guest's link): qr_matrix(), qr_svg()
│   │   └── windows.py          # the windows (Pipeline log, welcome, Project settings):
│   │                            #   open_monitoring_window(), _monitoring_tick, paging, keys
│   └── operators.py            # M_PIPELINE_OT_action_popup / text_popup / auto_version
├── farm/                      # Render farm: monitor/worker roles, queue, dispatch
│   ├── __init__.py
│   ├── loop.py                 # farm_tick, register_farm_loop, stop_farm_role_for_project
│   ├── monitor.py               # monitor role: launch/stop, job_request, request_preview_compile,
│   │                            #   queue ownership
│   ├── workers.py               # worker role: launch/kill, execute_render_request
│   ├── queue.py                 # scan_requests/scan_queue/scan_processes: stage machine
│   │                            #   (render jobs, a block's split, and preview compiles alike)
│   ├── dispatch.py               # render_dispatch: assign a job to worker(s)
│   ├── chunks.py                 # a render's chunks and their claims (pure helpers + claim files)
│   ├── setup.py                  # per-job output path + frame range resolution; a block's own
│   │                            #   split-at-setup lives here (run_render_setup_entry)
│   ├── stages.py                 # a job's stage_history: the one way a stage is added
│   ├── details.py                # a job's and a machine's details as plain data (the Farm tab)
│   ├── pace.py                   # seconds per frame per pre-render script (estimates)
│   ├── local.py                  # Render here: a file rendered on this machine, outside the queue
│   ├── awake.py                  # a worker kept out of idle sleep
│   └── post_render.py            # ffmpeg checks_images + compilation + preview concat
├── operators/
│   ├── __init__.py            # Exposes `classes` tuple
│   ├── project_ops.py          # create, find, set_active, unset, remove, edit project
│   ├── asset_ops.py            # create_asset
│   ├── shot_ops.py             # create_shot (mono or multishot block), edit_block_structure (§5)
│   ├── preview_ops.py           # compile_preview (block/sequence scope, §1.6)
│   ├── batch_ops.py             # batch_create (CSV, modal, polls the headless subprocess)
│   ├── file_ops.py             # increment_version
│   ├── log_ops.py              # pipeline_logs popup, its refresh, copy_log_line
│   ├── browser_ops.py          # open_file, open_file_version
│   ├── farm_ops.py             # submit render (incl. a block's per-shot checklist, Where:
│   │                            #   farm / local), monitor/worker role buttons
│   ├── live_ops.py             # open / stop the live page
│   ├── migration_ops.py        # Migrate old data
│   ├── monitoring_ops.py       # navigation inside the windows
│   ├── owner_ops.py            # delete a shot or an asset
│   ├── render_clean_ops.py     # Clean old renders
│   ├── rushes_ops.py           # push videos to editing/rushes/
│   ├── team_ops.py             # the team: picking one's user name
│   └── tracking_ops.py         # entry CRUD, prod snapshot export / review import / revert
├── panels/
│   ├── __init__.py            # Exposes `classes` tuple
│   ├── project_panel.py         # own draw_header(): active project name + edit/log/unset buttons
│   ├── file_panel.py            # per-file actions (asset or shot alike): version, render,
│   │                            #   preview, branch (shot only), open folder; own draw_header()
│   ├── farm_panel.py            # own draw_header(): monitor status, live even collapsed
│   ├── logs_panel.py            # Pipeline log window's list, threaded read (load_pipeline_log())
│   ├── monitoring_panel.py      # Those windows' content (Properties > Tool tab)
│   └── tracking_panel.py
│   # Project/File/Farm are standalone panels (no bl_parent_id, no shared
│   # M_PIPELINE_PT_main wrapper) -- each has its own header (no HIDE_HEADER),
│   # so each collapses independently; Farm defaults DEFAULT_CLOSED to keep
│   # the N-panel from stacking three full boxes while working inside a file.
├── menus/
│   ├── __init__.py            # Exposes `classes` + register_topbar_menu/unregister_topbar_menu
│   ├── button_context.py       # right-click menus on the addon's buttons (WM_MT_button_context, an operator's hidden rmb)
│   └── top_bar.py              # M_PIPELINE_MT_topbar_menu: same actions as the panels, condensed
│                                # into a "Pipeline" entry in the top bar (TOPBAR_MT_editor_menus);
│                                # read_only_indicator(): "READ-ONLY" label PREPENDED to
│                                # TOPBAR_MT_editor_menus (before the Blender icon itself),
│                                # plus a small arrow opening M_PIPELINE_MT_read_only_menu
│                                # (reason + Increment) -- see below
└── templates/                 # Bundled defaults copied into new projects, and farm subprocess entry scripts
```

`menus/`'s registration isn't only classes: the top bar's draw callbacks (the "Pipeline" menu, and the READ-ONLY indicator *prepended* so it sits before the Blender icon) are appended/removed explicitly from the root `register()`/`unregister()`, like the Ctrl+S keymap override. `Menu.draw()` defaults to `EXEC_DEFAULT`: set `layout.operator_context = "INVOKE_DEFAULT"` first, or every click skips `invoke()` and its dialog.

**Convention**: each sub-package's `__init__.py` re-exports a `classes` tuple; the root `__init__.py` assembles them with `*lib.classes`, `*panel_classes`, `*operator_classes` — never hand-duplicate a class list.

**The live page** is `templates/snapshot/` (page.html, `css/`, `js/` in parts listed by `lib/monitoring/snapshot_page.py` `CSS_PARTS` / `JS_PARTS`, assembled into one file) served by `lib/monitoring/live.py`, or written once as an offline snapshot. Its words are English keys, French in `js/i18n/fr.js` (`T('...')`; `TS()` for a word Blender sent). `tools/snapshot_kit.py` draws every component on one sheet; `tools/doc_screenshots/` makes the docs' screenshots.

---

## Key flows

What triggers what, where it isn't obvious from one file. The handlers are in `lib/handlers.py`, registered unconditionally by `register_handlers()` while the addon is enabled.

**File opened** (`load_post` → `post_load_handler`). No file, or a file outside the active project: nothing (a file of another *known* project offers to switch to it). Headless (a farm subprocess): nothing more. Then:
- `scan_sessions()` closes the sessions of other Blenders silent for 40 s;
- `session_update()` writes this one's (closing the previous file's session first);
- `sync_linked_libraries()` records links no import event reported;
- `check_library_update()` offers newer stables of linked libraries;
- read-only? (`-stable`, the `always_read_only` pref, reopened) → `set_opened_as_read_only()`, shown by the top bar's indicator, no popup;
- else `acquire_lock()`: refused → read-only with a popup naming who holds it;
- `m_pipeline.auto_version`: a day's first open of the latest version offers an increment (silent with `silent_auto_increment`), an older version offers a new one.

**Save** (Ctrl+S overridden → `wm.safe_save`, `lib/saving.py`). Outside the project, or not opened read-only: a plain save. Read-only: the lock is taken first (refused: "Save impossible"); a `-stable` asks Save / Increment / Cancel, another read-only file Save & Increment / Cancel. The File menu's Save and the top bar's icon bypass it (docs/limitations.md). After a save (`save_post_handler`): `session_update(saved=True)` -- the session's time counts as work --, `wipmeta_touch()`, then the links synced one tick later.

**Increment / Mark as stable** (`m_pipeline.increment_version`): the departments worked this session and, for a stable, the ones finished; `save_as()`, then a `.wipmeta` (`create_wipmeta()`) or a `.stablemeta` (`create_stablemeta()`) for the new file, which stays open, not read-only.

**Append / Link** (`blend_import_post`): an append from inside the project offers Clean & reLink; a link from outside the project offers Undo; a link inside is recorded in the `.wipmeta`, silently.

**Quit** (`exit_pre` → `on_quit_handler`): `close_session()` logs its duration (`sessions_log.jsonl`). Opening another file goes through `load_post` instead. Locks aren't released: they go stale (90 s).

**Clocks** (`bpy.app.timers`):
- `heartbeat_30s` (`lib/handlers.py`): `session_update()`, refreshes this machine's lock on the open file; once a day, `progress_log.check_yesterday()` -- the first Blender of the day writes yesterday's point and activity.
- `_status_tick` (`farm/loop.py`, ~10 s): `monitor.lock` only, for the Farm panel's header.
- `farm_tick` (`farm/loop.py`, `register_farm_loop()`, one per Blender): the monitor's `monitor_tick()` (`scan_requests()` → `scan_processes()` → `scan_queue()`: every job moved at most one stage, highest priority first) and/or the worker's `worker_tick()` (heartbeat, cancels, its render subprocesses, a request to take). Gone with the last role.
- `live._tick` (`lib/monitoring/live.py`, while the page is served): see below.
- `_monitoring_tick` (`lib/monitoring/windows.py`): keeps the Pipeline log, welcome and Project settings windows marked and redrawn.
- `ProjectScan._tick` (`lib/monitoring/tracking.py`): drains its reader thread into `TrackingStatusCache` while a project scan runs.

**Farm** -- roles: the monitor (`farm/monitor.py`, one per project, `monitor.lock`), workers (`farm/workers.py`, one per machine). A job: `incomings/job_<hash>.json` → `actives/`, `queued → setup_start → setup_finished → render_start → render_finished → checks_images_start → … → compilation_finished → finished → archived` (`stage_history`; `farm/stages.py` `mark_stage()` the one way to add a stage). Setup, frame check and compilation are subprocesses on the farm host, one at a time; the render is split in chunks claimed by workers (`farm/chunks.py`); a multishot block is split into one job per shot at setup (`farm/setup.py`). Render here (`farm/local.py`): the same job, on this machine, outside the queue. Every stage, failure and way back: NOTES.md, "Farm job: stages and cycles".

**Live page** (`lib/monitoring/live.py`):
- `start()` serves `127.0.0.1` (and the LAN while a guest's access is valid); request threads never touch bpy.
- `_tick()` → `_turn()` on the main thread: follows the active project, applies the page's queued actions (`_actions`: open, farm, play, relink at once; a review through `_apply()`, answered after the next pass), starts a reader pass (`read_live()`, a thread, pure os/json), and once it's back `_rebuild()`s the page's data (`build_snapshot()` → `page_data()`), bumping `version`.
- The page long-polls `/data?since=<version>`; a review is applied by `review_import.import_review()` as an imported review would be.
- `stop()` answers what was never turned to.

**Activate a project** (`lib.set_active_project_root()`): the farm role of the project left is stopped, the new root set, a worker launched if `auto_worker_on_open`. **Addon register**: preferences restored, handlers and timers registered, Ctrl+S overridden; an unreachable active project is unset (a dead NAS would freeze every redraw). **Unregister**: the live page stopped, timers, roles and the override removed.

---

## Multishot blocks

Full design rationale: `NOTES.md` (§ references below point to `multishot_spec_v2.md`). Summary of what's actually built, dev-facing:

- **What it is (§0)**: a *rare, deliberate* case — camera cuts on animation that can't be split into separate files without breaking the continuity, same decor/lighting, one department/person at a time. Never pushed forward in the UI; mono-shot stays the default. A mono-shot is a block of length 1 — no special case anywhere in the naming, creation, render-split, or camera-scaffolding code. The "homogeneous" precondition itself isn't checkable by the tool; the creation-time warning (§3, below) is the only barrier, and it teaches the rule instead of just flagging a count.
- **Naming (§1.1)**: the shot segment is `\d+(-\d+)*`, always sorted/deduped/zero-padded — `format_shot_segment()` builds it, `shots_in_segment()` is the inverse (parse a name back into shot numbers, filesystem-only, no `bpy`). A block covers exactly one sequence, enforced by the creation UI never offering a cross-sequence pick.
- **Creation** (`M_PIPELINE_OT_create_shot`, `shot_ops.py`): a shared `window_manager.shots_list_creation` (`PipelineShotItem`: shot number + start frame) drives both the naming preview and the actual file — `m_pipeline.add_multishot_item`/`remove_multishot_item` edit it (a remove button per row, by index; never the last row: its poll()), `_draw_shot_list`/`_draw_block_warning`/`_draw_timeline_warnings`/`_draw_naming_preview` (module-level, shared with the branch operator below) draw it. First shot's start frame, and the block's own `end_frame` default, both come from config's `default_frame_start` (1001 if unset), not a hardcoded 0.
- **Camera/marker scaffolding (§1.4)**: `build_shot_scene()` creates one camera + one timeline marker per shot (`cam_sq040_sh045_v001`), all sharing one CAM/SET/ASSETS collection set. `derive_shot_subranges()` is the read-back: live off `scene.timeline_markers`, only ever called once the file is genuinely open (see split, below) — never guessed from the filename.
- **Split at render (§1.2)**: happens at **setup time**, not submission — `run_render_setup_entry()` (the file is only ever genuinely open there). Submission (`M_PIPELINE_OT_farm_request_render`, any path: open file, cascade selector, or the batch render list) always writes exactly *one* `job_request()`, whether the target turns out to be a block or not; a submission-time checklist (filename-derived, `_populate_subshots()`) just rides along as that job's `only_shots`. `_split_into_shot_jobs()` (`farm/setup.py`) then fans a real block into one ordinary job per shot, each with its frame range already resolved to absolute *at split time* (so a child never has to reopen the file to re-derive what the split already knew) and `shot_override` set (routes its output to its own `shots/<sequence>/<shot_override>/` folder, never the block's own).
- **Divergence (§2)**: handled entirely *by the split*, not a separate submit-time or save-time check (deliberately rejected — the win is small, at most tens of seconds, and a second mechanism duplicating what the split already has to compute isn't worth it). Two kinds, both surfaced never silently:
  - `skipped_shots` — promised by the name, no marker found.
  - `absorbed_shots` — a marker found but not in the name; its frames merge into the preceding *promised* shot's range instead of getting their own (native Blender behavior: a camera switch with no boundary of its own just continues the previous shot).
  Both live on the parent job (its brief `split_finished → archived` window) and permanently in the block's own `.pipeline/render_history.json` (`construct_split_history()`).
- **Preview compile (§1.6)**: `M_PIPELINE_OT_compile_preview` (block or sequence scope) always goes through a farm request (`request_preview_compile()` → `run_preview_compile()`), never runs ffmpeg synchronously in the interactive session. Concat always uses ffmpeg's concat *filter* (decode + re-encode every source to the project's own resolution/fps), never the concat demuxer's `-c copy` — a block's shots can come from different render sessions and are never assumed to already share codec/fps/resolution. **Manual only, never auto-triggered** by a block's renders finishing (explicit decision): an auto-trigger would re-introduce the "continuous review" mechanism multishot_spec_v2.md's own §7 already walked back to a disposable, manual preview, and risks compiling a preview mid-flight on a partial/overridden sub-range.
- **Entries `shot` tag (§1.5)**: `create_entry()`/`edit_entry()`/the review import take an optional `shot` string, stored and displayed (`[sh045]` prefix) as-is — picked per line in New entry (`PipelineEntryItem.shot_tag`, `shot_tag_items()`: the block's own shots), one for the entry in Edit; no filter, no groupby.
- **Branch (§5)**: `M_PIPELINE_OT_edit_block_structure` (`shot_ops.py`, renamed from `branch_shot` for clarity) — its dialog pre-fills the shot list from the old block's own live `scene.timeline_markers` (`derive_shot_subranges()`) when the file being edited is the one currently open, `default_frame_start` otherwise. Blocks outright if the result would be a mono-shot exactly duplicating another active mono-shot's number; warns (behind a `confirm_overlap` checkbox) for any other shot-number overlap with an active file (`_classify_shot_conflicts()`, backed by `active_shot_owners()`). On execute: creates the new file first (so a failure there never leaves a block archived with no successor), flags the old block's `tracking.json` `archived: true` in place, `copy_entries()`, then moves the old composition into `old/` (`archive_folder()`) — deliberately not link-safe — and, per shot dropped from the new enumeration, its render folder too, unless another active file still covers that number. Version lineage continues (`start_version`) instead of restarting at v001. `list_active_blocks()` is the one filter point every block enumeration goes through instead of its own raw glob (wired into `shot_items()`), and skips the `old/` folder itself by name.

**Deferred, not implemented**: §6's MAX_PATH mitigation (shortening `.meta` filenames to drop the redundant base name) — a theoretical worst-case calculation was done (a UNC prefix over ~140 chars makes an 8-9 shot block's `.wipmeta.tmp` cross Windows' 260-char limit; the dominant 1-2 shot case has a large margin everywhere), but no real UNC test has been run, and the mitigation itself hasn't been coded pending that decision.

**Checked in real Blender**: creation and the render-time split, in real sessions (rough edges fixed along the way); Preview and Edit block structure still only through standalone logic -- see docs/limitations.md.

---

## What's NOT implemented yet

### v0.2 (next)
- [ ] **Casting JSON** — `shots/sq010/sh010/sq010_sh010_casting.json` per shot. Schema: `{shot, last_build, assets: [{name, version, built_version}]}`. `check_library_update()` already covers the per-file "your linked library has a newer stable" case; casting.json would be the shot-level, pinned/reviewable equivalent.
- [ ] **Build / rebuild** — link assets into shot file. Dry run first. Diff on rebuild.
- [ ] **§6 MAX_PATH mitigation** — see "Multishot blocks" above.

### Known tech debt
- `create_clean` in `create_asset`/`create_shot` uses `read_homefile()`, which resets Blender state. Should use a subprocess to generate the file without touching the current session.
- "Monitor" is the farm coordinator role (`launch_monitor`, `monitor_tick`, `monitor.lock`); the "monitoring windows" are the Pipeline log's, the welcome's and Project settings'.
- The live page's Farm tab lost, with the v7 page, the job's whole detail and a machine's (chunks in progress, failures, frames per machine, which machine rendered which frame, Stop now): `farm/details.py` `job_detail()` / `worker_detail()` and the server's `detail` / `worker_detail` actions still answer, the page no longer asks.
- `auto_worker_on_open` only fires at two specific moments (Blender startup, active-project switch) — no continuous re-check.
- **Pipeline log window** — `m_pipeline.pipeline_logs` (`operators/log_ops.py`, `search=` to open it filtered) opens the third monitoring window (`lib/monitoring/windows.py`, kind "log"; `M_PIPELINE_PT_log_monitoring`), filters in memory (`PIPELINE_PG_log_monitoring`, `WindowManager.pipeline_log_monitoring`); `draw_pipeline_logs()` (`panels/logs_panel.py`) pages it to the window (`rows_that_fit(..., _LINE_UNITS)`, `paginate("log")`, `draw_pager()`); `read_log_tail()` reads the last 1 MB of `pipeline_log.jsonl` on open/refresh/F5, on a thread (`load_pipeline_log()`, its timer redraws the window), never in draw(); a line click copies the whole entry (`m_pipeline.copy_log_line`). Keys: `_KEYMAP_ITEMS` (`lib/monitoring/windows.py`) -- each named for the preferences' Shortcuts section (`draw_addon_keys()`), the windows' on, the global ones off; `m_pipeline.monitoring_refresh` is F5.
- **Log rotation** (`lib/logs.py`) moves a log past `LOG_ROTATE_MAX_BYTES` into `config/logs/archives/` wholesale — never trims or compacts it. Fine at realistic scale (`sessions_log.jsonl` grows slowly enough that `RecentFilesCache` reading it whole on each rebuild stays cheap for a project's realistic lifetime), but if that ever stops holding, the fix isn't a smarter re-scan: it's baking old chunks down to one summed line per folder before they'd otherwise need re-reading, so old detail can be dropped without the total losing accuracy. Not built pre-emptively — no evidence yet that it's needed.

---

## Key patterns

```python
# Raising errors in core functions
raise PipelineError("Something went wrong", level="ERROR")

# Catching in operators (one try/except per operator)
except PipelineError as e:
    log(e.level, "operator_name", e.message)
    self.report({e.level}, e.message)
    return {"CANCELLED"}

# Showing a proposal to the user -- the callback can itself raise PipelineError,
# M_PIPELINE_OT_action_popup.execute() catches it (log + report) for every choice.
# 3rd tuple element (tooltip) is optional.
action = PipelineAction(
    title="Version outdated",
    message="Last save was yesterday.",
    severity="warning",
    choices=[
        ("Increment", lambda: save_as(), "Save as a new version."),
        ("Keep current", lambda: None),
    ]
)
set_pending_action(action)
bpy.ops.m_pipeline.action_popup("INVOKE_DEFAULT")
# ^ works from a handler/timer too (see check_library_update) --
# M_PIPELINE_OT_action_popup._force_close() handles the invoke_popup
# auto-close quirk regardless of caller.

# Reading config safely
config = ConfigCache.get()
digits = json_get(config, "naming.version.digits", 3)

# Writing a failure state -- NEVER box["action"] = "to_write" then raise in
# the same locked_json block: an exception skips straight past the write,
# same as any other code after yield in a @contextmanager. Use a separate,
# already-committed transaction instead (farm/stages.py's mark_stage() is the
# reusable version of this):
try:
    with locked_json(path) as box:
        ...  # do the work
        box["action"] = "to_write"
except Exception:
    mark_stage(path, "setup_failed")  # its own locked_json, always commits
    raise
```

**locked_json commits on normal exit only.** `raise` inside its `with` block skips the write the same way `raise` skips anything else after a generator's `yield` -- `box["action"] = "to_write"` set right before a `raise` never runs. This isn't a bug to route around case by case: it's why a stage-machine failure write always goes through its own already-closed `locked_json` call (`mark_stage()`), never inline in the block that failed. Rewriting the file unconditionally on every read was considered and rejected -- it would turn read-only calls into writes (mtime churn, defeats `ConfigCache`'s invalidation) and risks committing a half-mutated `box["data"]` if the exception fires mid-edit.

**The "who can report an error" rule**: a function raising `PipelineError` needs *someone* downstream able to catch it. An operator's `execute()`/`invoke()` can (`self.report` exists there). A handler, a `bpy.app.timers` callback, a `draw()` method, or an enum-items callback **cannot** — Blender gives no feedback channel there, and an uncaught exception in a timer silently deregisters it forever. Functions called from those contexts must not raise; they catch internally, `log()`, and return a safe default (see `session_update`, `close_session`, `check_library_update`, `TrackingStatusCache.get`).

---

## Preferences

`PipelineAddonPreferences` fields (drawn in `Preferences > Add-ons > Minimalist Pipeline`):
- `active_project_root: str` — never assign directly from an operator, go through `lib.set_active_project_root(prefs, new_root)`
- `machine_id: str` — generated once (`uuid4().hex[:12]`), persisted
- `opened_projects: CollectionProperty(PipelineProjectItem)` — each has `.name`, `.path`
- `opened_projects_index: int`
- `silent_auto_increment: bool` — `M_PIPELINE_OT_auto_version`'s day's-first-open case: silent increment vs. ask for confirmation first. No pref gates the 4 interactive handlers as a block anymore (used to be `auto_version`) — they're always registered while the addon is enabled (`register()`/`unregister()`, root `__init__.py`)
- `user_name: str`
- `auto_worker_on_open: bool`
- `always_read_only: bool`

---

## How to work with me

- No validation by default. If a proposed feature is useless, over-engineered, or solves the wrong problem — say it directly.
- If I suggest something that already exists in the codebase, point it out instead of implementing a duplicate.
- If my approach is wrong but the goal is valid, propose the right approach instead.
- I learn by implementing things myself. Prefer stubs with clear TODO comments over complete solutions, unless I explicitly ask for a full implementation.
- Over-engineering is the main risk on this project. When in doubt, the simpler solution is correct.

---

## Style rules

- Docstrings: one concise line. English. Note when a function must never raise (called from a handler/timer/draw context — see "Key patterns").
- `pathlib.Path` everywhere, not `os.path`.
- No silent modifications. No blocking operations.
- Operators: one `try/except PipelineError` block in `execute()`. Core functions raise, operators catch, and log the error alongside the `self.report`.
- Report user-facing success too, not just errors — an operator with no visible side effect (submitting a render, adding an entry) should still `self.report({"INFO"}, ...)`.
- UI: status bar for automatic actions, modal popup for user decisions.
- Sub-package `__init__.py` exposes a `classes` tuple; consumed via `*pkg.classes`, never hand-copied into another list.
- Type hints: annotate context params as `bpy.types.Context`, never `bpy.context` — the latter is a live (sometimes restricted) context instance at import time, not a type, and `bpy.context | None` raises `TypeError` on addon *load*, not on call.
