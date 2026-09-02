# Execution flow reference

Every handler, timer, and cross-cutting operator in the addon, traced against the actual code (not an aspirational design). Each section is a trigger (Blender handler, timer, or operator) and the decision tree it runs. Read `├──`/`└──` as branches of a condition, `│` as "still inside the branch above", `->`/`→` as "then calls / then shows".

---

## Worked departments (live toggle, no popup)

Not a handler -- a button row in `asset_panel.py`/`shot_panel.py`, drawn
whenever the open file is a tracked asset/shot with required departments.
Replaces an earlier popup-on-close/quit design (see git history): a modal
popup queued from `load_pre`/`exit_pre` isn't guaranteed to render -- by
`exit_pre` time Blender is already tearing down the window manager. Instead:

```
├── draw() : TrackingStatusCache.get(this_file)["departments_required"] for
│   the button list, get_session_worked_departments(this_file) (in-memory
│   cache keyed by the .wipmeta path, empty until this session has actually
│   toggled something -- an untouched file records nothing) for which ones
│   show `depress=True`
└── click : pipeline.toggle_worked_department(department=d)
      -> wipmeta_add_work(this_file, toggled_set) -- writes straight to
         .wipmeta AND updates the in-memory cache in the same call, so no
         redraw ever re-reads the file (see lib/tracking.py's
         _session_worked_cache)
```

---

## Validated departments (live toggle, no new -stable version)

Button rows in `tracking_panel.py`'s sidebar and the monitoring dashboard's
`pipeline.tracking_file_details` popup, wherever validated departments are
shown. Some departments (e.g. "render") aren't tied to editing the file at
all -- forcing a new -stable version just to flip one off/on doesn't fit.

```
├── draw() : get_current_departments(file) for depress=True state (reads
│   TrackingStatusCache -> latest .stablemeta's departments_validated)
└── click : pipeline.toggle_validated_department(department=d, filepath=file)
      -> set_department_validated(file, d, not current) -- mutates the
         *latest* .stablemeta's departments_validated in place
      ├── no .stablemeta exists yet (asset never marked stable) :
      │     PipelineError -- "Mark at least one version as stable before
      │     validating individual departments." (nothing to mutate)
      └── exists : written in place, TrackingStatusCache picks it up on
            next redraw (same mtime-based invalidation as everything else)
```

Note: `create_stablemeta()` (see "Increment version / Mark as stable" below)
already rebuilds departments_validated from scratch on every new -stable
version, using only what's checked in that dialog at the time -- this isn't
a new fragility, `departments_validated` was already a rolling status to
reconfirm each time, not an immutable historical snapshot.

---

## File opened

`bpy.app.handlers.load_post` → `post_load_handler`

```
├── no filepath (new/unsaved scene) : return
├── log("file_open")
│
├── file in active project ?
│   ├── yes : continue
│   └── no  : file belongs to another *known* project (opened_projects) ?
│       ├── yes : popup "Different project detected"
│       │         -> "Not now" | "Switch to this project" (sets active_project_root,
│       │            save_project_data, session_update) : return
│       └── no  : return (unknown file -> total silence, never touched again)
│
├── bpy.app.background (headless / farm subprocess) ?
│   └── yes : return (no session/lock/popup outside interactive Blender)
│
├── scan_sessions() : glob config/.sessions/.session_*.json, close_session()
│   any whose last_ping is older than 40s (crash detection for OTHER users/processes)
│
├── session_update() : create/refresh config/.sessions/.session_{pid}.json (THIS session)
│   └── if THIS session's own file changed since the last update (switched
│       files without quitting Blender) : close the OLD file's session first
│       (session_end, with duration, logged to sessions_log.jsonl) before
│       opening the new one -- otherwise it'd sit frozen and get swept much
│       later by scan_sessions(), misreported as a crash
│
├── check_library_update() : for every bpy.data.libraries entry inside the active
│   project, compare against get_last_file_stable() of its asset folder --
│   runs unconditionally here, BEFORE the read-only gate below, so a -stable
│   file still gets checked
│   ├── all up to date : nothing
│   └── outdated ones found : PipelineAction "New stable version available"
│         -> "Not now" | "Update libraries" (library_updates(): repoint +
│            reload each library, then wipmeta_update_libraries() to rewrite
│            the linked-libs paths recorded in this version's .wipmeta)
│
├── always_read_only pref, OR opened_as_read_only == this_file already,
│   OR filename tag == "-stable" ?
│   ├── yes : set_opened_as_read_only(this_file)
│   │         PipelineAction "Opened as Read-Only"
│   │         -> "Continue read-only" | "Increment outside stable" (opened
│   │            deferred one timer tick, same precaution as the save-guard
│   │            popups -- pipeline.increment_version INVOKE_DEFAULT)
│   │         return
│   └── no  : continue
│
├── acquire_lock(this_file, machine_id)   [kept alive afterwards by heartbeat_30s, see Clocks]
│   ├── failed (another machine's lock is live) :
│   │     set_opened_as_read_only(this_file)
│   │     informative popup "Opened as Read-Only" (who holds it, from the lock file) : return
│   └── acquired : continue
│
└── pipeline.auto_version (INVOKE_DEFAULT)
    ├── this_file is the latest version on disk ?
    │   ├── yes, and file's mtime date < today :
    │   │        ├── silent_auto_increment pref on : save_as() silently (mode=auto_increment)
    │   │        │      -> create_wipmeta(new, this_file, "auto_increment") : stays on the new file
    │   │        └── silent_auto_increment pref off (default) : invoke_confirm "New version?"
    │   │               ├── confirm "Increment" : same as the silent path above
    │   │               └── cancel : do nothing, stays open on this file
    │   ├── yes, and mtime date == today (already worked today) :
    │   │        get_last_wipmeta(this_file)'s edited_by == someone else ?
    │   │        ├── yes : invoke_confirm "Already worked on today" (always
    │   │        │         asked, ignores silent_auto_increment)
    │   │        │         ├── confirm "Create a new version" : save_as()
    │   │        │         │      (mode=branch_from) -> create_wipmeta(...)
    │   │        │         └── cancel : do nothing, stays open on this file
    │   │        └── no (same user, or no wipmeta yet) : do nothing : CANCELLED
    │   └── no (a newer version already exists) :
    │         invoke_confirm "Create a new version?"
    │         ├── confirm : save_as() (mode=branch_from) -> create_wipmeta(...) : new file
    │         └── cancel  : do nothing, stays open on this older (still-locked-by-us) file
```

Note: the read-only and library-update proposals above used to be dedicated
`invoke_confirm`-based operators (`read_only_notice`, `library_update_notice`),
kept off the shared `PipelineAction`/`pipeline.action_popup` mechanism because
`action_popup`'s `invoke_popup` didn't reliably auto-close when a choice button
was clicked (see `PIPELINE_OT_action_popup._force_close()`). Now that that's
fixed, both were converted to plain `PipelineAction`s (`_propose_read_only_increment`
in `handlers.py`, inlined in `tracking.check_library_update()`) like everything
else in this file. `pipeline.auto_version` above still uses `invoke_confirm` --
not converted yet, since its own `execute()` does the real work directly off
`self.is_branch`, not just a delegated `bpy.ops` call.

---

## Append / Link done

`bpy.app.handlers.blend_import_post` → `import_post_handler` → `import_warnings`

```
├── no imported items : return
├── any item has append_action == "MAKE_LOCAL" (i.e. an APPEND happened, not a link) ?
│   ├── yes :
│   │   ├── source library is inside the active project ?
│   │   │   ├── yes : popup "Append done : Link not better ?"
│   │   │   │         -> "Ignore" | "Clean & reLink" (delete the appended datablocks,
│   │   │   │            re-import them as linked instead)
│   │   │   └── no  : popup "Append done : Link not better ?"
│   │   │         -> "Ignore" | "Clean" (delete the appended datablocks, no relink --
│   │   │            source isn't in the project, nothing to link back to)
│   │   └── (either way, return after the popup)
│   └── no (a LINK happened) :
│       ├── source library is OUTSIDE the active project ?
│       │   ├── yes : popup "External project Link done ?"
│       │   │         -> "Ignore" (wipmeta_add_link: record it in this version's .wipmeta)
│       │   │            | "Undo Link" (clean_append -- removes the linked datablocks)
│       │   └── no  : wipmeta_add_link(this_file, data) silently -- linking within the
│       │             project is the expected case, just record it, no popup
```

---

## Want to save

Save button (NOT overridden) or Ctrl+S (overridden → `wm.safe_save`)

```
├── file NOT in active project : bpy.ops.wm.save_mainfile() directly : return
└── file in active project :
    ├── opened_as_read_only != this_file : bpy.ops.wm.save_mainfile() directly : return
    └── opened_as_read_only == this_file :
        ├── acquire_lock(this_file) to save
        │   ├── failed (someone else holds it now) :
        │   │     popup "Save Impossible" (who holds it) : CANCELLED, lock not touched
        │   └── acquired : continue
        ├── filename tag == "-stable" ?
        │   ├── yes : popup "You're on a stable file !" (opened deferred one
        │   │         timer tick, not synchronously from this invoke() --
        │   │         same popup-chaining precaution as the choices below)
        │   │         -> "Save" (save_mainfile, releases the lock)
        │   │          | "Increment" (releases the lock, then -- deferred one
        │   │            timer tick, same popup-chaining precaution as below --
        │   │            pipeline.increment_version INVOKE_DEFAULT)
        │   │          | "Cancel" (releases the lock, no save)
        │   └── no  : popup "Read-Only Origin" (opened deferred one timer
        │         tick too)
        │         -> "Save & Increment" (releases the lock, then -- deferred one
        │            timer tick, same popup-chaining precaution as
        │            pipeline.create_project's own INVOKE_DEFAULT call below --
        │            pipeline.increment_version INVOKE_DEFAULT)
        │          | "Cancel" (releases the lock, no save)
        └── dismissed without clicking (ESC / click-away) : action_popup.cancel()
              runs the action's on_dismiss, which releases the lock too
```

---

## Save done

`bpy.app.handlers.save_post` → `save_post_handler`

```
└── session_update()   (same file-in-active-project guard as above; no read-only check here)
```

---

## Increment version / Mark as stable

`pipeline.increment_version` — panel button "Increment version" / "Mark as stable", Save-guard's "Save & Increment"/"Increment", or `read_only_notice`'s "Increment outside stable"

```
├── invoke() pre-fills:
│   ├── worked_departments = get_session_worked_departments(this_file) --
│   │   whatever's already toggled in the asset/shot panel this session,
│   │   not asked from scratch (both read/write the same .wipmeta)
│   └── "departments validated" suggestions from (last stable's validated
│       departments) minus (departments already worked on since)
├── dialog : tag (none / any config tag, e.g. "stable") + worked departments
│   this session + [if tag == stable] departments now finished -- both
│   drawn expand=True (buttons side by side), not a dropdown menu
└── execute() : save_as(tag) -> new file
    ├── previous_file is itself a -stable (only has a .stablemeta, no
    │   .wipmeta) ? skip wipmeta_add_work -- else :
    │     wipmeta_add_work(previous_file, worked_departments)
    ├── tag != "stable" : create_wipmeta(new_file, previous_file, "manual_incrementation")
    └── tag == "stable" : create_stablemeta(new_file, previous_file, finished_departments, "")
```

Stays open on the new file — it is NOT flagged `opened_as_read_only` automatically; that only happens the next time a `-stable` file is *opened* (see "File opened" above).

---

## Pre file quit

Actual Blender quit only: `bpy.app.handlers.exit_pre` → `on_quit_handler`.
Switching files within the same session goes through `load_post` instead
(see "File opened" above) -- exit_pre does NOT fire on a plain File > Open/New.
No worked-departments capture happens here anymore (see "Worked departments"
above) -- that's already been written to disk live, well before quit.

```
└── close_session() : log session_end (flags "(crash)" if the last heartbeat
    is stale) to sessions_log.jsonl, delete config/.sessions/.session_{pid}.json
```

No explicit file-lock release here (see `docs/sessions-and-locking.md`, and README's "Known current limitations").

---

## Worker role

Manual or automatic start (`auto_worker_on_open` pref), automatic stop.

```
├── pipeline.farm_add_self_worker : launch_worker() -- registers farm_tick via
│   register_farm_loop, refuses if another live (non-stale) worker already owns
│   this machine's worker file
├── pipeline.farm_kill_self_worker : kill_worker()
├── auto_worker_on_open (Preferences > Add-ons > Minimalist Pipeline) : if on,
│   launch_worker() also fires from two other places -- see "Activate / deactivate
│   project" below (switching TO a project) and "addon register()" below (Blender
│   startup, if a project is already active from the restored backup)
└── switching the active project away from a worker's project stops it automatically
    too -- see "Activate / deactivate project" below.
```

---

## Farm monitor role

Manual start, automatic stop.

```
├── pipeline.farm_launch_monitor :
│   ├── shutil.which("ffmpeg") not found ?
│   │   └── yes : PipelineAction "FFmpeg not found" (opened deferred one
│   │         timer tick, same precaution as its own choices below) ->
│   │         "Cancel" (stop here) |
│   │         "Continue anyway" (re-invokes pipeline.farm_launch_monitor,
│   │         skip_ffmpeg_check=True, deferred one timer tick -- same
│   │         popup-chaining precaution as pipeline.create_project's own
│   │         INVOKE_DEFAULT call below) -- checks_images/compilation would
│   │         otherwise fail silently per-job, only surfacing in the log
│   └── launch_monitor() -- becomes the monitor for the active project,
│         refuses if monitor.lock is live; if stale, requires a confirm
│         ("stale lock, take over?") before forcing it
└── pipeline.farm_kill_monitor : request_monitor_kill() -- writes a kill_*.json request,
    the CURRENT monitor's own next tick sees it, stops itself and clears monitor.lock
    (this is why it never blocks: the requester never touches the lock directly)
```

---

## Activate / deactivate project

`pipeline.set_active_project`, `.unset_active_project`, `.create_project`, `.find_project`, or the "Switch to this project" popup choice — all funnel through `lib.set_active_project_root(prefs, new_root)`:

```
├── stop_farm_role_for_project(OLD active_project_root) : if THIS Blender instance
│   is running farm_tick for the project being left, stop_monitor_loop() and/or
│   kill_worker() as applicable -- a farm role never keeps running for a project
│   that stopped being active in this instance
├── active_project_root = new_root (or "" for unset)
└── new_root is truthy AND auto_worker_on_open pref is on : launch_worker()
    for the newly active project
```

Each caller still does its own `save_project_data(prefs)` + `opened_projects` list bookkeeping around this call — `set_active_project_root` only owns the farm-role switch + the `active_project_root` field itself.

**Not done here**: `session_update()` for a file that's already open and belongs to the newly-activated project. Only the "Switch to this project" popup path calls it — activating the same project from the project list while already sitting in one of its files does NOT retroactively create a session/lock/auto_version check for that file; that only happens on the next `load_post`.

---

## Addon register()

`bpy.utils.register_class(*classes)`

```
├── load_project_data(prefs) : restore opened_projects + active_project_root from
│   Blender's user config dir (best-effort, ignored on failure)
├── prefs.user_name empty ? seed it from getpass.getuser() -- only once,
│   never overwrites an already-set name; get_user() would fall back to the
│   same getpass.getuser() at read time anyway, but only in memory -- this
│   makes it visible in the Preferences panel and correctable on a shared
│   machine (getpass, not os.getlogin(): the latter needs a controlling
│   terminal, reliably fails without one -- desktop icon, Steam, VS Code...)
├── register_handlers() unconditionally (load_post/exit_pre/save_post/
│   blend_import_post handlers + heartbeat_30s timer) -- no preference gates
│   these as a block; only unregister_handlers(), called from unregister(),
│   ever tears them down
├── register the pipeline_farm_list collection + a few Scene bools (UI collapse state)
├── set_running_project(None) : this Blender instance owns no farm role yet
├── deferred (0.1s later, once the addon keyconfig exists) : override_shortcut()
│   installs the Ctrl+S -> wm.safe_save keymap override
├── deferred (0.05s later) : active_project_root was restored non-empty AND its
│   folder isn't reachable (Path(root).exists() fails -- NAS disconnected,
│   drive unmapped) ? pipeline.unset_active_project() + PipelineAction popup
│   ("Active project unreachable") -- without this, every redraw of
│   farm_panel.py (poll()s on get_active_project_root() alone, no file needs
│   to be open) tries to resolve/stat a path under the dead mount and can
│   freeze Blender's single UI thread solid. Startup-only: doesn't catch the
│   NAS dropping mid-session.
└── deferred (0.1s later, so it runs after the reachability check above) :
    auto_worker_on_open pref is on AND active_project_root was restored
    non-empty (and still active -- see above) ? launch_worker()
```

---

## Addon unregister()

Addon disabled, or Blender quitting.

```
├── unregister_handlers() (safe even if never registered)
├── save_project_data(prefs) : best-effort backup, ignored on failure
├── unregister all classes
├── unregister_refresh_timer() : defensive only -- normally already stopped
│   by the farm monitor popup's own execute()/cancel() (see Clocks)
├── if this instance was running the monitor : stop_monitor_loop()
│   (terminates any local render subprocesses first)
├── if this instance was running as a worker : kill_worker()
└── unoverride_shortcut() : remove the Ctrl+S keymap override
```

Note: this is a *different* path from "Activate / deactivate project" above — both end up stopping the local farm role, but this one fires on addon disable/Blender quit rather than on an explicit project switch. Session closing (`close_session()`) is NOT called here directly: on a real Blender quit, `exit_pre` fires first (see "Pre file quit" above) and closes it; disabling the addon without quitting Blender does NOT go through `exit_pre`, so the session is left to expire and get cleaned up by the next `scan_sessions()`.

---

## Clocks

`bpy.app.timers`

### heartbeat_30s

Every 30s, for as long as the addon is enabled.

```
├── session_update() : refresh THIS session's last_ping
└── if bpy.data.filepath is in the active project AND opened_as_read_only
    is NOT this file (i.e. this session holds the lock, not just reading it) :
    refresh_lock(this_file, machine_id) -- re-timestamps the .lock this
    machine already owns so it doesn't cross LOCK_STALE_SECONDS (90s -- 3x
    this heartbeat's own interval, so a single missed/delayed beat never
    gets it silently stolen by the next opener while still legitimately
    in use. Never creates or steals a lock -- a no-op if it belonged to
    someone else already (e.g. it went stale and got taken during a long
    enough network hiccup that several heartbeats in a row got missed).
```

### _refresh_tick

Every ~2s, only while the farm monitor popup (`pipeline.farm_monitor`) is
open -- registered in its `invoke()`, unregistered in `execute()`/`cancel()`.
Not running the rest of the time; never touches farm state, UI only.

```
└── recompute the monitor snapshot (jobs/workers), tag_redraw() the popup's
    own region (via context.region_popup, captured every draw()) and any
    open 3D viewports.
```

### farm_tick

Registered on-demand by `register_farm_loop`, one instance owns it.

```
├── is this Blender instance the monitor ? monitor_tick(project_root) :
│   ├── scan_requests() : consume kill_*.json, move job_*.json incoming -> active
│   ├── scan_processes() : poll locally-tracked Popen (setup/checks/compilation),
│   │     advance stage_history once a job's process group finishes
│   └── scan_queue(project_root) : advance every active job by one stage
│         (queued -> setup -> render_start -> checks_images -> compilation -> finished/failed
│          -> archived), dispatching to workers via render_request() as machines free up
├── is this Blender instance a worker ? worker_tick() :
│   ├── update_worker_heartbeat(), scan_cancel_requests(), scan_worker_processes()
│   └── if idle : execute_render_request() -- pop a pending request targeting this
│         machine's uuid and launch it as a local subprocess
└── neither role anymore : return None -> Blender deregisters this timer
```
