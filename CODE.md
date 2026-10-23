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
├── snapshots/                           ← the Snapshot button's default folder (ConfigCache "snapshots")
└── exports/
```

Prefix routing: `ch`, `pr`, `env` → `assets/`. `mat`, `gn`, `tech` → `library/`.
Routing logic: `prefix_to_parent_folder()` in `lib/config.py`. All paths resolved via `ConfigCache.get_path(name)` (see the dict in `lib/config.py`) or `to_relative()`/`to_absolute()` — never hand-built.

---

## Project config (`project_config.json`)

```json
{
  "project_name": "my_project",
  "pipeline_addon_version": "1.0.6",
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
           "stuck_frame_factor": 5, "chunk_size": 5, "default_prerender_script": "",
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
│   ├── tracking.py             # tracking.json / .wipmeta / .stablemeta, entries (incl. shot tag),
│   │                            #   copy_entries/is_block_archived/list_active_blocks (§5)
│   ├── libraries.py            # append/link warning logic
│   ├── versioning.py           # get_version_number, save_as
│   ├── presets.py              # asset collection preset; shot scaffolding + camera/marker
│   │                            #   build (build_shot_scene) and read-back (derive_shot_subranges)
│   ├── preview.py               # multishot preview providers: latest_shot_mp4,
│   │                            #   resolve_block_sources, resolve_sequence_sources
│   ├── saving.py               # WM_OT_safe_save (Ctrl+S override)
│   ├── logs.py                 # log(), read_log_tail()
│   ├── monitoring.py           # Project/Farm monitoring windows: open_monitoring_window(),
│   │                            #   monitoring_windows(), _monitoring_tick, open_mainfile()
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
│   ├── farm_ops.py             # submit render (incl. a block's per-shot checklist),
│   │                            #   monitor/worker role buttons, farm dashboard
│   └── tracking_ops.py         # entry CRUD, prod snapshot export / review import, tracking dashboard
├── panels/
│   ├── __init__.py            # Exposes `classes` tuple
│   ├── project_panel.py         # own draw_header(): active project name + edit/log/unset buttons
│   ├── file_panel.py            # per-file actions (asset or shot alike): version, render,
│   │                            #   preview, branch (shot only), open folder; own draw_header()
│   ├── farm_panel.py            # own draw_header(): monitor status, live even collapsed
│   ├── logs_panel.py            # Pipeline log window's list, threaded read (load_pipeline_log())
│   ├── monitoring_panel.py      # Project/Farm monitoring windows' content (Properties > Tool tab)
│   └── tracking_panel.py
│   # Project/File/Farm are standalone panels (no bl_parent_id, no shared
│   # M_PIPELINE_PT_main wrapper) -- each has its own header (no HIDE_HEADER),
│   # so each collapses independently; Farm defaults DEFAULT_CLOSED to keep
│   # the N-panel from stacking three full boxes while working inside a file.
├── menus/
│   ├── __init__.py            # Exposes `classes` + register_topbar_menu/unregister_topbar_menu
│   └── top_bar.py              # M_PIPELINE_MT_topbar_menu: same actions as the panels, condensed
│                                # into a "Pipeline" entry in the top bar (TOPBAR_MT_editor_menus);
│                                # read_only_indicator(): "READ-ONLY" label PREPENDED to
│                                # TOPBAR_MT_editor_menus (before the Blender icon itself),
│                                # plus a small arrow opening M_PIPELINE_MT_read_only_menu
│                                # (reason + Increment) -- see below
└── templates/                 # Bundled defaults copied into new projects, and farm subprocess entry scripts
```

`menus/`'s registration doesn't fit the plain `classes`-tuple pattern alone: appending/removing the draw callback to `bpy.types.TOPBAR_MT_editor_menus` is a side effect outside class registration, called explicitly from the root `register()`/`unregister()` (same shape as `override_shortcut()`/`unoverride_shortcut()` for the keymap). `Menu.draw()` defaults to `EXEC_DEFAULT` — every operator call inside `M_PIPELINE_MT_topbar_menu.draw()` needs `layout.operator_context = "INVOKE_DEFAULT"` set first, or every click skips `invoke()` (and therefore every dialog) silently.

`read_only_indicator(self, context)` is a plain function (not a menu class method) prepended to the same `bpy.types.TOPBAR_MT_editor_menus` as `top_bar_menu`, above. `.prepend()`, not `.append()`: prepended callbacks run before the class's own native `draw()` entirely — which means before the Blender icon too, not just before "File". There's no clean way to land it *between* the icon and "File": both are hardcoded, back to back, inside that one native `draw()`, with no hook point between them (confirmed against Blender's own source) — `.append()`/`.prepend()` can only add content before or after that whole block, never inside it. Getting exactly "icon, then warning, then File" would need monkey-patching `TOPBAR_MT_editor_menus.draw()` itself; turned down as too fragile (depends on Blender's own internal draw code, could silently drift on a future version) for a cosmetic one-slot difference — see NOTES.md. Checks `get_opened_as_read_only() == bpy.data.filepath` (the same in-memory flag `lib/saving.py`'s Ctrl+S guard already relies on, no new state) and draws nothing when the file isn't read-only. Placed in the top bar rather than a panel because it needs to be visible without the sidebar open, right where the two saves that bypass the guard entirely live (File menu's Save, the top bar's save icon).

The red text itself is a plain `row.label()`, not the button opening the menu: a `layout.menu()` pulldown doesn't pick up `row.alert`'s red styling, and a `wm.call_menu` operator button (which does) pops the menu as a floating, draggable popup with its own `bl_label` redrawn inside it -- both wrong here. So the row is `label("READ-ONLY", alert red) + menu(icon-only arrow)`: `layout.menu()` used directly in a header row (same mechanism `top_bar_menu` already relies on) is what actually gives an anchored, non-draggable pulldown with no duplicate title, it's just not stylable red -- hence keeping it icon-only right after the label instead of carrying the text itself. `M_PIPELINE_MT_read_only_menu` reads `get_read_only_reason()` (`lib/session.py` -- `"stable"` | `"profile"` | `"reopened"` | `"locked"`, stored alongside the filepath by `set_opened_as_read_only()`) to show why, plus an Increment button (hidden for `"locked"`, since incrementing doesn't get you past someone else's lock). Its `draw()` reimplements `draw_box_tip()`'s BEGINNER-only gate manually instead of calling it: `draw_box_tip()`'s own `box().column()` wrapper breaks a `Menu`'s layout (menus are more restrictive than panels/popovers about nested box/column layouts) -- `text_to_lines()` drawn flat on `layout` sidesteps it.

**Convention**: each sub-package's `__init__.py` re-exports a `classes` tuple; the root `__init__.py` assembles them with `*lib.classes`, `*panel_classes`, `*operator_classes` — never hand-duplicate a class list, that's exactly how a stale/renamed reference goes unnoticed (happened once already).

---

## lib/ — what's implemented

### Infrastructure
- `PipelineError(message, level)` — raise from core functions, catch once in operators
- `ConfigCache` — `.get()`, `.invalidate()`, `.get_asset_regex()`, `.get_shot_regex()`, `.get_path(name)` (central path table for every project-relative file/folder — plain join on the project root, memoized, never `resolve()`d: a resolve is two network round-trips on Windows)
- `PipelineAction` dataclass — `title`, `message`, `severity`, `choices: list[tuple[str, Callable] | tuple[str, Callable, str]]` (label, callback, optional tooltip), `on_dismiss` (optional callback for Escape/click-away, see below), `explanation` (optional beginner-mode concept text, rendered via `draw_box_tip()` below the message — gated on the `experience_level` addon preference, no-op for `ADVANCED`)
- `set_pending_action()` / `get_pending_action()` — global store for the popup
- `M_PIPELINE_OT_action_popup` — generic popup, reads pending action, executes chosen callback inside `try/except PipelineError` (logs + reports on failure — this is the single safety net for every `PipelineAction` callback in the codebase). `description()` classmethod returns each choice's optional 3rd tuple element as that button's tooltip. `cancel()` handles Escape/click-away: clears the pending action and runs `on_dismiss` if set, so dismissing without clicking a choice cleans up the same as clicking one (e.g. `wm.safe_save` releasing its lock — see below). `execute()` calls `_force_close()` (`context.window.screen = context.window.screen`) before returning: `invoke_popup` doesn't auto-close just because a button inside it ran an operator to completion — a known Blender quirk (blender.stackexchange.com/q/202550), not specific to this addon.
- `M_PIPELINE_OT_text_popup` — simple message popup
- `M_PIPELINE_OT_auto_version` — on file open, checks mtime vs today / whether it's the latest version, proposes increment or branch. Still `invoke_confirm`-based (not converted to `PipelineAction`/`action_popup`): its own `execute()` does the real work directly off `self.is_branch`, not a delegated `bpy.ops` call, so converting it isn't a drop-in change like the two below were.
- Library-update-available used to be a dedicated `invoke_confirm`-based operator (`library_update_notice`), kept off `PipelineAction`/`action_popup` because of the same auto-close quirk `_force_close()` now fixes. Converted to a plain `PipelineAction`, inlined in `tracking.check_library_update()` (closes over its `update` list directly — the old `_pending_library_update` global/`get_pending_library_update()` indirection is gone). Read-only-on-open went through the same conversion (`_propose_read_only_increment()`) and was then dropped entirely — the top bar's `M_PIPELINE_MT_read_only_menu` (see `menus/top_bar.py`, above) now carries the reason + Increment on demand instead of an interrupting popup on every open, for the three static reasons; only the lock case (dynamic, not knowable ahead of time) still pops up, via `M_PIPELINE_OT_text_popup`.

### Utilities (`core.py`, `config.py`)
- `addon_pref(context=None)` — returns addon preferences
- `resolve_ffmpeg()` — `prefs.ffmpeg_path` if set (no fallback past it if it's set but invalid — see NOTES.md, "FFmpeg detection"), else `shutil.which("ffmpeg")`, then `_COMMON_FFMPEG_PATHS` (a few well-known per-platform install spots) as a last resort; every ffmpeg call site (`farm/post_render.py`) takes the result as a value, never shells out to the bare `"ffmpeg"` string
- `json_get(data, path, default)` — dot-notation dict access
- `parse_filename(filename)` — returns `{prefix, name/sequence/shot, number, tag}` or None
- `sanitize_name(raw)` — spaces→hyphens, lowercase, a-z0-9- only
- `list_to_labels(layout, items, ...)`, `text_to_lines(layout, text, max_width, ...)` — Blender UI helpers
- `type_by_folder(filepath, project_root)` — "asset" | "library" | "shot" | "other"
- `prefix_to_parent_folder(prefix, config)` — "assets" or "library"
- `find_project_root(start_path)` — walks up from start_path looking for `config/project_config.json`
- `to_relative(path, project_root=None)` / `to_absolute(rel_path, project_root=None)` — every path stored in a shared JSON file goes through these, so it's portable across machines that mount the project differently
- `cached_scandir(path)` — `os.scandir(path)` results cached on `path`'s own mtime (changes exactly when a direct child is added/removed/renamed); returns `os.DirEntry`, not `Path`, so `.is_dir()` reads scandir's own cached stat instead of a second one. Used anywhere a listing is re-derived on every redraw (`browser.py`'s enum callbacks, `list_active_blocks()`) — see NOTES.md, "Network-share redraw cost".
- `file_in_active_project(filepath, project_root=None)` (`config.py`) — memoized on the exact `(filepath, project_root)` pair (single slot, not a dict): `M_PIPELINE_PT_file_panel.poll()` calls it with the same two values on every sidebar redraw candidate between file opens, and each `Path.resolve()` is a syscall per path component on a mounted share.

### Locking (`core.py`)
- `acquire_lock(path, machine_id, retries=10, delay=0.1)` — O_CREAT|O_EXCL, steals a stale lock (age > `LOCK_STALE_SECONDS` = 90s)
- `check_lock(path, ...)` — read-only wait, never creates/steals; a lock `_is_unlock()` already judges stale is treated as cleared immediately rather than waited out across the full `retries*delay` budget (a dead writer, e.g. a crashed client machine, otherwise costs every reader on every machine that same wait, for as long as the orphaned lock file sits there — see NOTES.md, "Network-share redraw cost")
- `release_lock(path, machine_id)` — only releases if still owned
- `refresh_lock(path, machine_id)` — re-timestamps a lock already owned (can't reuse `acquire_lock`, it fails on O_EXCL against its own lock); no-op if it belongs to someone else
- `locked_json(path, read_only=False, retries=10)` — context manager wrapping all of the above around a JSON read/write, with atomic write (`write_json_atomic()`: tmp + `os.replace`, also used alone for a file with one writer, a chunk claim). `retries=0` is the convention for a UI-thread read (draw()/poll()/enum-items callback): never sleep, just read the previous version.

### Browser (`browser.py`)
- File cascade: `prefix_items`, `asset_folder_items`, `sequence_items`, `shot_items`, `version_items`, `dir_version_items`, `get_folder(self, context)` — the folder-listing ones go through `cached_scandir()` (above), not raw `Path.iterdir()`: Blender re-invokes an enum-items callback on every redraw, so without it every redraw re-lists from disk even when nothing changed.
- Department pickers (shared by asset/shot/file/tracking-entry dialogs): `asset_department_items`, `shot_department_items`, `file_department_items`, `tracked_department_items` — first three build cached `(id, label, "", 2**i)` enum items from a department name list pulled from a different source each (config's `assets_departments`/`shots_departments`, or the current file's `tracking.json`); the fourth reads pre-built items off `TrackingStatusCache`.

### Versioning (`versioning.py`)
- `get_version_number(filepath="")` → int | None
- `get_last_version_number(filepath="", cached=False)` → int (scans siblings, returns max). `cached=True` (lists through `cached_scandir()`) is for a draw() preview only — anything that picks a filename to write (`save_as()`) lists fresh (see NOTES.md, "Next version number: never from a cached listing")
- `save_as(tag=None)` → new filepath str | None

### Sessions & project backup (`session.py`)
- `session_update()` — writes/updates `.session_{pid}.json`; never raises (called from timers/handlers with no operator to report through)
- `close_session(session_file=None)` — logs session_end (`filepath` + `duration_seconds` as their own fields, consumed by `WorkTimeCache`, not parsed back out of the message string), deletes session file; never raises. No `session_start` line is logged — everything it would say is recoverable from the end line alone.
- `scan_sessions()` — detects orphaned sessions (last_ping > 40s), calls `close_session` on them; wired into `post_load_handler`
- `get_user(context=None)` / `get_user_data(user)` — identity for logs/sessions: prefs.user_name (seeded with `lib.random_display_name()` at first register) > "unknown"
- `save_project_data(prefs)` / `load_project_data(prefs)` — backs up `opened_projects` + `active_project_root` to Blender's user config dir
- `set_active_project_root(prefs, new_root)` — the ONE place that changes `active_project_root`: stops this instance's farm role for the project being left (`stop_farm_role_for_project`), then auto-launches a worker for the new one if `auto_worker_on_open` is on. Every operator that can switch projects calls this instead of assigning the field directly.
- `get_opened_as_read_only()` / `set_opened_as_read_only(value, reason)` / `get_read_only_reason()` — in-memory (not persisted) flag for the current session: which filepath is read-only, and why (`"stable"` | `"profile"` | `"reopened"` | `"locked"`). `get_read_only_reason()` alone isn't scoped to the current file — always pair it with `get_opened_as_read_only() == bpy.data.filepath` (the flag is never cleared on a normal file open, only ever overwritten by the next read-only one).

### Creation (`creation.py`)
- `create_asset_file(project_root, *, prefix, name, departments=None, description="")` — folder/version resolution, preset, save, tracking init
- `create_shot_file(project_root, *, sequence_number, shot_number, departments=None, description="", timeline=None, start_version=None)` — `shot_number` is an `int` (mono-shot) or `list[int]` (multishot block, no separate code path — `format_shot_segment()` handles both); `timeline` is `[start_0, ..., end]`, `None` defaults to `[default_frame_start]`; `start_version` is a floor for the version number, used by the branch operation (§5) to continue a lineage instead of restarting at v001
- `resolve_timeline(*, frame_start=None, frame_end=None, frame_duration=None, shot_count=1, config=None)` — turns the CSV batch's loose, independently-optional frame columns into a `create_shot_file()`-ready `timeline`; the only caller that still needs the loose form (the interactive multishot dialog builds its own `timeline` directly from per-shot start frames). `shot_count` > 1 (a CSV multi-shot row) spreads shots evenly across `[frame_start, end]` (`end` from `frame_end`/`frame_duration` if given, else defaulted from `DEFAULT_MULTISHOT_STEP`) — never past an explicit `frame_end`
- `DEFAULT_MULTISHOT_STEP` (`creation.py`) — shared default per-shot spacing (20 frames) used when a CSV multi-shot row gives no `frame_end`/`frame_duration` to derive the span from instead; same default the interactive multishot dialog's own "add row" uses (`operators/shot_ops.py`)
- `parse_timeline(raw)` (`config.py`) — parses a CSV row's `timeline` column (e.g. `"1001-1021-1051-1076"`) straight into a `create_shot_file()`-ready `timeline`, bypassing `resolve_timeline()`'s auto-spread for exact per-shot control. Not to be confused with the farm's own, unrelated `overrided_frame_range`/`resolved_frame_range` (`operators/farm_ops.py`, `farm/dispatch.py`)

### Tracking (`tracking.py`)
- Validation roles (`lib/config.py`: `validation_roles(config)`, `covering_role(approvals, role, roles)`; `lib/tracking.py`: `set_department_approval(filepath, department=, role=, approved=, user=, stable_file=)` -- the latest stable's `approvals`, a note under the role (`APPROVAL_SOURCE`) --, `_carried_approvals()` into the next stable's `approvals_previous`, `department_approvals()` / `highest_approval()` for the UI; `lib/session.py`: `get_user_role()` from the `user_role` pref; `create_entry(role=)`). UI: `m_pipeline.toggle_department_approval` (File details, `_draw_approval()`), the monitor's "Done · prod" and `only_to_validate` filter (`_to_validate()`), entry marks (`_ROLE_ICON`...). `m_pipeline.create_entry`'s `as_role` (off: a team note). Snapshot: `_approval_mark()`, the *Validated* figure (`top_validation_role()`, `item["validation"]`, `meta["validation"]`, a `valid` column, `average_progress(items, "validation")`), the review template's Role / `valid all` / `valid <dept>` (`_review_columns()`), a line's `[sh020] [f12-40]` (`_line_tags()`), `review_import_plan()` + `M_PIPELINE_OT_import_review_confirm`. See NOTES.md "Validation roles".
- `threads_paused()` / `background_work()` / `checkpoint()` (`lib/background.py`) -- reader threads held still while a window operator runs (`window_new`, `window_close`, `area_dupli`, `open_mainfile`): `bpy.ops` releases the GIL, and a thread alongside crashed Blender. Every reader thread runs in `background_work()`; `checkpoint()` in `_walk_owner_dirs()` and `read_json_quiet()`. See NOTES.md "Monitoring crash: a thread during window_new()".
- `bring_monitoring_to_front(context, kind)` (`lib/monitoring.py`) -- the open monitoring window raised: `SetForegroundWindow()` on Windows (`_raise_win32()`, matched by client size), else reopened in front. See NOTES.md "Monitoring windows: to the front".
- `ordered_departments(deps)` (`lib/config.py`) -- the project's order (Edit project), used wherever departments are written or read (tracking.json's `departments_required` was sorted by name).
- Entries' departments: `entry_departments(e)` (`"departments"` list, else the single `"department"`), written by `create_entry()` / `edit_entry()` (`departments=` list) through `_set_entry_departments()` -- the first always in `"department"` for older addons; dialogs pick them with an ENUM_FLAG menu (`tracked_department_flag_items()`, `PipelineEntryItem.departments`). See NOTES.md "Entries for several departments"
- `TrackingStatusCache` — per-asset cache of computed status, invalidated on `.pipeline/`'s mtime; `.get()` never raises (read by `draw()`/enum callbacks with no way to report an error). Re-checking that mtime is itself a handful of syscalls, so `.get()` also skips it within a short TTL (`_VALIDATE_TTL`, `time.monotonic()`) of the last check — one redraw calls `.get()` several times (draw, `get_description`, `get_current_departments`, the department enum...), this collapses that into roughly one disk check per TTL window instead of one per call. `.known(project_root)` is what Project monitoring's draw() reads: memory only, archived blocks (§5) filtered out, filled by `ProjectScan` below. File details: `_draw_renders_to_check()` (box under the thumbnail row) and `_draw_last_renders()` (column right of the departments: the last render per shot -- `read_render_state()` (`lib/snapshot.py`, the snapshot's "Last render" source, which also gives the folder's `path`), read on click by `load_file_renders()` next to `load_file_thumbnail()`). "Farm" cell (`_draw_farm_cell()`): icons only, shot by shot -- a green `m_pipeline.open_render_video` per render to check (the entry's `video`, the job's `compiled_output_path`; else the newest video in its `render` folder, looked up on click) interleaved with a grey/blue/red `m_pipeline.department_status_info` (tooltip carrier) per job of the folder from `farm_activity()`, then one `m_pipeline.render_checked` checkbox (`farm/loop.py`: the monitor cache's unfinished render jobs keyed by `owner_key()`, memory only; the window's opening, its refresh button and `_monitoring_tick` (every 10 s) kick `request_monitor_refresh()`, a one-shot threaded read -- the snapshot export does the same and passes `farm_activity()` to `build_snapshot()`). "Checked" (`m_pipeline.render_checked`): its `invoke()` fills `WindowManager.render_checked_departments` (`PIPELINE_PG_department_check_item`: every required department, `validate` as validated now -- "render" too -- and `was_validated`) and asks which are validated after watching it, writing only the changes (unticking unvalidates) -- skipped when there are none or no stable version; a checklist, not a dynamic ENUM_FLAG, which draws as an empty box in a dialog -- `set_department_validated()` after the check; `clear_render_to_check()` returns the dropped entries' `job_id`s, and each one still in `actives/` with a `finished` stage goes through `archive()`. The Pipeline log popup opens at `popup_width(context)` (`panels/tracking_panel.py`): `MONITOR_POPUP_SHARE` of the window, never under `MONITOR_POPUP_MIN_WIDTH`, divided by the UI scale since a dialog's width is unscaled. Project and Farm monitoring are windows instead (`lib/monitoring.py`, the screen's `MONITORING_SCREEN_KEY` = "project" / "farm"; `M_PIPELINE_PT_monitoring` / `M_PIPELINE_PT_farm_monitoring` in `panels/monitoring_panel.py` -- see NOTES.md, "Monitoring: windows, not popups"): `m_pipeline.tracking_monitor` / `m_pipeline.farm_monitor` open them (on the first, `open_file` -- the File panel's Details button, or Ctrl+click: `invoke()` reads `event.ctrl` -- `_show_open_file()` shows the open file's detail, or `monitoring_detail("missing_file")` -- its name -- for the not-found view with a Back button, a key of its own so nothing reading the "file" detail gets a non-folder; the Farm panel's header status is a `farm_monitor` button too), `draw_file_details()` wraps on the region's own width; their filters are `WindowManager.pipeline_monitoring` / `pipeline_farm_monitoring` (`PIPELINE_PG_monitoring` in `operators/tracking_ops.py`, `PIPELINE_PG_farm_monitoring` in `operators/farm_ops.py`: `memory_prop()` / `memory_enum()`, get/set on a module dict, never stored in the .blend). `draw_monitor_table()` filters it (type/prefix/sequence, `only_farm`, `only_rtk` -- `_has_rtk()`, also the red department icon --, `search` on file name + description), sorted by name, or by `sort` (`_oldest_open_rtk()`, or the status's `last_saved_at`: its latest wipmeta's `edited_at`), paged by `paginate()` (`lib/monitoring.py`: the page and page count in `_pages`, back to 1 when a filter or the sort changes) at `rows_that_fit()` rows -- the region's height less `_TABLE_RESERVED_UNITS`, over `ROW_UNITS`, never under `MIN_ROWS` (6) -- padded with blank rows, `draw_pager()` in the footer (arrows: `m_pipeline.monitoring_page` → `turn_page()`, Ctrl to the ends; `operators/monitoring_ops.py`, with `m_pipeline.monitoring_back` -- Esc; `m_pipeline.monitoring_switch` -- Tab, assets / shots or jobs / workers; `register_monitoring_keymap()` binds Left / Right in "Frames" (its own arrows win over the Properties editor's keymap), Esc / Tab in "Property Editor", their poll() keeping them to a monitoring window; `draw_addon_keys()` lists them, with Ctrl+S, editable in the addon preferences; `split_footer()` keeps the pager at the footer's right end); Blender's active tool panel, which heads the Tool tab, is hidden in the monitoring windows (`hide_active_tool_in_monitoring()` at register, `restore_active_tool()` at unregister); `draw_farm_jobs()` does the same for Farm monitoring's jobs (paged alike, `_pages["farm"]`, `_JOBS_RESERVED_UNITS`; `draw_farm_workers()` pads its machines to `rows_that_fit()` too, `_WORKERS_RESERVED_UNITS`, no pages; stage icons from `job_icon()` (`panels/farm_panel.py`), shared with the Farm column, `state` via `job_state()` in `farm/loop.py`, also what `m_pipeline.farm_archive_jobs` archives by, `only_mine` on the entry's `user`, `search` on file name + shot), sorted on the entry's `submitted_at`.
- `create_tracking`, `get_departments_required`, `create_wipmeta` (original_filepath is `None` for a brand-new file; stamps `edited_by`/`edited_at`), `wipmeta_add_work`, `wipmeta_touch` (edited_at/edited_by only, no departments/linked changes -- called from `save_post_handler` on every save so `M_PIPELINE_OT_auto_version` can tell a same-day re-open by a different user from the file's own author), `get_session_worked_departments` (in-memory cache of the current session's own worked-departments toggle state, kept in sync by `wipmeta_add_work` -- backs the toggle row in `file_panel.py`), `wipmeta_add_link`, `create_stablemeta`, `get_last_stable`, `get_last_wipmeta`, `get_current_departments`
- Entries: `create_entry`, `edit_entry`, `delete_entry`, `get_entries`, `valid_task`, `unvalid_task`, `toggle_entry_task` — all take an optional `shot` string (§1.5): a plain-text tag (e.g. `"045"`), not validated against anything real, displayed as a `[sh045]` prefix by `tracking_panel.py`. No filter, no groupby, no selector — a written convention only.
- `create_entry(..., created_at=None, source=None)` — `created_at` overrides now() (an imported review's own date), `source` marks where a non-hand-typed entry came from (`"prod_review"`).
- `check_library_update()` — compares every linked library against `get_last_file_stable()` of its folder, proposes a batch update via a `PipelineAction` (closes over the `update` list directly); wired into `post_load_handler` (runs unconditionally, before the read-only gate — a `-stable` file still gets checked), never raises
- `library_updates`, `wipmeta_update_libraries`, `clean_libraries`
- `compact_linked(entries)` — a meta's `linked` list as one `{"file"}` per linked file (`../` collapsed, compared normcased); applied by every writer of the list (`wipmeta_add_link`, `wipmeta_sync_links`, `wipmeta_add_work`, `wipmeta_update_libraries`, `create_wipmeta`/`create_stablemeta` inheritance) and by `get_linked_libraries()` on read (an old `.stablemeta` is never rewritten). `scan_linked_libraries()` (`lib/libraries.py`) lists the open file's direct project libraries -- see NOTES.md "Linked libraries: one line per file"
- `set_department_validated(filepath, department, validated)` — toggles one department's validated status directly, mutating the latest `.stablemeta` in place, no new `-stable` version needed (for departments like "render" that aren't tied to editing the file); raises `PipelineError` if the asset has no stable version yet. Backs the toggle buttons in `tracking_panel.py` and `m_pipeline.tracking_file_details`.
- `WorkTimeCache` — total `session_end` `duration_seconds` per asset/shot folder (keyed project-relative, `_session_folder_key()`: `session_end` stores a relative `filepath`, older lines an absolute one), everyone/every version summed, no per-person breakdown (see `design.md`); `.get(folder)` never raises, rebuilds on the *current* `sessions_log.jsonl`'s own mtime change (not per-folder — the log is shared). Rotated `sessions_log_*.jsonl` archives are scanned into a separate cache keyed on which archive files exist, not on the current log's mtime: once rotated out, an archive never changes again (see NOTES.md, "Rotation trigger"), so a `session_end` (which only ever touches the current log) no longer forces a full re-read of every past archive too. `format_duration(seconds)` — display formatting only, `"XhYY"`/`"Xd YYhZZ"`. Backs the "Total work time" line in `m_pipeline.tracking_file_details`.
- `RecentFilesCache` — the most-recently-opened files (`get(limit)`; the Pipeline menu's "Recent files" submenu, `M_PIPELINE_MT_recent_files`, shows 5), one per folder, for the *current* `get_user()` only (not the whole team) — same mtime-cached full scan of `sessions_log.jsonl` as `WorkTimeCache`, but keyed on `ts` (newest per folder wins) and filtered to `entry["user"] == get_user().lower()` instead of summed. `.get(limit=3)` never raises. Backs the "Recent" entries in the top bar menu (`menus/top_bar.py`) — each opens directly via `m_pipeline.open_file_version` given an exact file path (skips its own version-picker dialog, see `M_PIPELINE_OT_open_file_version.invoke()` in `browser_ops.py`).
- **Branch (§5)**: `copy_entries(from_filepath, to_filepath)` — appends the old block's entries onto the new one's, as-is (author/created_at untouched). `is_block_archived(shot_dir)` — cached on the shot's own `tracking.json` mtime (one `stat()` instead of a lock+read on every call; `list_active_blocks()` calls it once per shot in a sequence, and the enum callback that drives it re-invokes on every redraw) — / `list_active_blocks(project_root, sequence_label=None)` — the one point of truth every block enumeration goes through instead of its own raw glob (already wired into `shot_items()` in `browser.py`), skips the reserved `old/` (`ARCHIVE_DIRNAME`) sibling folder by name. `archive_folder(path)` moves a folder into that `old/` sibling next to it, collision-safe (timestamp suffix on a name clash) — used on the branched-out composition and, per dropped shot, its render folder. `active_shot_owners(project_root, sequence_label, config)` — `{shot_number: owning folder}` across every active file in a sequence — backs both that skip-if-still-used check and `M_PIPELINE_OT_edit_block_structure`'s own shot-number-conflict warning/block. The `archived: true` flag itself is still set inline in `M_PIPELINE_OT_edit_block_structure.execute()` (`operators/shot_ops.py`) — kept alongside the move since `ProjectScan`'s walk would otherwise still surface a moved block.
- **Sidecar paths** (`lib/tracking.py`): `tracking_json_path(filepath, must_exist=False)` and `_meta_path(filepath, suffix)` are the only places a `tracking.json` / `.wipmeta` / `.stablemeta` path is built. Owner folder decided from the name (`_owner_dir()`: `.blend` → parent, else the folder itself), never `is_file()`. Every writer but `create_tracking()` passes `must_exist=True`; `create_tracking()` and `_meta_path()` only accept a `.blend`. See NOTES.md "tracking.json: one path, never created by a write".
- `ProjectScan` (`lib/tracking.py`) — background refresh for Project monitoring, started by `m_pipeline.tracking_monitor`, the window's Refresh button (`m_pipeline.tracking_refresh`): reader thread (pure os/json: `_walk_owner_dirs()` — only `assets/`, `library/`, `shots/`, never `renders/`, and never below a tracked folder — `_collect_folder()` -- its `started` departments: the latest stable's `departments_started` (cumulative, written by `create_stablemeta()` and `set_department_validated()`), or for a stable made before it `_started_before()`, which reads the older stables then wipmetas only for the required departments otherwise "not started" --, `_read_link_targets()`, `read_json_quiet()`) + main-thread timer applying results to `TrackingStatusCache` and the linked-by index. See NOTES.md "Popups on a network share…".
- `find_linked_by(project_root, filepath)` — every folder linking into filepath's own, for `m_pipeline.tracking_file_details`'s "Linked by" list. Reads an inverse index (`_linked_by_index`, target folder → set of linker folders) built by `ProjectScan` — memory only, called by `draw()`; with no index for this project yet it starts a scan and returns `[]` (the popup shows "Linked by: scanning project...").

### Snapshot (`snapshot.py`)
- Production snapshot export, see NOTES.md "Production snapshot". `read_snapshot_raw(root)` (disk only, thread-safe) → `build_snapshot(raws, config, meta, farm=None)` (memory, main thread; `farm` = `farm_activity()`: with each item's `to_check` labels, the "Last render" pills, `_render_cell()` / `_farm_pill()`) → `render_html(snapshot)` / `render_review_xlsx(snapshot)` (dict → str/bytes, no bpy). `write_snapshot()` = render + write, run on a thread. Progress: `_department_score()` per department into `item["scores"]` (validated 1, not started 0, else `progress_weights(config)`: `PROGRESS_WEIGHTS` for wip, rework and an open RTK on that department (`item["rtk_departments"]`), overridden by the project's `snapshot.progress`), `item["progress"]` their mean; the red outline goes on any state with an open RTK, `average_progress()` for groups and the `meta["progress"]` totals. Review import: `import_review_xlsx()` (notes), then `review_description_changes()` -- the rows whose non-empty description differs from `description_exported` (hidden column, schema 2; none for a schema-1 template) and from the current one, applied all or none by `M_PIPELINE_OT_review_descriptions`'s confirm dialog. `department_progress()` gives each table's "All" row, from `item["scores"]`. `_render_overview()`: the *Progress* block above the filters (stat tiles, `_render_timeline()` with a schedule, then `_overview_card()` per section: a stacked bar of department tasks by state -- `_TASK_STATES`, "rtk" for one in `rtk_departments` whatever its state --, `_bar_list()` by group and by department, `_heatmap()` group × department; pace pills and the timeline's colours from `_pace_band()`, a spreadsheet's 105 / 100 / 90 % bands); `meta["schedule"]` (`project_schedule()` from the config's `snapshot.schedule`, typed day first in Edit project and read by `parse_day()` -- also the review import's text dates, `parse_review_date()`: start, end, days_off, worked_days as ISO weekday numbers; `schedule_progress()` on the scan's day: `working_days()` is NETWORKDAYS.INTL, `nth_working_day()` the day a section's Done reaches) adds the expected progress, its tile, the timeline (one band per section on a scale of planned progress: expected line, Done fill, the gap between them coloured) and the hairline on each bar. Every section goes through `_section()`: a `<details class="sec" open>` -- `_JS`'s `unfold()` opens the one a link points into, and all of them before printing. Sticky column headers: a `.stuck` copy of each table's `<thead>`, fixed under the nav while the real one is scrolled past (`place()` on scroll, `size()` copies the column widths on load/resize/filter/column/fold changes) -- `position:sticky` can't, inside `.scroll`'s horizontal scroll box it sticks to the box. Notes: in a row under their item's (`_notes_row()`, folded at load, lined up with the name past a `.nspace` spacer the thumbnail column's width -- `data-col="thumb"`, so the Columns menu hides it with the column; `_notes_toggle()` the row's "n notes" button, the nav's *Notes* folds/unfolds them all; `apply()` hides a notes row with its item, and prints them all), every thread is exported, `_thread_closed()` (done root, no pending reply -- `filter_review_boxes()`'s hide_done rule) marks the ones the page hides until "Show closed".
- `SnapshotJob(fn, *args)` — runs one step on a thread, polled by `M_PIPELINE_OT_export_snapshot.modal()` (`operators/tracking_ops.py`).
- Snapshot dict: `{"meta", "assets", "shots", "notes"}`; each item carries `departments` (`done`/`rework`/`wip`/`todo`, absent = not required), `wip_version`, `stable_version`, `current_version`.
- Review import: `read_xlsx_grid(path)` (first sheet → `{row: {col: text}}`), `read_review_xlsx(path)` (schema/author/date/rows), `import_review_xlsx(path)` → `{"imported", "duplicates", "skipped": [(label, reason)]}` — one entry per text line, skips lines already imported (same file/text/author, `source == REVIEW_SOURCE`). Backs `M_PIPELINE_OT_import_review`.

### Thumbnails (`thumbnails.py`)
- Asset/shot thumbnails, see NOTES.md "Thumbnails". `thumbnail_path(shot_render_dir)`, `source_frame()` (middle frame of the latest render), `exr_layer()` (layer of a multilayer EXR, header only), `thumbnail_jobs(dirs, v_prefix, force=False, size)` (missing, stale, or not at `size` -- read off the JPEG header by `jpeg_size()`) — all pure os. `thumbnail_size(config)` — the project's `thumbnails.size` (Edit project), 240 by default. `run_thumbnail_jobs(jobs, blender_bin, ffmpeg_bin, size=, wait=True)` runs `templates/make_thumbnails.py` in one headless Blender: waited on (snapshot thread, returns `{dst: "ok" | reason}`) or detached (`farm/post_render.py`'s `refresh_shot_thumbnail()`, at `compilation_finished`).
- `owner_render_dir(project_root, owner)` — the render folder whose thumbnail stands for an asset/shot (a block → its first shot). File details: `load_file_thumbnail(folder)` / `unregister_thumbnail_previews()` (`panels/tracking_panel.py`), a `bpy.utils.previews` collection filled on click, never in `draw()`.
- Snapshot side: `read_snapshot_data(root, thumbnails, v_prefix)` (`snapshot.py`) = `read_snapshot_raw()` + thumbnails brought up to date + read as base64.

### Handlers (`handlers.py`)
- `post_load_handler` — session, library-update check (always, even read-only), lock (+ its heartbeat refresh), read-only gating (silent for `stable`/`profile`/`reopened` — flags the reason via `set_opened_as_read_only()`, the top bar indicator carries it; still a `M_PIPELINE_OT_text_popup` for the lock case), auto-version proposal
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
- `render_root(project_root, owner_dir)` — the render folder of an asset/shot folder: `renders/<seq>/<shot>` for a shot, `renders/assets/<prefix>/<asset>` (or `library/...`) otherwise; used by the farm's `compute_output_path()` and the snapshot. `latest_render_dir(shot_dir, v_prefix)` — a shot's most recent render increment folder, read from its name (`vNNN_MMM`), never mtime; pure os. `latest_shot_mp4(project_root, sequence_label, shot_label, config=None)` — the mp4 in it
- `resolve_block_sources(filepath, project_root, config=None)` / `resolve_sequence_sources(sequence_label, project_root, config=None)` — the two providers behind §1.6's "one button, two scopes": `(shot_label, mp4)` pairs for a block's own enumeration, or for every shot ever rendered in a sequence ("sq030" -- the Render dialog's Preview mode has no file to start from). Submitted by `submit_preview()` / `request_sequence_preview()` (`operators/preview_ops.py`). Filesystem-only, no `bpy` — works for any file, open or not.

### Saving (`saving.py`)
- `WM_OT_safe_save` (`wm.safe_save`) — Ctrl+S override; direct save outside the project or when not read-only, otherwise gates on lock/`-stable`/read-only-origin with a popup (stable: Save / Increment / Cancel; read-only-origin: Save & Increment / Cancel). The popup itself is opened via `_open_popup()`, deferred one timer tick rather than called synchronously from `invoke()` — calling `action_popup` synchronously there made `invoke()` forward its inner `RUNNING_MODAL`, entangling the two operators' modal state so no button in the popup would reliably close it.

---

## farm/ — what's implemented

Two roles, coordinated purely through JSON files under `config/.farm/` on the shared project drive — no SSH, no direct machine-to-machine connection (see `docs/design.md`, "No SSH, push-pull coordination over the shared drive", for the rationale).

- **Monitor** (`monitor.py`) — one per project (`monitor.lock`: heartbeat = best-effort `update_tick` rewrite + `os.utime()` each tick, readers take the newer, see NOTES.md "Windows: replace/delete refused…"). `launch_monitor()`, `is_blender_monitor()` (read-only; keeps its last answer if a read fails), `stop_monitor_loop()`, `job_request()` (writes an incoming render request — `shot_override`/`only_shots` are set only on a per-shot job created by a block's own split, never at submission, see below), `request_preview_compile()` (writes an incoming preview-compile request, §1.6 — same `job_*.json`/`scan_requests()` path, distinguished purely by its own first stage, `initial_stage="preview_queued"`, not a `kind` field), `request_monitor_kill()` (async: writes a kill request, the monitor stops itself on its next tick), `job_cancel_request(job_id, target_uuid, user)` (async: asks one worker to stop rendering a specific job -- UI: the "X" button per job/worker in the farm dashboard), `archive(job_path)` (moves a job file + its render logs to `queue/archives/`, each log through `compact_log()` first -- the dashboard's "✓" button, or `farm_housekeeping()` below; reaching "archived" in a job's own `stage_history` does NOT move it by itself, see below), `farm_housekeeping()` (end of every `monitor_tick()`, runs at most hourly: archives jobs that ended well -- `finished`/`split_finished`/`preview_finished` -- more than `farm.auto_archive_hours` (24) ago, compacts the big logs of jobs already over still in `requests/`, deletes archived logs older than `farm.archive_log_days` (14); failed jobs stay. See NOTES.md "Farm logs: kept small"), `load_job_details(job_id)` / `get_job_details()` / `get_job_details_path()` / `get_job_details_logs()` (the Farm popup's job detail view: one read of `actives/` then `archives/` on click, `draw_farm_job_details()` only reads the cache -- the path feeds its "open JSON" button, `wm.open_folder` on the file; `monitoring_detail("job")` (`lib/core.py`, in memory) switches the popup, same pattern as `monitoring_detail("file")`)
- **Worker** (`workers.py`) — `launch_worker()` (its file's `ffmpeg` / `ffmpeg_version`: `_ffmpeg_version()`, `resolve_ffmpeg()` then `ffmpeg -version` run once, before the file's lock; see NOTES.md "Workers with ffmpeg"), `is_blender_worker()`, `kill_worker()` (returns bool: True if this machine ends up worker-free), `this_instance_is_worker()` (runtime flag the UI reads — never a Scene property, see NOTES.md "Farm popup…"), `execute_compile_request()` / `scan_compile_processes()` (a preview sent by the host, `compile_<job>_<uuid>.json`, status `compile`; its end written in the job by the worker -- NOTES.md "Previews on a worker"), `execute_render_request()` (one Blender per job: `templates/worker_render_entry.py` with the job's `chunk_size` -- never the project's -- and this machine's id; the entry's `render_chunks()` -- passes over the chunks while one rendered something, `render_chunk()` each -- claims a chunk, renders each missing frame with Blender's own animation render over a one-frame range (File Output nodes numbered, as with `-a`) to a hidden `.<machine>_<pid>_#####.tmp`, renamed onto its final name (`FINALS`, `frame_path()` read before the output is switched to the tmp), rewrites its claim before and after each frame, appends to the `.saved`, releases it; exits 0 once every chunk is on disk or held elsewhere, or on a stop; a failure leaves its claim for the host; see NOTES.md "Farm 1.1.0: chunks replace placeholders"), `check_stuck_renders()` (the frame's name from this machine's claim, `_frame_in_progress()`), `apply_custom_preset()` (per-job render settings override, `.py` or `.json`; also applied by the setup, in memory, so `output_extension`/`fps` are read after it; reads the job without a lock, `_read_job_quiet()`; `strict=True` -- the render entry -- raises instead of logging, so a preset that can't be applied fails the render rather than rendering with the .blend's settings, see NOTES.md "Render preset: read without a lock, fail the render"), `stop_worker(kill_render)` (what quitting Blender -- the root `unregister()` -- and a project switch call: `kill_worker()` alone left the render subprocess running), `scan_render_requests()` (pending requests, read without a lock, a vanished one left out), `idle_machines()` (idle and not targeted by a pending request -- computed once per monitor tick; never a worker whose file doesn't announce this addon's `FARM_PROTOCOL`, logged once). `read_workers(workers_dir)` — every worker with a recent heartbeat, pure os/json (no lock, thread-safe: the farm snapshot's reader thread uses it); `scan_workers()` — the same for the active project, cached for `_WORKERS_CACHE_TTL` (~1.5s) since the Render dialog's machine enum reads it on every redraw. The farm popup's Workers tab reads neither: `draw_farm_workers()` reads the snapshot's `workers`.
- **Process logs** (`dispatch.py`) — `popen_logged(cmd, job_id, stage)` (every farm subprocess: output appended to `request_<job_id>.log` under a stage header, never a PIPE — see NOTES.md "Farm subprocess output: files, never pipes"), `read_process_log(proc)` (that stage's section only), `discard_job_log(job_id)` (called by `scan_queue()` when a job ends well), `saved_frames_path(job_id, uuid)` (`workers.py`: the machine's record of the frames it wrote, one `"<dispatch_id> <frame> <time>"` line each -- the time on the worker's own clock, none from an older worker -- appended by the render entry after each frame; `discard_saved_frames(job_id)` (`queue.py`) deletes every machine's once the render is judged, with the `.stop` flag a crashed worker left; `frame_seconds(text)` turns it into the seconds each frame took, two lines in a row of one render; next to it `render_stop_path(job_id)` -- "stop after this frame", read by the render entry; `queue._note_frames()` turns the records into each machine's pace and `frame_machines`, one letter per frame, read through `machine_for_frame()` -- Farm monitoring's job detail and File details' last render, `draw_frame_lookup()`; `_note_machine_names()` keeps `machine_names`, {uuid: "user (id)"} of every machine of the job, in the job and its render history -- `machine_label()` (`panels/farm_panel.py`) names a machine by its live worker, else that, else its id), `compact_log(path)` (a kept log shrunk in place: Blender's "Fra:" progress lines dropped but the last ones, then head + tail past `LOG_KEEP_BYTES`). Worker renders: `request_<job_id>_<uuid>.log`, deleted by `scan_worker_processes()` on exit 0.
- **Queue** (`queue.py`) — `scan_requests()` (incoming → active; reads the request's own `initial_stage` if it names one, else `"queued"` — the one hook a request kind needs to join the stage machine with its own first step), `scan_queue()` (advances every active job one stage — render jobs, a block's split, and preview compiles all live in the same flat `elif` chain, keyed on stage name alone; jobs read by `read_active_jobs()`, without a lock, archived/orphaned ones skipped while their file is unchanged; highest `priority` first, then oldest; `idle_machines()` once per tick, minus this instance's own worker while a job waits for its setup -- see NOTES.md "Monitor tick: read without a lock, decide once"), `scan_processes()` (polls locally-tracked `Popen`; its generic `"*_start"` → `"*_finished"/"*_failed"` completion detection is reused as-is by both the split and the preview compile, no new code needed there), `corrupted_frames()` (the frame check's ffmpeg output -- `level+info`, `-threads 1`, `showinfo` -- turned into frame numbers) and `_send_back_bad_frames()` (end of the frame check, in `_finish_job_processes()`: corrupted frames deleted, job back to `setup_finished`, then rendered and checked again, at most `MAX_FRAME_CHECK_ROUNDS` times; see NOTES.md "Frame check: naming the corrupted frames"), `check_render_completion(job, root, data, idle)` (monitor-only, every tick of a job at `render_start`, no lock while it simply renders: `read_claims()` + `missing_frames()`, one listing each; `_dead_claims()` -- a claim is held while its machine's worker is alive (`_read_worker()`, never the stale-filtered `scan_workers()`; `_worker_gone()`), rendering this job, with the claim's pid -- freed under the job's lock by `_free_claims()`, a failed or stuck render counted, `_failed_this_render()` on its `dispatch_id`, in `chunk_failures`/`failed_machines`/`stuck_frames`; `MAX_CHUNK_ATTEMPTS` (3) machines on one chunk -> `fail_reason` + `cancel_requested`, then `_stop_render()` -- requests withdrawn, cancel files -- and `_end_render()` once nobody is on it (`_on_this_render()`); all frames, no claim -> `_finish_render()` (`rendered_by`, `_note_frames()`, `_note_machine_names()`, `.tmp` and `remove_claims()`); free chunks -> `_send_to_idle()` (`machines_for()`, one per free chunk less those starting or waiting, one in "single"), none -> waiting requests withdrawn; nobody on it and `_no_machine_left()` -> `render_failed`; see NOTES.md "Farm 1.1.0: chunks replace placeholders"), `retry_job()` / `failed_stage()` (a failed job rewound to the stage before the one that failed -- refused, `PipelineError`, if its `.blend` no longer exists, `_RETRY_STAGE` -- same `output_path`, no new increment; a render retry clears `chunk_failures`/`fail_reason`, and `failed_machines` if no other live worker is allowed; UI: `m_pipeline.farm_retry_job`, which also brings a failed job back from `archives/`), `_flag_to_check()` (`compilation_finished` only moves on once `mark_render_to_check()` returned True -- retried each tick, given up after `_TO_CHECK_ATTEMPTS`), `construct_history()` (duration first `render_start` → last `render_finished`, machines from `rendered_by` -- `used_machines` is emptied by the local stages that follow -- plus `source_file`/`output_path`/`shot_override`), `construct_split_history()` (a block's split outcome — `split_into`/`skipped_shots`/`absorbed_shots`, see "Multishot blocks" — appended to the block's own `.pipeline/render_history.json`, mirroring `construct_history()` for an ordinary job)
- **Chunks** (`chunks.py`) — `chunk_frames(start, end, size, k)` ((first, last) of chunk k, from 0, the last cut short; None past the range) and `chunks_number()`, both pure; a claim per chunk in progress, `claims_dir(job_id)` / `claim_path(job_id, k)` (`queue/claims/<job_id>/claim_<k>.json`): `try_claim()` (exclusive create -- False if held or pending deletion, any other error raised, a half-created claim removed), `write_claim()` (`write_json_atomic()`, no lock: one writer), `release_claim()` (already gone is fine), `read_claims(job_id)` (one listing; an unreadable claim is `{}`, still held), `free_chunks()` (pure), `remove_claims(job_id)` (the folder, at `render_finished` and by `archive()`); `read_claims_in(folder)` for the farm snapshot's reader thread (`loop._claims_for_jobs()` -> the monitor cache's `claims`, {job_id: {k: claim}}, what Job details' *In progress* and Worker details' *Chunk* show). The Render dialog (`operators/farm_ops.py`): modes `all` / `single` (a job file's older `auto`/`placeholder` reads as `all`); the pre-render picker's items from `pre_render_script_items(presets_dir)`, "No pre-render script" first, its value set on every `invoke()` to the project's `farm.default_prerender_script` (`default_pre_render_script()`), which Edit project picks among the *edited* project's presets (`_edited_project_scripts()`). See NOTES.md "Farm 1.1.0: chunks replace placeholders"
- **Dispatch** (`dispatch.py`) — `render_dispatch(job_path, idle)`: takes its machines out of the tick's `idle_machines()` (`machines_for()`: all, or the job's assigned ones, never one in `failed_machines`, nor in `left_machines` -- one machine's Cancel, `cancel_pending_renders()` -> `_leave_job()` -- unless `with_left` (`scan_queue()`'s second pass, the machine still idle after every job); none -> `note_waiting()`, logged once per wait), re-checks the stage under its lock, fails a job whose `.blend` is gone; `single` (one machine) or one per chunk to render (`chunks.free_chunks()`), through `send_render()` (also `check_render_completion()`'s); `chunk_size()`, the project's `farm.chunk_size`, stored in the job with its `dispatch_id` -- every worker of a render cuts it the same way; `frame_paths()` lists the range's frame files, `missing_frames()` those not on disk yet (one listing of the folder). Chunks in progress: see NOTES.md "Farm 1.1.0: chunks replace placeholders"
- **Setup** (`setup.py`) — `compute_output_path()`, `resolve_job_context()` (`shot_override` routes to `shots/<sequence>/<shot_override>/` instead of the target file's own folder — how a block's per-shot jobs, all pointing at the same block file, land in separate output folders), `run_render_setup()` (launches the headless setup subprocess — deliberately doesn't compute the output path itself anymore: a possible block might split instead of rendering, only knowable once the file is genuinely open), `run_render_setup_entry()` (runs inside that subprocess — the file is only ever genuinely open here, so this is where a block gets detected and split via `_split_into_shot_jobs()` if `shot_override` isn't already set; a child's frame range is already absolute from split time, no marker re-read needed), `resolve_override_range()` (public: also used by the split to resolve each shot's override against its own sub-range instead of the whole file's)
- **Post-render** (`post_render.py`) — `checks_images()` (ffmpeg frame-corruption pass, naming the frames: see `corrupted_frames()`), `compilation()` (ffmpeg → video, via the project's ffmpeg presets), `preview_command()` (one command for the host and a worker), `ffmpeg_worker(idle)` / `send_preview_compile()` / `check_remote_compile()` (a preview on an idle worker with ffmpeg first -- see NOTES.md "Previews on a worker"), `build_concat_command()` / `run_preview_compile()` (§1.6 — concatenates a preview's resolved sources via ffmpeg's concat *filter*, decoding and re-encoding every input to the project's own resolution/fps, never the concat demuxer's `-c copy`: a block's shots can come from different render sessions and are never assumed to already match)
- **Loop** (`loop.py`) — `farm_tick()` (the shared timer both roles run through), `register_farm_loop()`, `stop_farm_role_for_project()` (used when the active project changes without quitting Blender); two UI-only redraw timers, split by cost, both reading on a background thread (`_BackgroundRead`) and applying on the main thread: `_refresh_tick()`/`register_refresh_timer()` (full snapshot — status, jobs, frame counts, workers: `_read_farm_snapshot()` → `_apply_farm_snapshot()`, only while the farm monitor popup is open — `_build_job_entry()` also projects `skipped_shots`/`absorbed_shots` into the dashboard snapshot, and the pace: `_frame_seconds_for_jobs()` reads the `.saved` records of the jobs rendering, parsed again only once changed, `_time_left()` divides the frames left by the summed pace of the machines rendering the job *now* -- each one's last `_PACE_FRAMES` frames, the job's average for one not timed yet -- see NOTES.md "Time left: per machine, from each frame's time") and `_status_tick()`/`register_status_timer()` (status only — `_read_farm_raw(want_jobs=False)` → `_status_from_monitor_raw()`, just `monitor.lock`, liveness via `monitor_last_tick()`/`monitor_age_status()` — always running while the addon is enabled, so the N-panel farm header stays live even collapsed). The reader functions are pure os/json, no lock; the actives/incomings folders are only re-read when their mtime changed (`_scanned_mtimes()`). `refresh_monitor_cache()`/`refresh_monitor_status()` run the same reads synchronously (project switch, right after a launch).

Job stage machine: `queued → setup_start/finished/failed → render_start/finished/failed → checks_images_start/finished/failed → compilation_start/finished/failed → finished → archived` (a job interrupted by a crash is resumed, not orphaned: `recover_interrupted_jobs()` at monitor launch adopts a still-running process by PID or rewinds the stage to redo it, and a render lost by its worker is re-dispatched — see NOTES.md "Crash recovery: resume, don't orphan"; `orphaned` only remains on jobs marked by older versions). `"archived"` is a stage_history marker, not a location: `scan_queue()` appends it right after `finished`/`*_failed` so it stops touching the job again, but the file stays in `queue/actives/` (and keeps showing in the dashboard) until someone clicks "Archive" (`M_PIPELINE_OT_farm_archive_job` → `archive()`) -- or, for a job that ended well, until `farm_housekeeping()` archives it `farm.auto_archive_hours` later.

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
- **Creation** (`M_PIPELINE_OT_create_shot`, `shot_ops.py`): a shared `window_manager.shots_list_creation` (`PipelineShotItem`: shot number + start frame) drives both the naming preview and the actual file — `m_pipeline.add_multishot_item`/`remove_multishot_item` edit it (a remove button per row, by index; never the last row: its poll()), `_draw_shot_list`/`_draw_block_warning`/`_draw_timeline_warnings`/`_draw_naming_preview` (module-level, shared with the branch operator below) draw it. First shot's start frame, and the block's own `end_frame` default, both come from config's `default_frame_start` (1001 if unset), not a hardcoded 0.
- **Camera/marker scaffolding (§1.4)**: `build_shot_scene()` creates one camera + one timeline marker per shot (`cam_sq040_sh045_v001`), all sharing one CAM/SET/ASSETS collection set. `derive_shot_subranges()` is the read-back: live off `scene.timeline_markers`, only ever called once the file is genuinely open (see split, below) — never guessed from the filename.
- **Split at render (§1.2)**: happens at **setup time**, not submission — `run_render_setup_entry()` (the file is only ever genuinely open there). Submission (`M_PIPELINE_OT_farm_request_render`, any path: open file, cascade selector, or the batch render list) always writes exactly *one* `job_request()`, whether the target turns out to be a block or not; a submission-time checklist (filename-derived, `_populate_subshots()`) just rides along as that job's `only_shots`. `_split_into_shot_jobs()` (`farm/setup.py`) then fans a real block into one ordinary job per shot, each with its frame range already resolved to absolute *at split time* (so a child never has to reopen the file to re-derive what the split already knew) and `shot_override` set (routes its output to its own `shots/<sequence>/<shot_override>/` folder, never the block's own).
- **Divergence (§2)**: handled entirely *by the split*, not a separate submit-time or save-time check (deliberately rejected — the win is small, at most tens of seconds, and a second mechanism duplicating what the split already has to compute isn't worth it). Two kinds, both surfaced never silently:
  - `skipped_shots` — promised by the name, no marker found.
  - `absorbed_shots` — a marker found but not in the name; its frames merge into the preceding *promised* shot's range instead of getting their own (native Blender behavior: a camera switch with no boundary of its own just continues the previous shot).
  Both live on the parent job (visible in the farm dashboard for its brief `split_finished → archived` window) and permanently in the block's own `.pipeline/render_history.json` (`construct_split_history()`).
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
- "Monitor" names two different things in the codebase on purpose, left as-is: the farm coordinator role (`launch_monitor`, `monitor_tick`, `monitor.lock`) and the UI dashboard popups (`M_PIPELINE_OT_farm_monitor`, `M_PIPELINE_OT_tracking_monitor` — "show a popup view of X", unrelated to the role).
- `auto_worker_on_open` only fires at two specific moments (Blender startup, active-project switch) — no continuous re-check.
- **Pipeline log window** — `m_pipeline.pipeline_logs` (`operators/log_ops.py`, `search=` to open it filtered) opens the third monitoring window (`lib/monitoring.py`, kind "log"; `M_PIPELINE_PT_log_monitoring`), filters in memory (`PIPELINE_PG_log_monitoring`, `WindowManager.pipeline_log_monitoring`); `draw_pipeline_logs()` (`panels/logs_panel.py`) pages it to the window (`rows_that_fit(..., _LINE_UNITS)`, `paginate("log")`, `draw_pager()`); `read_log_tail()` reads the last 1 MB of `pipeline_log.jsonl` on open/refresh/F5, on a thread (`load_pipeline_log()`, its timer redraws the window), never in draw(); a line click copies the whole entry (`m_pipeline.copy_log_line`). Keys: `_KEYMAP_ITEMS` (`lib/monitoring.py`) -- each named for the preferences' Shortcuts section (`draw_addon_keys()`), the windows' on, the global ones off; `m_pipeline.monitoring_refresh` is F5.
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
