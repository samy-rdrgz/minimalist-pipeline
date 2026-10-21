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
└── click : m_pipeline.toggle_worked_department(department=d)
      -> wipmeta_add_work(this_file, toggled_set) -- writes straight to
         .wipmeta AND updates the in-memory cache in the same call, so no
         redraw ever re-reads the file (see lib/tracking.py's
         _session_worked_cache)
```

---

## Validated departments (live toggle, no new -stable version)

Button rows in `tracking_panel.py`'s sidebar and the monitoring dashboard's
`m_pipeline.tracking_file_details` popup, wherever validated departments are
shown. Some departments (e.g. "render") aren't tied to editing the file at
all -- forcing a new -stable version just to flip one off/on doesn't fit.

```
├── draw() : get_current_departments(file) for depress=True state (reads
│   TrackingStatusCache -> latest .stablemeta's departments_validated)
└── click : m_pipeline.toggle_validated_department(department=d, filepath=file)
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
├── unregister_refresh_timer() : stop the farm popup's refresh timer first --
│   a file load frees every popup region, and that persistent timer would
│   still tag_redraw() the freed one (crash)
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
├── sync_linked_libraries() : record in this version's .wipmeta the links the
│   file already holds but no import event ever reported (file migrated from
│   outside, library repointed by a script) -- before auto_version below, so
│   a new version inherits a complete linked list
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
├── reason = "stable" if filename tag == "-stable"
│         else "profile" if always_read_only pref
│         else "reopened" if opened_as_read_only == this_file already
│         else "" ?
│   ├── reason set : set_opened_as_read_only(this_file, reason) -- no popup.
│   │         The top bar's red READ-ONLY indicator (see menus/top_bar.py,
│   │         Interface) carries the reason + an Increment button on demand
│   │         instead; these three don't change mid-session, so an
│   │         interrupt-every-open popup was dropped in favor of that
│   │         always-there, non-blocking indicator.
│   │         return
│   └── reason == "" : continue
│
├── acquire_lock(this_file, machine_id)   [kept alive afterwards by heartbeat_30s, see Clocks]
│   ├── failed (another machine's lock is live) :
│   │     set_opened_as_read_only(this_file, "locked")
│   │     informative popup "Opened as Read-Only" (who holds it, from the lock file) : return
│   │     -- kept as an interrupting popup, unlike the three reasons above:
│   │     who's holding the file is live information a static indicator
│   │     can't carry, and there's no Increment offered here since
│   │     incrementing doesn't get you past someone else's lock.
│   └── acquired : continue
│
└── m_pipeline.auto_version (INVOKE_DEFAULT)
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

Note: the library-update proposal above used to be a dedicated
`invoke_confirm`-based operator (`library_update_notice`), kept off the shared
`PipelineAction`/`m_pipeline.action_popup` mechanism because `action_popup`'s
`invoke_popup` didn't reliably auto-close when a choice button was clicked
(see `M_PIPELINE_OT_action_popup._force_close()`). Now that that's fixed, it
was converted to a plain `PipelineAction`, inlined in
`tracking.check_library_update()`. The read-only case went through the same
conversion at first (`_propose_read_only_increment` in `handlers.py`), then
was dropped entirely once the top bar's read-only indicator grew a reason +
Increment button of its own (see above) -- the popup was redundant with it
for the three static reasons, only the lock case still needs one.
`m_pipeline.auto_version` above still uses `invoke_confirm` -- not converted
yet, since its own `execute()` does the real work directly off
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
        │   │            m_pipeline.increment_version INVOKE_DEFAULT)
        │   │          | "Cancel" (releases the lock, no save)
        │   └── no  : popup "Read-Only Origin" (opened deferred one timer
        │         tick too)
        │         -> "Save & Increment" (releases the lock, then -- deferred one
        │            timer tick, same popup-chaining precaution as
        │            m_pipeline.create_project's own INVOKE_DEFAULT call below --
        │            m_pipeline.increment_version INVOKE_DEFAULT)
        │          | "Cancel" (releases the lock, no save)
        └── dismissed without clicking (ESC / click-away) : action_popup.cancel()
              runs the action's on_dismiss, which releases the lock too
```

---

## Save done

`bpy.app.handlers.save_post` → `save_post_handler`

```
├── session_update()
└── file in active project :
    ├── wipmeta_touch() : stamp edited_at/edited_by in this version's .wipmeta
    └── sync_linked_libraries() : same as on load (see "File opened")
```

---

## Increment version / Mark as stable

`m_pipeline.increment_version` — panel button "Increment version" / "Mark as stable", Save-guard's "Save & Increment"/"Increment", or `read_only_notice`'s "Increment outside stable"

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
├── m_pipeline.farm_add_self_worker : launch_worker() -- registers farm_tick via
│   register_farm_loop, refuses if another live (non-stale) worker already owns
│   this machine's worker file
├── m_pipeline.farm_kill_self_worker : kill_worker()
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
├── m_pipeline.farm_launch_monitor :
│   ├── shutil.which("ffmpeg") not found ?
│   │   └── yes : PipelineAction "FFmpeg not found" (opened deferred one
│   │         timer tick, same precaution as its own choices below) ->
│   │         "Cancel" (stop here) |
│   │         "Continue anyway" (re-invokes m_pipeline.farm_launch_monitor,
│   │         skip_ffmpeg_check=True, deferred one timer tick -- same
│   │         popup-chaining precaution as m_pipeline.create_project's own
│   │         INVOKE_DEFAULT call below) -- checks_images/compilation would
│   │         otherwise fail silently per-job, only surfacing in the log
│   └── launch_monitor() -- becomes the monitor for the active project,
│         refuses if monitor.lock is live; if stale, requires a confirm
│         ("stale lock, take over?") before forcing it
└── m_pipeline.farm_kill_monitor : request_monitor_kill() -- writes a kill_*.json request,
    the CURRENT monitor's own next tick sees it, stops itself and clears monitor.lock
    (this is why it never blocks: the requester never touches the lock directly)
```

---

## Farm job: stages and cycles

Every job file in `config/.farm/queue/actives/` carries a `stage_history`;
its last entry is the job's stage. The monitor's `scan_queue()` (every
`farm_tick`, ~10 s) moves each job at most one step, highest `priority`
first, then oldest. The local stages (setup, frame check, compilation,
preview) run as subprocesses on the farm host, one at a time
(`local_slot_busy()`); only the render runs on workers. A `*_start` stage
just waits: `scan_processes()` moves it on once its subprocess exits, or
`check_render_completion()` for `render_start`. `⟲` marks a way back.

Happy path:

```
incomings/job_<id>.json
  -> queued -> setup_start -> setup_finished -> render_start -> render_finished
  -> checks_images_start -> checks_images_finished -> compilation_start
  -> compilation_finished -> finished -> archived      (-> archives/ after 24 h)
```

### Submission and the stage machine

```
├── submit : job_request() (Render dialog) -> incomings/job_<hash>.json, hash of
│   file + preset + shot (a re-render of the same shot reuses the id) ;
│   request_preview_compile() -> same, initial_stage "preview_queued"
│
├── scan_requests() (monitor, every tick)
│   ├── kill_*.json : the monitor stops (request_monitor_kill())
│   └── job_*.json : a job with this id already in actives/, still in flight ?
│       ├── yes : stays in incomings/, retried every tick -- goes out by itself
│       │         once that job ends ("waiting for this shot's job")
│       └── no  : -> actives/, stage_history = [queued] (or its initial_stage)
│
├── queued : local slot free AND this instance's own worker not rendering ?
│   └── yes : run_render_setup() -> setup_start
│         (blender -b <file> --python farm_entry_render_setup.py: output path +
│          increment, resolved_frame_range, fps ; a block: the split)
│         launch raises -> setup_failed
│
├── setup_start : once the setup subprocess exits
│   ├── exit != 0, or no resolved_frame_range written -> setup_failed
│   └── else -> setup_finished
│
├── setup_finished
│   ├── split_into (a multishot block) -> split_finished (the setup already
│   │     submitted one job_request() per shot) -> construct_split_history()
│   │     -> archived
│   ├── no idle machine it may use (assigned_machines ; the farm host's own
│   │     worker is held back while a job is queued) : note_waiting(), stays
│   └── render_dispatch()
│       ├── .blend gone -> render_failed ("source file missing")
│       └── 1 machine if single / auto fallen back to single / refill_single,
│           else up to farm.max_workers_per_job ; a new dispatch_id ;
│           requests/request_<job>_<uuid>.json per machine -> render_start
│
├── render_start : check_render_completion() (see "Render: workers and
│   completion" below)
│   ├── a machine still renders it -> stays (progress: non-empty frames)
│   └── none left -- judged on the frames on disk:
│       ├── every frame there, non-empty -> render_finished
│       ├── a machine failed it -> render_failed (failed_machines kept)
│       ├── every machine cancelled (the job's Cancel) -> render_failed (cancelled)
│       ├── refill_rounds >= MAX_REFILL_ROUNDS (3) -> render_failed
│       └── else : empty files deleted, refill_rounds + 1
│                  -> setup_finished ("frames left after machines stopped")  ⟲
│
├── render_finished : local slot free ? checks_images() -> checks_images_start
│   (ffmpeg -vf showinfo -f null over the sequence) ; no ffmpeg ->
│   checks_images_failed
│
├── checks_images_start : once ffmpeg exits
│   ├── exit != 0 -> checks_images_failed
│   ├── frames corrupted (corrupted_frames()) or written by two machines
│   │   (frames_written_twice()), and a refill round left ?
│   │   └── yes : those frames deleted, refill_single, refill_rounds + 1
│   │             -> setup_finished ("N frame(s) to render again")  ⟲
│   └── else -> checks_images_finished (frames_corrupted recorded ; bad frames
│              past the last round are kept, named in a warning)
│
├── checks_images_finished : local slot free ? compilation() -> compilation_start
│   (ffmpeg -> compiled_output_path) ; no ffmpeg -> compilation_failed
│
├── compilation_start : once ffmpeg exits -> compilation_finished | compilation_failed
│
├── compilation_finished : _flag_to_check() (render flagged "to check" in its
│   tracking.json ; not written -> retried next tick, given up after 30)
│   -> refresh_shot_thumbnail() -> finished -> construct_history("finished")
│   (not for a recompile) -> archived ; .saved records deleted, the log too
│   (kept if frames were corrupted)
│
├── preview_queued : local slot free ? run_preview_compile() -> preview_start
│   (ffmpeg concat) | preview_failed
├── preview_start : once ffmpeg exits -> preview_finished | preview_failed
├── preview_finished | preview_failed -> archived (log deleted if finished)
│
├── setup_failed | render_failed | checks_images_failed | compilation_failed :
│   construct_history("failed") -> archived
│
└── archived : skipped by scan_queue() while its file is unchanged
    ├── ended well : farm_housekeeping() (hourly) moves it to archives/ after
    │   farm.auto_archive_hours (24 h)
    └── failed : stays in actives/ until someone retries or archives it
```

### Render: workers and completion

```
├── join_running_renders() (every tick, before any dispatch) : an idle worker
│   joins a render_start job rather than start a new one if it renders on
│   several machines (not single / refill_single), the worker is allowed on
│   it (assigned_machines), not already in it nor in failed_machines, under
│   max_workers_per_job, with more than JOIN_MIN_FRAMES_LEFT (10) frames
│   nobody started per joining worker -> same request, same dispatch_id,
│   added to used_machines
│
├── worker_tick() (each worker, every tick)
│   ├── stop_<uuid>.json : stop_worker() -- render killed (result "stopped"),
│   │   or left to finish, then the role ends ("stopping")
│   ├── heartbeat ; cancel_<job>_<uuid>.json : render terminated, result
│   │   {cancelled}
│   ├── render subprocess exited : status idle, last_job_result {job_id,
│   │   dispatch_id, success: exit == 0} -- ONE slot, the next render
│   │   overwrites it
│   └── idle : execute_render_request() -- request deleted ; blender -b
│       <file> -o <output> -s <start> -e <end> --python worker_render_entry.py
│       (placeholders on, no overwrite: every machine runs the whole range,
│       skipping any frame file already there -- empty = taken by someone ;
│       render preset strict) -> status "render", current_job_id,
│       current_dispatch_id
│
└── check_render_completion() (monitor) : each used machine, from its worker
    file read directly (_read_worker()):
    ├── last_job_result about this render (its dispatch_id) :
    │   success | failed | cancelled | stopped | lost (crash, see below)
    ├── worker file gone, silent WORKER_GONE_SECONDS (180 s) or "stopped" : lost
    ├── not rendering it, no request of it waiting, result about another
    │   render -- for MOVED_ON_SECONDS (30 s) : moved_on (result overwritten)
    └── else : still running
    then:
    ├── one succeeded, others' requests never picked up : requests deleted
    │   (_drop_pending_request()), they leave used_machines
    ├── any still running : wait
    └── none : judged on disk (render_start above) -- lost, stopped, cancelled
        and moved_on are neutral, only "failed" fails it
```

### Ways back

```
├── refill (render_start -> setup_finished) : machines stopped early, frames
│   missing -- empty files deleted, sent out again ; at most 3 rounds
├── bad frames (checks_images_start -> setup_finished) : corrupted or written
│   twice -- deleted, rendered again on ONE machine (refill_single), then the
│   whole frame check again ; same 3 rounds as the refill
├── Retry button (any *_failed, even from archives/) : retry_job() ->
│   _RETRY_STAGE, refill_rounds reset
│   ├── setup_failed -> queued
│   ├── render_failed -> render_finished if every frame is there, else
│   │   setup_finished (empty frames deleted, steered off failed_machines)
│   ├── checks_images_failed -> render_finished
│   └── compilation_failed -> checks_images_finished
├── Recompile (finished) : recompile_job() -> checks_images_finished
│   ("recompile") -> the compilation only, no render, no history entry
├── Cancel button (render_start) : cancel_pending_renders() -- requests not
│   picked up deleted (none left -> render_failed, cancelled) ; the machines
│   rendering get cancel_<job>_<uuid>.json
└── crash recovery
    ├── monitor relaunched : recover_interrupted_jobs() -- a local *_start
    │   stage (never render_start) whose PID still runs on this machine is
    │   adopted, else resume_interrupted_stage():
    │   setup_start -> setup_finished if it got as far as its result, else
    │   queued ; checks_images_start -> render_finished ; compilation_start
    │   -> checks_images_finished ; preview_start -> preview_queued
    └── worker relaunched : _recover_previous_render() -- render PID still
        alive: adopted (reported "lost" when it ends) ; else last_job_result
        {lost} right away
```

---

## Activate / deactivate project

`m_pipeline.set_active_project`, `.unset_active_project`, `.create_project`, `.find_project`, or the "Switch to this project" popup choice — all funnel through `lib.set_active_project_root(prefs, new_root)`:

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
├── register_status_timer() : starts _status_tick (see Clocks) unconditionally,
│   for as long as the addon is enabled -- unlike _refresh_tick, not gated
│   behind the farm monitor popup being open
├── deferred (0.1s later, once the addon keyconfig exists) : override_shortcut()
│   installs the Ctrl+S -> wm.safe_save keymap override
├── deferred (0.05s later) : active_project_root was restored non-empty AND its
│   folder isn't reachable (Path(root).exists() fails -- NAS disconnected,
│   drive unmapped) ? m_pipeline.unset_active_project() + PipelineAction popup
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
├── unregister_status_timer() : stops _status_tick, always running until here
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

Every 0.25s, only while the farm monitor popup (`m_pipeline.farm_monitor`) is
open -- registered in its `invoke()`, unregistered in `execute()`/`cancel()`
and on file load. Never touches farm state, UI only, and never the disk itself.

```
├── a background read finished ? _apply_farm_snapshot() (status + jobs +
│   frame counts + workers into the monitor cache), then tag_redraw() the
│   3D views' sidebars and the popup regions registered since the last
│   redraw (each forgotten right after: a closed popup's region is freed)
└── none running and >= 2s since the last one started ? start the next
    _read_farm_snapshot() on the reader thread
```

### _status_tick

Every ~10s, for as long as the addon is enabled (`register_status_timer()`,
addon `register()`/`unregister()`) -- unlike `_refresh_tick`, not gated
behind the farm monitor popup. Cheap counterpart: `monitor.lock` only, so
the sidebar's farm panel header (status label, collapsed or not) stays live.

```
├── a background read finished ? status/lock_user/lock_machine/last_tick
│   into the monitor cache (jobs list untouched); tag_redraw() the 3D views'
│   sidebars only if the status changed
└── else : start the monitor.lock read on the reader thread, come back in 0.5s
```

### ProjectScan._tick

Every 0.1s while a Project monitoring scan runs (started by the popup's
`invoke()`, its Refresh button, or `find_linked_by()` finding no index for
the project), then stops itself.

```
├── drain what the reader thread posted (≤10 ms per tick) : found folders,
│   raw tracking data -> TrackingStatusCache, link targets
└── scan done : drop folders gone since the last scan, rebuild the linked-by
    index. No redraw: the popup refreshes on the next mouse move (holding
    its region across ticks would crash Blender once it's closed)
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
│          -- every stage and way back: "Farm job: stages and cycles" above
├── is this Blender instance a worker ? worker_tick() :
│   ├── update_worker_heartbeat(), scan_cancel_requests(), scan_worker_processes()
│   └── if idle : execute_render_request() -- pop a pending request targeting this
│         machine's uuid and launch it as a local subprocess
└── neither role anymore : return None -> Blender deregisters this timer
```
