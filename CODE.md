# Minimalist Pipeline — Code

Blender addon. Lightweight pipeline for solo artists and small teams (2–5).
Python 3.11+, Blender 4.2+ (see README's Installation note -- `UILayout.separator()`'s `type` parameter, used throughout the panels/popups, is the actual floor; `invoke_props_dialog`'s `confirm_text`, 4.1, is a lesser constraint already covered by it). No external dependencies beyond stdlib + bpy.

For a user-facing explanation of concepts and design rationale, see `README.md`. For the exact execution order of every handler/timer/operator, see `graph.md`. This file is the dev-facing function inventory + patterns reference.

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
│   ├── logs/pipeline_log.jsonl, sessions_log.jsonl
│   ├── presets/
│   │   ├── asset_file_preset.py         ← user-editable, copied from templates/ at project creation
│   │   └── ffmpeg_presets/default.json
│   ├── .sessions/.session_{pid}.json    ← active session files
│   └── .farm/
│       ├── monitor.lock
│       ├── workers/worker_{uuid}.json
│       └── queue/{incomings,actives,archives,requests}/
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
│   └── sq010/
│       ├── sh010/{version}_{i}/         ← always per-shot, even for a block: a block's own folder is never used for output
│       └── _preview/{scope}_{date}.mp4  ← disposable, never authoritative (see "Multishot blocks")
└── exports/
```

Prefix routing: `ch`, `pr`, `env` → `assets/`. `mat`, `gn`, `tech` → `library/`.
Routing logic: `prefix_to_parent_folder()` in `lib/config.py`. All paths resolved via `ConfigCache.get_path(name)` (see the dict in `lib/config.py`) or `to_relative()`/`to_absolute()` — never hand-built.

---

## Project config (`project_config.json`)

```json
{
  "project_name": "my_project",
  "pipeline_addon_version": "1.0.1",
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
  "farm": {"max_concurrent_local": 1, "stale_monitor_seconds": 30}
}
```

Access via `ConfigCache.get()` — cached, invalidated on the config file's `st_mtime`. Dot-notation helper: `json_get(config, "naming.version.digits", 3)`.

---

## Architecture

```
minimalist_pipeline/
├── __init__.py               # Registration: classes = (*lib.classes, *data_classes,
│                              #   PIPELINE_PT_main_panel, *panel_classes, *operator_classes)
├── addon_data.py              # PipelineProjectItem, PipelineAddonPreferences (has draw())
├── lib/                       # Core logic, package (not a single file anymore)
│   ├── __init__.py            # Re-exports every public symbol; classes = (4 core operators)
│   ├── errors.py              # PipelineError
│   ├── actions.py             # PipelineAction, set/get_pending_action
│   ├── core.py                 # addon_pref, json_get, locked_json, lock primitives, get_machine_id
│   ├── config.py               # ConfigCache, parse_filename, path helpers, project detection,
│   │                            #   format_shot_segment/shots_in_segment/format_camera_name/parse_camera_name
│   ├── browser.py              # dynamic enum callbacks: file cascade + department pickers
│   ├── batch.py                 # CSV batch creation: parse rows, launch headless per-row subprocess
│   ├── creation.py              # create_asset_file, create_shot_file, resolve_timeline
│   ├── handlers.py             # load_post/exit_pre/save_post/blend_import_post, heartbeat_30s
│   ├── session.py              # sessions, project backup, set_active_project_root
│   ├── tracking.py             # tracking.json / .wipmeta / .stablemeta, entries (incl. shot tag),
│   │                            #   copy_entries/is_block_archived/list_active_blocks (§5)
│   ├── libraries.py            # append/link warning logic
│   ├── versioning.py           # get_version_number, save_as
│   ├── presets.py              # asset collection preset; shot scaffolding + camera/marker
│   │                            #   build (build_shot_scene) and read-back (derive_shot_subranges)
│   ├── preview.py               # multishot preview providers: latest_shot_mp4,
│   │                            #   resolve_block_sources, resolve_sequence_sources
│   ├── saving.py               # WM_OT_safe_save (Ctrl+S override)
│   ├── logs.py                 # log()
│   └── operators.py            # PIPELINE_OT_action_popup / text_popup / auto_version
├── farm/                      # Render farm: monitor/worker roles, queue, dispatch
│   ├── __init__.py
│   ├── loop.py                 # farm_tick, register_farm_loop, stop_farm_role_for_project
│   ├── monitor.py               # monitor role: launch/stop, job_request, request_preview_compile,
│   │                            #   queue ownership
│   ├── workers.py               # worker role: launch/kill, execute_render_request
│   ├── queue.py                 # scan_requests/scan_queue/scan_processes: stage machine
│   │                            #   (render jobs, a block's split, and preview compiles alike)
│   ├── dispatch.py               # render_dispatch: assign a job to worker(s)
│   ├── setup.py                  # per-job output path + frame range resolution; a block's own
│   │                            #   split-at-setup lives here (run_render_setup_entry)
│   └── post_render.py            # ffmpeg checks_images + compilation + preview concat
├── operators/
│   ├── __init__.py            # Exposes `classes` tuple
│   ├── project_ops.py          # create, find, set_active, unset, remove, edit project
│   ├── asset_ops.py            # create_asset
│   ├── shot_ops.py             # create_shot (mono or multishot block), branch_shot (§5)
│   ├── preview_ops.py           # compile_preview (block/sequence scope, §1.6)
│   ├── batch_ops.py             # batch_create (CSV, modal, polls the headless subprocess)
│   ├── file_ops.py             # increment_version
│   ├── browser_ops.py          # open_file, open_file_version
│   ├── farm_ops.py             # submit render (incl. a block's per-shot checklist),
│   │                            #   monitor/worker role buttons, farm dashboard
│   └── tracking_ops.py         # entry CRUD, CSV import, tracking dashboard
├── panels/
│   ├── __init__.py            # Exposes `classes` tuple
│   ├── project_panel.py
│   ├── file_panel.py            # per-file actions (asset or shot alike): version, render,
│   │                            #   preview, branch (shot only), open folder
│   ├── farm_panel.py
│   └── tracking_panel.py
├── menus/
│   ├── __init__.py            # Exposes `classes` + register_topbar_menu/unregister_topbar_menu
│   └── top_bar.py              # PIPELINE_MT_topbar_menu: same actions as the panels, condensed
│                                # into a "Pipeline" entry in the top bar (TOPBAR_MT_editor_menus);
│                                # read_only_indicator(): plain "READ-ONLY" label PREPENDED to
│                                # TOPBAR_MT_editor_menus (before the Blender icon itself), not a menu -- see below
└── templates/                 # Bundled defaults copied into new projects, and farm subprocess entry scripts
```

`menus/`'s registration doesn't fit the plain `classes`-tuple pattern alone: appending/removing the draw callback to `bpy.types.TOPBAR_MT_editor_menus` is a side effect outside class registration, called explicitly from the root `register()`/`unregister()` (same shape as `override_shortcut()`/`unoverride_shortcut()` for the keymap). `Menu.draw()` defaults to `EXEC_DEFAULT` — every operator call inside `PIPELINE_MT_topbar_menu.draw()` needs `layout.operator_context = "INVOKE_DEFAULT"` set first, or every click skips `invoke()` (and therefore every dialog) silently.

`read_only_indicator(self, context)` is a plain function (not a menu class method) prepended to the same `bpy.types.TOPBAR_MT_editor_menus` as `top_bar_menu`, above. `.prepend()`, not `.append()`: prepended callbacks run before the class's own native `draw()` entirely — which means before the Blender icon too, not just before "File". There's no clean way to land it *between* the icon and "File": both are hardcoded, back to back, inside that one native `draw()`, with no hook point between them (confirmed against Blender's own source) — `.append()`/`.prepend()` can only add content before or after that whole block, never inside it. Getting exactly "icon, then warning, then File" would need monkey-patching `TOPBAR_MT_editor_menus.draw()` itself; turned down as too fragile (depends on Blender's own internal draw code, could silently drift on a future version) for a cosmetic one-slot difference — see NOTES.md. Checks `get_opened_as_read_only() == bpy.data.filepath` (the same in-memory flag `lib/saving.py`'s Ctrl+S guard already relies on, no new state) and draws nothing when the file isn't read-only. Placed in the top bar rather than a panel because it needs to be visible without the sidebar open, right where the two saves that bypass the guard entirely live (File menu's Save, the top bar's save icon).

**Convention**: each sub-package's `__init__.py` re-exports a `classes` tuple; the root `__init__.py` assembles them with `*lib.classes`, `*panel_classes`, `*operator_classes` — never hand-duplicate a class list, that's exactly how a stale/renamed reference goes unnoticed (happened once already).

---

## lib/ — what's implemented

### Infrastructure
- `PipelineError(message, level)` — raise from core functions, catch once in operators
- `ConfigCache` — `.get()`, `.invalidate()`, `.get_asset_regex()`, `.get_shot_regex()`, `.get_path(name)` (central path table for every project-relative file/folder)
- `PipelineAction` dataclass — `title`, `message`, `severity`, `choices: list[tuple[str, Callable] | tuple[str, Callable, str]]` (label, callback, optional tooltip), `on_dismiss` (optional callback for Escape/click-away, see below), `explanation` (optional beginner-mode concept text, rendered via `draw_box_tip()` below the message — gated on the `experience_level` addon preference, no-op for `ADVANCED`)
- `set_pending_action()` / `get_pending_action()` — global store for the popup
- `PIPELINE_OT_action_popup` — generic popup, reads pending action, executes chosen callback inside `try/except PipelineError` (logs + reports on failure — this is the single safety net for every `PipelineAction` callback in the codebase). `description()` classmethod returns each choice's optional 3rd tuple element as that button's tooltip. `cancel()` handles Escape/click-away: clears the pending action and runs `on_dismiss` if set, so dismissing without clicking a choice cleans up the same as clicking one (e.g. `wm.safe_save` releasing its lock — see below). `execute()` calls `_force_close()` (`context.window.screen = context.window.screen`) before returning: `invoke_popup` doesn't auto-close just because a button inside it ran an operator to completion — a known Blender quirk (blender.stackexchange.com/q/202550), not specific to this addon.
- `PIPELINE_OT_text_popup` — simple message popup
- `PIPELINE_OT_auto_version` — on file open, checks mtime vs today / whether it's the latest version, proposes increment or branch. Still `invoke_confirm`-based (not converted to `PipelineAction`/`action_popup`): its own `execute()` does the real work directly off `self.is_branch`, not a delegated `bpy.ops` call, so converting it isn't a drop-in change like the two below were.
- Read-only-on-open and library-update-available used to be dedicated `invoke_confirm`-based operators (`read_only_notice`, `library_update_notice`), kept off `PipelineAction`/`action_popup` because of the same auto-close quirk `_force_close()` now fixes. Converted to plain `PipelineAction`s: `_propose_read_only_increment()` in `handlers.py`, inlined in `tracking.check_library_update()` (closes over its `update` list directly — the old `_pending_library_update` global/`get_pending_library_update()` indirection is gone).

### Utilities (`core.py`, `config.py`)
- `addon_pref(context=None)` — returns addon preferences
- `json_get(data, path, default)` — dot-notation dict access
- `parse_filename(filename)` — returns `{prefix, name/sequence/shot, number, tag}` or None
- `sanitize_name(raw)` — spaces→hyphens, lowercase, a-z0-9- only
- `list_to_labels(layout, items, ...)`, `text_to_lines(layout, text, max_width, ...)` — Blender UI helpers
- `type_by_folder(filepath, project_root)` — "asset" | "library" | "shot" | "other"
- `prefix_to_parent_folder(prefix, config)` — "assets" or "library"
- `find_project_root(start_path)` — walks up from start_path looking for `config/project_config.json`
- `to_relative(path, project_root=None)` / `to_absolute(rel_path, project_root=None)` — every path stored in a shared JSON file goes through these, so it's portable across machines that mount the project differently

### Locking (`core.py`)
- `acquire_lock(path, machine_id, retries=10, delay=0.1)` — O_CREAT|O_EXCL, steals a stale lock (age > `LOCK_STALE_SECONDS` = 90s)
- `check_lock(path, ...)` — read-only wait, never creates/steals
- `release_lock(path, machine_id)` — only releases if still owned
- `refresh_lock(path, machine_id)` — re-timestamps a lock already owned (can't reuse `acquire_lock`, it fails on O_EXCL against its own lock); no-op if it belongs to someone else
- `locked_json(path, read_only=False)` — context manager wrapping all of the above around a JSON read/write, with atomic write (tmp + `os.replace`)

### Browser (`browser.py`)
- File cascade: `prefix_items`, `asset_folder_items`, `sequence_items`, `shot_items`, `version_items`, `dir_version_items`, `get_folder(self, context)`
- Department pickers (shared by asset/shot/file/tracking-entry dialogs): `asset_department_items`, `shot_department_items`, `file_department_items`, `tracked_department_items` — first three build cached `(id, label, "", 2**i)` enum items from a department name list pulled from a different source each (config's `assets_departments`/`shots_departments`, or the current file's `tracking.json`); the fourth reads pre-built items off `TrackingStatusCache`.

### Versioning (`versioning.py`)
- `get_version_number(filepath="")` → int | None
- `get_last_version_number(filepath="")` → int (scans siblings, returns max)
- `save_as(tag=None)` → new filepath str | None

### Sessions & project backup (`session.py`)
- `session_update()` — writes/updates `.session_{pid}.json`; never raises (called from timers/handlers with no operator to report through)
- `close_session(session_file=None)` — logs session_end (`filepath` + `duration_seconds` as their own fields, consumed by `WorkTimeCache`, not parsed back out of the message string), deletes session file; never raises. No `session_start` line is logged — everything it would say is recoverable from the end line alone.
- `scan_sessions()` — detects orphaned sessions (last_ping > 40s), calls `close_session` on them; wired into `post_load_handler`
- `get_user(context=None)` / `get_user_data(user)` — identity for logs/sessions: prefs.user_name > OS login > "unknown"
- `save_project_data(prefs)` / `load_project_data(prefs)` — backs up `opened_projects` + `active_project_root` to Blender's user config dir
- `set_active_project_root(prefs, new_root)` — the ONE place that changes `active_project_root`: stops this instance's farm role for the project being left (`stop_farm_role_for_project`), then auto-launches a worker for the new one if `auto_worker_on_open` is on. Every operator that can switch projects calls this instead of assigning the field directly.

### Creation (`creation.py`)
- `create_asset_file(project_root, *, prefix, name, departments=None, description="")` — folder/version resolution, preset, save, tracking init
- `create_shot_file(project_root, *, sequence_number, shot_number, departments=None, description="", timeline=None, start_version=None)` — `shot_number` is an `int` (mono-shot) or `list[int]` (multishot block, no separate code path — `format_shot_segment()` handles both); `timeline` is `[start_0, ..., end]`, `None` defaults to `[default_frame_start]`; `start_version` is a floor for the version number, used by the branch operation (§5) to continue a lineage instead of restarting at v001
- `resolve_timeline(*, frame_start=None, frame_end=None, frame_duration=None, config=None)` — turns the CSV batch's loose, independently-optional frame columns into a `create_shot_file()`-ready `timeline`; the only caller that still needs the loose form (the interactive multishot dialog builds its own `timeline` directly from per-shot start frames)

### Tracking (`tracking.py`)
- `TrackingStatusCache` — per-asset cache of computed status, invalidated on `.pipeline/`'s mtime; `.get()` never raises (read by `draw()`/enum callbacks with no way to report an error); `.get_all()` filters out archived blocks (§5)
- `create_tracking`, `get_departments_required`, `create_wipmeta` (original_filepath is `None` for a brand-new file; stamps `edited_by`/`edited_at`), `wipmeta_add_work`, `wipmeta_touch` (edited_at/edited_by only, no departments/linked changes -- called from `save_post_handler` on every save so `PIPELINE_OT_auto_version` can tell a same-day re-open by a different user from the file's own author), `get_session_worked_departments` (in-memory cache of the current session's own worked-departments toggle state, kept in sync by `wipmeta_add_work` -- backs the toggle row in `file_panel.py`), `wipmeta_add_link`, `create_stablemeta`, `get_last_stable`, `get_last_wipmeta`, `get_current_departments`
- Entries: `create_entry`, `edit_entry`, `delete_entry`, `get_entries`, `valid_task`, `unvalid_task`, `toggle_entry_task` — all take an optional `shot` string (§1.5): a plain-text tag (e.g. `"045"`), not validated against anything real, displayed as a `[sh045]` prefix by `tracking_panel.py`. No filter, no groupby, no selector — a written convention only.
- CSV: `upload_csv(filepath, user)` → `(imported_count, total_rows)`
- `check_library_update()` — compares every linked library against `get_last_file_stable()` of its folder, proposes a batch update via a `PipelineAction` (closes over the `update` list directly); wired into `post_load_handler` (runs unconditionally, before the read-only gate — a `-stable` file still gets checked), never raises
- `library_updates`, `wipmeta_update_libraries`, `clean_libraries`
- `set_department_validated(filepath, department, validated)` — toggles one department's validated status directly, mutating the latest `.stablemeta` in place, no new `-stable` version needed (for departments like "render" that aren't tied to editing the file); raises `PipelineError` if the asset has no stable version yet. Backs the toggle buttons in `tracking_panel.py` and `pipeline.tracking_file_details`.
- `WorkTimeCache` — total `session_end` `duration_seconds` per asset/shot folder, everyone/every version summed, no per-person breakdown (see `design.md`); `.get(folder)` never raises, rebuilds in one pass over `sessions_log.jsonl` on that file's own mtime change (not per-folder — the log is shared). `format_duration(seconds)` — display formatting only, `"XhYY"`/`"Xd YYhZZ"`. Backs the "Total work time" line in `pipeline.tracking_file_details`.
- `RecentFilesCache` — up to 3 most-recently-opened files, one per folder, for the *current* `get_user()` only (not the whole team) — same mtime-cached full scan of `sessions_log.jsonl` as `WorkTimeCache`, but keyed on `ts` (newest per folder wins) and filtered to `entry["user"] == get_user().lower()` instead of summed. `.get(limit=3)` never raises. Backs the "Recent" entries in the top bar menu (`menus/top_bar.py`) — each opens directly via `pipeline.open_file_version` given an exact file path (skips its own version-picker dialog, see `PIPELINE_OT_open_file_version.invoke()` in `browser_ops.py`).
- **Branch (§5)**: `copy_entries(from_filepath, to_filepath)` — appends the old block's entries onto the new one's, as-is (author/created_at untouched). `is_block_archived(shot_dir)` / `list_active_blocks(project_root, sequence_label=None)` — the one point of truth every block enumeration goes through instead of its own raw glob (already wired into `shot_items()` in `browser.py` and `TrackingStatusCache.get_all()`). The `archived: true` flag itself is set inline in `PIPELINE_OT_branch_shot.execute()` (`operators/shot_ops.py`) — a 5-line `locked_json` write with exactly one caller, not worth its own lib function.

### Handlers (`handlers.py`)
- `post_load_handler` — session, library-update check (always, even read-only), lock (+ its heartbeat refresh), read-only gating (now a `PipelineAction` popup, not silent), auto-version proposal
- `on_quit_handler` — closes the session
- `save_post_handler`, `import_post_handler`
- `heartbeat_30s()` — timer; refreshes session + (if held) the current file's lock
- `register_handlers()` / `unregister_handlers()` — called unconditionally from `register()`/`unregister()` (root `__init__.py`): all 4 handlers + the heartbeat timer run for as long as the addon is enabled, no preference gates them as a block anymore

### Presets (`presets.py`)
- `install_default_preset()` / `install_default_ffmpeg_preset()` — copy bundled defaults into a fresh project, never overwrite
- `apply_asset_preset(prefix, name)` — runs the project's (user-editable) collection-building script, falls back to a single collection on any failure
- `build_shot_scene(sequence_label, shot_numbers, timeline, config)` — one camera + one timeline marker per shot in the block (`cam_sq040_sh045_v001`, named per §1.4, bound to a marker at that shot's own start frame), sharing a single CAM/SET/ASSETS collection set — a block is one decor/lighting setup, never one per shot. `shot_numbers=[n]` for a mono-shot, same code path.
- `derive_shot_subranges(scene, sequence_label, promised, config=None)` — the read-back counterpart, live off `scene.timeline_markers`: derives each shot's frame sub-range (one ends where the next *promised* one's marker begins). `promised` (the file's own name enumeration) decides which markers count as real boundaries — a marker not in it doesn't start its own range, its frames are absorbed into the preceding promised shot instead (§2). Returns `(ranges, absorbed)` — `absorbed` is never silent, see "Multishot blocks" below.

### Preview (`preview.py`)
- `latest_shot_mp4(project_root, sequence_label, shot_label, config=None)` — a shot's most recently rendered mp4, "most recent" read from the render increment folder's own name (`vNNN_MMM`), never mtime
- `resolve_block_sources(filepath, project_root, config=None)` / `resolve_sequence_sources(filepath, project_root, config=None)` — the two providers behind §1.6's "one button, two scopes": `(shot_label, mp4)` pairs for a block's own enumeration, or for every shot ever rendered under the file's sequence. Filesystem-only, no `bpy` — works for any file, open or not.

### Saving (`saving.py`)
- `WM_OT_safe_save` (`wm.safe_save`) — Ctrl+S override; direct save outside the project or when not read-only, otherwise gates on lock/`-stable`/read-only-origin with a popup (stable: Save / Increment / Cancel; read-only-origin: Save & Increment / Cancel). The popup itself is opened via `_open_popup()`, deferred one timer tick rather than called synchronously from `invoke()` — calling `action_popup` synchronously there made `invoke()` forward its inner `RUNNING_MODAL`, entangling the two operators' modal state so no button in the popup would reliably close it.

---

## farm/ — what's implemented

Two roles, coordinated purely through JSON files under `config/.farm/` on the shared project drive — no SSH, no direct machine-to-machine connection (see `docs/design.md`, "No SSH, push-pull coordination over the shared drive", for the rationale).

- **Monitor** (`monitor.py`) — one per project (`monitor.lock`). `launch_monitor()`, `is_blender_monitor()`, `stop_monitor_loop()`, `job_request()` (writes an incoming render request — `shot_override`/`only_shots` are set only on a per-shot job created by a block's own split, never at submission, see below), `request_preview_compile()` (writes an incoming preview-compile request, §1.6 — same `job_*.json`/`scan_requests()` path, distinguished purely by its own first stage, `initial_stage="preview_queued"`, not a `kind` field), `request_monitor_kill()` (async: writes a kill request, the monitor stops itself on its next tick), `job_cancel_request(job_id, target_uuid, user)` (async: asks one worker to stop rendering a specific job -- UI: the "X" button per job/worker in the farm dashboard), `archive(job_path)` (moves a job file + its render logs to `queue/archives/` -- manual only, via the dashboard's "✓" button; reaching "archived" in a job's own `stage_history` does NOT move it by itself, see below)
- **Worker** (`workers.py`) — `launch_worker()`, `is_blender_worker()`, `kill_worker()` (returns bool: True if this machine ends up worker-free), `execute_render_request()`, `apply_custom_preset()` (per-job render settings override, `.py` or `.json`)
- **Queue** (`queue.py`) — `scan_requests()` (incoming → active; reads the request's own `initial_stage` if it names one, else `"queued"` — the one hook a request kind needs to join the stage machine with its own first step), `scan_queue()` (advances every active job one stage — render jobs, a block's split, and preview compiles all live in the same flat `elif` chain, keyed on stage name alone), `scan_processes()` (polls locally-tracked `Popen`; its generic `"*_start"` → `"*_finished"/"*_failed"` completion detection is reused as-is by both the split and the preview compile, no new code needed there), `check_render_completion()` (monitor-only, cross-checks workers' declared results), `construct_split_history()` (a block's split outcome — `split_into`/`skipped_shots`/`absorbed_shots`, see "Multishot blocks" — appended to the block's own `render_history.json`, mirroring `construct_history()` for an ordinary job)
- **Dispatch** (`dispatch.py`) — `render_dispatch()`: `single` (one machine) vs `placeholder`/`auto` (all available machines attempt the same range, self-arbitrated via Blender's own `use_placeholder` + `use_overwrite=False`; `render_mode_auto` falls back to `single` if the last placeholder attempt on that file left corrupted frames, tracked in `render_history.json`)
- **Setup** (`setup.py`) — `compute_output_path()`, `resolve_job_context()` (`shot_override` routes to `shots/<sequence>/<shot_override>/` instead of the target file's own folder — how a block's per-shot jobs, all pointing at the same block file, land in separate output folders), `run_render_setup()` (launches the headless setup subprocess — deliberately doesn't compute the output path itself anymore: a possible block might split instead of rendering, only knowable once the file is genuinely open), `run_render_setup_entry()` (runs inside that subprocess — the file is only ever genuinely open here, so this is where a block gets detected and split via `_split_into_shot_jobs()` if `shot_override` isn't already set; a child's frame range is already absolute from split time, no marker re-read needed), `resolve_override_range()` (public: also used by the split to resolve each shot's override against its own sub-range instead of the whole file's)
- **Post-render** (`post_render.py`) — `checks_images()` (ffmpeg frame-corruption pass), `compilation()` (ffmpeg → video, via the project's ffmpeg presets), `build_concat_command()` / `run_preview_compile()` (§1.6 — concatenates a preview's resolved sources via ffmpeg's concat *filter*, decoding and re-encoding every input to the project's own resolution/fps, never the concat demuxer's `-c copy`: a block's shots can come from different render sessions and are never assumed to already match)
- **Loop** (`loop.py`) — `farm_tick()` (the shared timer both roles run through), `register_farm_loop()`, `stop_farm_role_for_project()` (used when the active project changes without quitting Blender), `_refresh_tick()` (UI-only, redraws the farm panel; `_build_job_entry()` also projects `skipped_shots`/`absorbed_shots` into the dashboard snapshot)

Job stage machine: `queued → setup_start/finished/failed → render_start/finished/failed → checks_images_start/finished/failed → compilation_start/finished/failed → finished → archived` (plus `orphaned`, detected on monitor startup for jobs stuck mid-stage with no matching local process). `"archived"` is a stage_history marker, not a location: `scan_queue()` appends it right after `finished`/`*_failed` so it stops touching the job again, but the file stays in `queue/actives/` (and keeps showing in the dashboard) until someone clicks "Archive" (`PIPELINE_OT_farm_archive_job` → `archive()`).

A multishot block's own submission joins two side branches onto that same chain, both landing back on `archived`:
```
queued → setup_finished ─┬─(ordinary job)──→ render_start → ... → finished → archived
                          └─(a block, no shot_override)─→ split_finished → archived
                              (fans out into one ordinary "queued" job per shot,
                               shot_override set -- ordinary chain from there)

queued → preview_queued → preview_start → preview_finished/failed → archived
```

---

## Multishot blocks

Full design rationale: `NOTES.md` (§ references below point to `multishot_spec_v2.md`). Summary of what's actually built, dev-facing:

- **What it is (§0)**: a *rare, deliberate* case — camera cuts on animation that can't be split into separate files without breaking the continuity, same decor/lighting, one department/person at a time. Never pushed forward in the UI; mono-shot stays the default. A mono-shot is a block of length 1 — no special case anywhere in the naming, creation, render-split, or camera-scaffolding code. The "homogeneous" precondition itself isn't checkable by the tool; the creation-time warning (§3, below) is the only barrier, and it teaches the rule instead of just flagging a count.
- **Naming (§1.1)**: the shot segment is `\d+(-\d+)*`, always sorted/deduped/zero-padded — `format_shot_segment()` builds it, `shots_in_segment()` is the inverse (parse a name back into shot numbers, filesystem-only, no `bpy`). A block covers exactly one sequence, enforced by the creation UI never offering a cross-sequence pick.
- **Creation** (`PIPELINE_OT_create_shot`, `shot_ops.py`): a shared `window_manager.shots_list_creation` (`PipelineShotItem`: shot number + start frame) drives both the naming preview and the actual file — `pipeline.add_multishot_item`/`remove_multishot_item` edit it, `_draw_shot_list`/`_draw_block_warning`/`_draw_timeline_warnings`/`_draw_naming_preview` (module-level, shared with the branch operator below) draw it. First shot's start frame, and the block's own `end_frame` default, both come from config's `default_frame_start` (1001 if unset), not a hardcoded 0.
- **Camera/marker scaffolding (§1.4)**: `build_shot_scene()` creates one camera + one timeline marker per shot (`cam_sq040_sh045_v001`), all sharing one CAM/SET/ASSETS collection set. `derive_shot_subranges()` is the read-back: live off `scene.timeline_markers`, only ever called once the file is genuinely open (see split, below) — never guessed from the filename.
- **Split at render (§1.2)**: happens at **setup time**, not submission — `run_render_setup_entry()` (the file is only ever genuinely open there). Submission (`PIPELINE_OT_farm_request_render`, any path: open file, cascade selector, or the batch render list) always writes exactly *one* `job_request()`, whether the target turns out to be a block or not; a submission-time checklist (filename-derived, `_populate_subshots()`) just rides along as that job's `only_shots`. `_split_into_shot_jobs()` (`farm/setup.py`) then fans a real block into one ordinary job per shot, each with its frame range already resolved to absolute *at split time* (so a child never has to reopen the file to re-derive what the split already knew) and `shot_override` set (routes its output to its own `shots/<sequence>/<shot_override>/` folder, never the block's own).
- **Divergence (§2)**: handled entirely *by the split*, not a separate submit-time or save-time check (deliberately rejected — the win is small, at most tens of seconds, and a second mechanism duplicating what the split already has to compute isn't worth it). Two kinds, both surfaced never silently:
  - `skipped_shots` — promised by the name, no marker found.
  - `absorbed_shots` — a marker found but not in the name; its frames merge into the preceding *promised* shot's range instead of getting their own (native Blender behavior: a camera switch with no boundary of its own just continues the previous shot).
  Both live on the parent job (visible in the farm dashboard for its brief `split_finished → archived` window) and permanently in the block's own `render_history.json` (`construct_split_history()`).
- **Preview compile (§1.6)**: `PIPELINE_OT_compile_preview` (block or sequence scope) always goes through a farm request (`request_preview_compile()` → `run_preview_compile()`), never runs ffmpeg synchronously in the interactive session. Concat always uses ffmpeg's concat *filter* (decode + re-encode every source to the project's own resolution/fps), never the concat demuxer's `-c copy` — a block's shots can come from different render sessions and are never assumed to already share codec/fps/resolution. **Manual only, never auto-triggered** by a block's renders finishing (explicit decision): an auto-trigger would re-introduce the "continuous review" mechanism multishot_spec_v2.md's own §7 already walked back to a disposable, manual preview, and risks compiling a preview mid-flight on a partial/overridden sub-range.
- **Entries `shot` tag (§1.5)**: `create_entry()`/`edit_entry()`/CSV import take an optional `shot` string, stored and displayed (`[sh045]` prefix) as-is — no selector, no filter, no groupby, no validation against real shots.
- **Branch (§5)**: `PIPELINE_OT_branch_shot` (`shot_ops.py`) — creates the new file first (so a failure there never leaves a block archived with no successor), *then* flags the old block's `tracking.json` `archived: true` in place (no move — an in-flight farm job on the old file never breaks), then `copy_entries()`. Version lineage continues (`start_version`) instead of restarting at v001. `list_active_blocks()` is the one filter point every block enumeration goes through instead of its own raw glob (wired into `shot_items()` and `TrackingStatusCache.get_all()`).

**Deferred, not implemented**: §6's MAX_PATH mitigation (shortening `.meta` filenames to drop the redundant base name) — a theoretical worst-case calculation was done (a UNC prefix over ~140 chars makes an 8-9 shot block's `.wipmeta.tmp` cross Windows' 260-char limit; the dominant 1-2 shot case has a large margin everywhere), but no real UNC test has been run, and the mitigation itself hasn't been coded pending that decision.

**Also true of the whole feature**: nothing above has been exercised against a real `bpy` yet — every check made while building it was standalone Python (regex, path/frame arithmetic), since this environment has no Blender. Treat it as unverified until run for real.

---

## What's NOT implemented yet

### v0.2 (next)
- [ ] **Casting JSON** — `shots/sq010/sh010/sq010_sh010_casting.json` per shot. Schema: `{shot, last_build, assets: [{name, version, built_version}]}`. `check_library_update()` already covers the per-file "your linked library has a newer stable" case; casting.json would be the shot-level, pinned/reviewable equivalent.
- [ ] **Build / rebuild** — link assets into shot file. Dry run first. Diff on rebuild.
- [ ] **§6 MAX_PATH mitigation** — see "Multishot blocks" above.

### Known tech debt
- `create_clean` in `create_asset`/`create_shot` uses `read_homefile()`, which resets Blender state. Should use a subprocess to generate the file without touching the current session.
- "Monitor" names two different things in the codebase on purpose, left as-is: the farm coordinator role (`launch_monitor`, `monitor_tick`, `monitor.lock`) and the UI dashboard popups (`PIPELINE_OT_farm_monitor`, `PIPELINE_OT_tracking_monitor` — "show a popup view of X", unrelated to the role).
- `auto_worker_on_open` only fires at two specific moments (Blender startup, active-project switch) — no continuous re-check.
- **Log rotation** (`lib/logs.py`) moves a log past `LOG_ROTATE_MAX_BYTES` into `config/logs/archives/` wholesale — never trims or compacts it. Fine at realistic scale (`sessions_log.jsonl` grows slowly enough that `WorkTimeCache` reading every archived chunk on each cache rebuild stays cheap for a project's realistic lifetime — see `docs/design.md`, "Work duration is logged..."), but if that ever stops holding, the fix isn't a smarter re-scan: it's baking old chunks down to one summed line per folder before they'd otherwise need re-reading, so old detail can be dropped without the total losing accuracy. Not built pre-emptively — no evidence yet that it's needed.

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
# PIPELINE_OT_action_popup.execute() catches it (log + report) for every choice.
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
bpy.ops.pipeline.action_popup("INVOKE_DEFAULT")
# ^ works from a handler/timer too (see check_library_update,
# _propose_read_only_increment) -- PIPELINE_OT_action_popup._force_close()
# handles the invoke_popup auto-close quirk regardless of caller.

# Reading config safely
config = ConfigCache.get()
digits = json_get(config, "naming.version.digits", 3)

# Writing a failure state -- NEVER box["action"] = "to_write" then raise in
# the same locked_json block: an exception skips straight past the write,
# same as any other code after yield in a @contextmanager. Use a separate,
# already-committed transaction instead (farm/queue.py's mark_stage() is the
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

**The "who can report an error" rule** (see README/graph.md for the full writeup): a function raising `PipelineError` needs *someone* downstream able to catch it. An operator's `execute()`/`invoke()` can (`self.report` exists there). A handler, a `bpy.app.timers` callback, a `draw()` method, or an enum-items callback **cannot** — Blender gives no feedback channel there, and an uncaught exception in a timer silently deregisters it forever. Functions called from those contexts must not raise; they catch internally, `log()`, and return a safe default (see `session_update`, `close_session`, `check_library_update`, `TrackingStatusCache.get`).

---

## Preferences

`PipelineAddonPreferences` fields (drawn in `Preferences > Add-ons > Minimalist Pipeline`):
- `active_project_root: str` — never assign directly from an operator, go through `lib.set_active_project_root(prefs, new_root)`
- `machine_id: str` — generated once (`uuid4().hex[:12]`), persisted
- `opened_projects: CollectionProperty(PipelineProjectItem)` — each has `.name`, `.path`
- `opened_projects_index: int`
- `silent_auto_increment: bool` — `PIPELINE_OT_auto_version`'s day's-first-open case: silent increment vs. ask for confirmation first. No pref gates the 4 interactive handlers as a block anymore (used to be `auto_version`) — they're always registered while the addon is enabled (`register()`/`unregister()`, root `__init__.py`)
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
