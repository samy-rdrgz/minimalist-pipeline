# Rendering (farm)

*[← Documentation index](README.md) · [Version française](farm_fr.md)*

---

Two roles, independent of whether a file is open or not:

- **Monitor**: one per project at a time (`config/.farm/monitor.lock`). Runs the queue — receives render requests, advances each job through its stages, dispatches to available workers.
- **Worker**: any machine with Blender + the addon open. Registers itself, sends a heartbeat, executes the renders assigned to it as a headless Blender subprocess.

A job goes through: `queued → setup → render → checks_images (ffmpeg check) → compilation (ffmpeg video assembly) → finished/failed → archived`. Every stage has its own dedicated failure (`*_failed`), never blocking for the other jobs in the queue. Launching the monitor checks for `ffmpeg` on this machine's PATH upfront and warns (Cancel / Continue anyway) if it's missing — otherwise that failure would only surface later, silently, per job.

Submission (the "Render" panel, or a per-file button): priority, render mode, increment (systematic new output folder, or reuse), frame range with relative override (`s+10`, `e-5`...), targeted machines (empty = auto), pre-render script preset.

**Render modes**:
- `single`: one machine over the whole range.
- `placeholder`: every free machine attacks the same range in parallel, with no explicit splitting — they self-arbitrate via Blender's native `use_placeholder` + `use_overwrite=False` settings (any frame already claimed/rendered is skipped by the others). Fast, but a frame corrupted by a race between two machines remains possible on a slow drive.
- `auto`: like `placeholder`, unless the last placeholder render of this file left corrupted frames (remembered in `render_history.json` next to the file) — in that case, automatically falls back to `single` for this job.

A multishot block (see [Shot blocks (multishot)](multishot.md)) submits and behaves exactly like any file from this side — the split into one job per shot happens automatically once the file is picked up, not something you do differently at submission.

The whole farm coordinates over the shared project drive, no SSH or direct machine-to-machine connection — see [Design choices](design.md#no-ssh-push-pull-coordination-over-the-shared-drive) for the push-pull mechanism and its trade-offs.

---

**See also**: [Interface](interface.md#overview-popups) for the Jobs/Workers dashboard · [Sessions and locking](sessions-and-locking.md) for the heartbeat/expiration pattern workers and the monitor also follow.
