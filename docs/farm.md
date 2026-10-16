# Rendering (farm)

*[← Documentation index](README.md) · [Version française](farm_fr.md)*

---

Two roles, independent of whether a file is open or not:

- **Monitor**: one per project at a time (`config/.farm/monitor.lock`). Runs the queue — receives render requests, advances each job through its stages, dispatches to available workers.
- **Worker**: any machine with Blender + the addon open. Registers itself, sends a heartbeat, executes the renders assigned to it as a headless Blender subprocess.

A job goes through: `queued → setup → render → checks_images (ffmpeg check) → compilation (ffmpeg video assembly) → finished/failed → archived`. Every stage has its own dedicated failure (`*_failed`), never blocking for the other jobs in the queue. Launching the monitor checks for `ffmpeg` upfront (this machine's PATH, or the explicit path set in Preferences → FFmpeg path, for a Blender launch that doesn't see PATH properly — a sandboxed runtime such as Steam's, for instance) and warns (Cancel / Continue anyway) if it's missing — otherwise that failure would only surface later, silently, per job.

Submission (the "Render" panel, or a per-file button): priority (higher goes first, 10 by default; equal priority: oldest first), render mode, increment (systematic new output folder, or reuse), frame range with relative override (`s+10`, `e-5`...), targeted machines (empty = auto), pre-render script preset.

**Pre-render presets**: any `.py` or `.json` file dropped in `config/presets/` (except `asset_file_preset.py`) shows up in the submission's preset list, and is applied by each worker right before rendering -- on top of the file's own settings, never saved back into it. A `.py` defines `override(scene, job_data)` (`job_data` is the job's JSON, read-only use); a `.json` is a flat map of dot-notation paths from the scene:

```python
def override(scene, job_data):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.render.resolution_percentage = 50
```

```json
{"render.engine": "CYCLES", "cycles.samples": 64, "render.resolution_x": 1280, "render.resolution_y": 720}
```

A preset that can't be applied **fails that machine's render** instead of rendering with the file's own settings (burn-in, full resolution...): a `.py` that raises, a preset name that no longer exists, an unreadable `.json` -- logged as a farm error, the job carries on with its other machines or fails. Only an invalid `.json` key is just skipped (the others still apply). Each worker reads the job without taking its lock: all of a job's machines start at once, and the lock they fought over used to make some of them render without the preset.

The preset is also applied once at setup, in that throwaway session (never saved either), to read what the render will actually produce: the output format (what the frame check and compilation look for) and the fps (what the compilation encodes at) come from the file *plus* its preset. Mind version-specific identifiers when workers run different Blender versions: EEVEE is `BLENDER_EEVEE_NEXT` on 4.2–4.5 but `BLENDER_EEVEE` from 5.0 -- a `.py` preset can pick whichever exists.

**Render modes**:
- `single`: one machine over the whole range.
- `placeholder`: every free machine attacks the same range in parallel, with no explicit splitting — they self-arbitrate via Blender's native `use_placeholder` + `use_overwrite=False` settings (any frame already claimed/rendered is skipped by the others). Fast, but a frame corrupted by a race between two machines remains possible on a slow drive.
- `auto`: like `placeholder`, unless the last placeholder render of this file left corrupted frames (remembered in `.pipeline/render_history.json` next to the file) — in that case, automatically falls back to `single` for this job.

**Workers per job** (Edit project, 0 = no limit): the most machines one `placeholder`/`auto` render gets at once, joining workers included -- the machines left over go to the next jobs. Blender's placeholder isn't atomic on a network share: two machines finishing a frame at the same moment can both take the next one and write it together (a readable frame with corrupted blocks, not caught by the frame check). Fewer machines on the same frames, fewer of those.

**Idle workers join renders in progress first**: before any new job is sent out, a worker that is (or becomes) idle joins a render already running -- highest priority first -- if that render is `placeholder` or `auto` (not `single`, nor an `auto` fallen back to it), the worker is allowed on it (no machine assigned, or in its list) and never failed it, and more than 10 frames nobody has started yet are left *per joining worker* (78 left: up to 7 join; 10 or fewer: none). It gets the same render request, so it only takes the frames still free. A new job only gets the workers left over. While jobs wait for their setup, the farm host's own worker (when it's also the monitor) takes no new render: the setup waits for that machine's render to end, which held the whole queue back for hours.

A multishot block (see [Shot blocks (multishot)](multishot.md)) submits and behaves exactly like any file from this side — the split into one job per shot happens automatically once the file is picked up, not something you do differently at submission.

**Output folders**: a shot renders into `renders/<seq>/<shot>/<version>_<n>/`, an asset or library file into `renders/assets/<prefix>/<asset>/<version>_<n>/` (or `renders/library/...`).

**Thumbnail**: once a render is compiled, the farm writes a thumbnail next to its folders — `renders/<seq>/<shot>/<seq>_<shot>_thumbnail.jpg`, `renders/assets/ch/ch_bob/ch_bob_thumbnail.jpg` (middle frame, 240 px on its longest side by default — "Thumbnails" in Edit project), used by the production snapshot. Made by Blender itself; only a multilayer EXR needs ffmpeg.

**After the render**: once a job is finished (frames checked, video compiled), its render shows up in Project monitoring's "Farm" column (which also shows each file's job while it's queued or rendering) until someone marks it checked (video button to play it, check mark button to mark it), which also archives the job (it leaves the Farm monitoring list) -- see [Tracking & reviews](tracking-and-reviews.md). A finished job (render, block split, preview) leaves the Farm monitoring list on its own 24 h after ending (`"auto_archive_hours"`, 0 = never); a failed one stays until someone archives it.

**Logs**: every farm process writes its output to a file in `config/.farm/queue/requests/` -- `request_<job_id>.log` for a job's setup, frame check, compilation and preview, plus one `request_<job_id>_<machine>.log` per worker render. Deleted when the job ends well, kept (and archived with the job) when something failed: that's the first place to look. A kept log is trimmed once its job is over -- Blender's per-frame progress lines dropped but for the last ones, then only its start and end kept past 256 KB (a failed render's log reached 36 MB) -- and archived logs are deleted after 14 days (`"farm": {"archive_log_days": ...}` in `project_config.json`, 0 = never).

**Re-submitting a shot already in the farm**: a job is identified by file + preset + shot, so a new request for a shot whose previous job is still in flight (queued, waiting for a worker, rendering...) waits until that job ends, then goes out by itself. Farm monitoring shows it as "waiting for this shot's job in progress (stage)"; clicking it opens the job holding it back.

**Retry**: a failed job has a retry button (in the Farm monitoring list and its detail). It restarts from the stage that failed -- same output folder, frames and preset, no new version. A render only renders the missing frames: the empty files the failed render left behind are deleted first -- and if every frame is already on disk (the other machines finished them), the render is skipped altogether: straight to the frame check and compilation, no worker needed. A render retry also steers clear of the machine(s) that failed it: the job is reassigned to the other workers (an "auto" job -- no machine assigned -- gets every other known worker; one with assigned machines keeps the rest of its list), shown as "Assigned to" / "Failed on" in the job detail. If no other worker exists, it goes back to the same machine. A job whose `.blend` no longer exists (replaced by a newer version, moved) can't be retried -- submit the current version -- and fails at once instead of being sent to every worker.

**Recompile**: a finished job has a recompile button (list and detail) that compiles its video again from the frames already on disk -- ffmpeg only, on the monitor's machine, no render and no worker. The render goes back to "to check" once done. Useful after replacing a few frames by hand, or after changing the ffmpeg preset.

**After a crash**: if the Blender running the farm monitor or a worker crashes, its jobs are picked up again on relaunch -- a step still running is waited for, a step cut short is redone, an interrupted render is sent out again (frames already rendered are kept, only the missing ones are rendered). When a machine drops out of a render (its Blender crashed, it stopped responding for 3 minutes, its worker was stopped, or its share was cancelled) while others still render the job, the job just carries on with them. Once no machine renders it anymore, it's judged on the frames actually on disk: every frame there, it carries on to the frame check (a warning in the log if a machine dropped out); frames missing after a real render failure, it fails; the job's own Cancel on every machine, it stops (cancelled); otherwise -- frames left by a machine that stopped early -- the empty files of the frames it abandoned mid-render are deleted (safe then: nobody renders the job anymore) and the job is sent out again for what's left, up to 3 times before failing. A cancel never counts as the machine failing the job.

**Stopping a worker**: "Kill this worker" on a machine that's rendering asks what to do with its render: *Stop the render too* (interrupted now; the job carries on with its other machines, or goes out again for the frames left -- never a failure) or *Let it finish* (no new render is picked up; the worker stops once this one is done and reported). Either way the machine stays eligible for that job if it's started again later. Quitting Blender, or switching to another project, while its worker renders stops the render too (*Stop the render too*): the render used to outlive Blender, taken for lost while it still wrote its frames. Any machine can be stopped from any other one too: the pause button on its row in Farm monitoring's Workers tab asks the same question (when it's rendering) and takes effect on that worker's next tick, about 10 s; the row then reads "stops after this render", then "stopped".

The whole farm coordinates over the shared project drive, no SSH or direct machine-to-machine connection — see [Design choices](design.md#no-ssh-push-pull-coordination-over-the-shared-drive) for the push-pull mechanism and its trade-offs.

---

**See also**: [Interface](interface.md#overview-popups) for the Jobs/Workers dashboard · [Sessions and locking](sessions-and-locking.md) for the heartbeat/expiration pattern workers and the monitor also follow.
