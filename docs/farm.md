# Rendering (farm)

*[← Documentation index](README.md) · [Version française](farm_fr.md)*

---

Two roles, independent of whether a file is open or not:

- **Monitor**: one per project at a time (`config/.farm/monitor.lock`). Runs the queue — receives render requests, advances each job through its stages, dispatches to available workers.
- **Worker**: any machine with Blender + the addon open. Registers itself, sends a heartbeat, executes the renders assigned to it as a headless Blender subprocess.

A job goes through: `queued → setup → render → checks_images (ffmpeg check) → compilation (ffmpeg video assembly) → finished/failed → archived`. Every stage has its own dedicated failure (`*_failed`), never blocking for the other jobs in the queue. Launching the monitor checks for `ffmpeg` upfront (this machine's PATH, or the explicit path set in Preferences → FFmpeg path, for a Blender launch that doesn't see PATH properly — a sandboxed runtime such as Steam's, for instance) and warns (Cancel / Continue anyway) if it's missing — otherwise that failure would only surface later, silently, per job.

Submission (the "Render" panel, or a per-file button): priority, render mode, increment (systematic new output folder, or reuse), frame range with relative override (`s+10`, `e-5`...), targeted machines (empty = auto), pre-render script preset.

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

A broken preset never blocks the render: an invalid `.json` key is skipped (the others still apply), a `.py` that raises or a preset name that no longer exists falls back to the file's own settings -- each case logged as a farm warning.

The preset is also applied once at setup, in that throwaway session (never saved either), to read what the render will actually produce: the output format (what the frame check and compilation look for) and the fps (what the compilation encodes at) come from the file *plus* its preset. Mind version-specific identifiers when workers run different Blender versions: EEVEE is `BLENDER_EEVEE_NEXT` on 4.2–4.5 but `BLENDER_EEVEE` from 5.0 -- a `.py` preset can pick whichever exists.

**Render modes**:
- `single`: one machine over the whole range.
- `placeholder`: every free machine attacks the same range in parallel, with no explicit splitting — they self-arbitrate via Blender's native `use_placeholder` + `use_overwrite=False` settings (any frame already claimed/rendered is skipped by the others). Fast, but a frame corrupted by a race between two machines remains possible on a slow drive.
- `auto`: like `placeholder`, unless the last placeholder render of this file left corrupted frames (remembered in `.pipeline/render_history.json` next to the file) — in that case, automatically falls back to `single` for this job.

A multishot block (see [Shot blocks (multishot)](multishot.md)) submits and behaves exactly like any file from this side — the split into one job per shot happens automatically once the file is picked up, not something you do differently at submission.

**Output folders**: a shot renders into `renders/<seq>/<shot>/<version>_<n>/`, an asset or library file into `renders/assets/<prefix>/<asset>/<version>_<n>/` (or `renders/library/...`).

**Thumbnail**: once a render is compiled, the farm writes a thumbnail next to its folders — `renders/<seq>/<shot>/<seq>_<shot>_thumbnail.jpg`, `renders/assets/ch/ch_bob/ch_bob_thumbnail.jpg` (middle frame, 240 px on its longest side by default — "Thumbnails" in Edit project), used by the production snapshot. Made by Blender itself; only a multilayer EXR needs ffmpeg.

**After the render**: once a job is finished (frames checked, video compiled), its render shows up in Project monitoring's "To check" column until someone marks it checked (video button to play it, checkbox to mark it), which also archives the job (it leaves the Farm monitoring list) -- see [Tracking & reviews](tracking-and-reviews.md).

**Logs**: every farm process writes its output to a file in `config/.farm/queue/requests/` -- `request_<job_id>.log` for a job's setup, frame check, compilation and preview, plus one `request_<job_id>_<machine>.log` per worker render. Deleted when the job ends well, kept (and archived with the job) when something failed: that's the first place to look.

**Retry**: a failed job has a retry button (in the Farm monitoring list and its detail). It restarts from the stage that failed -- same output folder, frames and preset, no new version. A render only renders the missing frames: the empty files the failed render left behind are deleted first -- and if every frame is already on disk (the other machines finished them), the render is skipped altogether: straight to the frame check and compilation, no worker needed. A render retry also steers clear of the machine(s) that failed it: the job is reassigned to the other workers (an "auto" job -- no machine assigned -- gets every other known worker; one with assigned machines keeps the rest of its list), shown as "Assigned to" / "Failed on" in the job detail. If no other worker exists, it goes back to the same machine.

**Recompile**: a finished job has a recompile button (list and detail) that compiles its video again from the frames already on disk -- ffmpeg only, on the monitor's machine, no render and no worker. The render goes back to "To check" once done. Useful after replacing a few frames by hand, or after changing the ffmpeg preset.

**After a crash**: if the Blender running the farm monitor or a worker crashes, its jobs are picked up again on relaunch -- a step still running is waited for, a step cut short is redone, an interrupted render is sent out again (frames already rendered are kept, only the missing ones are rendered). A render whose worker stops responding for 3 minutes is sent to another machine. When one machine of a multi-machine render fails (its Blender crashed mid-render, say) while the others keep going, the job waits for them, then judges on the frames actually on disk: every frame there, it carries on (logged as a warning); any missing, it fails as before.

The whole farm coordinates over the shared project drive, no SSH or direct machine-to-machine connection — see [Design choices](design.md#no-ssh-push-pull-coordination-over-the-shared-drive) for the push-pull mechanism and its trade-offs.

---

**See also**: [Interface](interface.md#overview-popups) for the Jobs/Workers dashboard · [Sessions and locking](sessions-and-locking.md) for the heartbeat/expiration pattern workers and the monitor also follow.
