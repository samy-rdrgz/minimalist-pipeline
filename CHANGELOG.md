# Changelog

All notable changes to this addon. Dates are release dates.

## Unreleased

### Performance — sidebar on a network share

- **The Pipeline sidebar no longer lags on a shared drive.** Each redraw
  of the File panel made a dozen network calls (about a third of a second
  on the studio share) just to locate and re-check the project config.
  Config paths are now built without touching the disk, and the config
  and tracking data are re-checked at most every 2 seconds, whatever the
  redraw rate.
- The farm header no longer checks the disk on every redraw; it reads the
  farm status the addon already refreshes every 10 seconds.

## 1.0.8 — 2026-10-13

### Fixed — render farm on a Windows network share

- **Jobs no longer freeze mid-queue** (e.g. stuck in `setup_start`). On a
  shared drive, Windows refused the monitor's heartbeat write whenever
  another machine was reading `monitor.lock` (`WinError 5`/`32` in the log),
  and that failure skipped the rest of the tick — job progress included.
  Each tick step is now independent, and the heartbeat no longer depends
  on that write: the file's own timestamp is refreshed every tick too, in
  a way other machines' reads can't block, and the farm status reads
  whichever is newer.
- Shared-file writes and deletes retry briefly when Windows reports the file
  as in use, instead of failing on the first attempt.
- A monitor no longer stops silently after a single failed read of its own
  lock file.
- The render dialog's machine picker listed no worker at all ("Could not
  list machines: 'name'" in the log).
- **A job's setup could hang forever** on a production file: the setup
  subprocess's error output went to a buffer nobody read until the process
  ended, so a page of rig/driver warnings on load filled it and blocked
  the process. Every farm process now writes to a log file instead — one
  per job (`config/.farm/queue/requests/request_<job_id>.log`, all stages
  in order), plus one per machine for renders. Logs are deleted when the
  job ends well and kept when something failed, for inspection.
- One unreadable or deleted job file no longer stops the farm from noticing
  that the other jobs' processes have finished.
- **Re-rendering the same file no longer reports it finished right away.**
  The farm recognized the previous render's result as the new one's and
  started the frame check and video compilation on frames still being
  rendered. Each render now carries its own id.
- On the machine that is both farm host and worker, a job's setup now waits
  for the current render to end instead of loading a second scene alongside
  it. Frame checks and compilations still run right away.

### Changed — render farm after a crash

- **A crash no longer leaves jobs to resubmit by hand.** When the Blender
  running the farm or a worker crashes, the jobs it was handling are picked
  up again on relaunch: a step still running is waited for, a step that
  was cut short is redone, and an interrupted render is sent out again —
  frames already rendered are kept, only the missing ones are rendered.
  Previously these jobs were marked "orphaned" (setup, frame check,
  compilation) or stayed stuck for good (preview, render). Works on
  Windows, Linux and macOS.
- A render whose worker stops responding for 3 minutes is sent to another
  machine.

## 1.0.7 — 2026-10-12

*Note: 1.0.5 and 1.0.6 were version-string bumps only — neither was tagged
or shipped as a release, so everything merged since 1.0.4 is bundled into
this entry rather than split across changelog sections nobody saw.*

### Performance — network shares (studio/multi-machine setups)

A project that lives on a shared drive, read concurrently by several
machines, pays a network round-trip for every disk access a local NVMe
drive would answer in microseconds — and `draw()`/`poll()`/enum-items
callbacks all re-run on every redraw, dozens of times a second. This
release targets exactly those call sites:

- **Fixed the main cause of studio-only lag/freezes**: a reader used to
  poll for up to ~1s against a lock file even once it had gone stale (e.g.
  after another machine crashed mid-write) — every machine, every read of
  that file, indefinitely, until a writer happened to pass by and steal it.
  Readers now recognize a stale lock immediately instead of waiting it out.
- The tracking monitor's "Linked by" lookup no longer walks every linked-file
  record in the whole project (including `renders/`, by far the largest
  folder) on every popup redraw — it now reads a small index built once
  when the popup opens.
- The project-wide tracking scan (and the links lookup above) no longer
  descend into `renders/` at all, only `assets/`, `library/`, `shots/`.
- The file-browser dropdowns (asset/sequence/shot/version pickers) and the
  active-shots listing now cache a folder's contents until the folder
  itself actually changes, instead of re-listing it on every redraw.
- Tracking status, shot-archived flags, and the farm worker list are all
  now cached for a second or two, instead of re-reading disk on every one
  of the several times a single redraw can ask for the same thing.
- The farm dashboard's worker/job scans no longer take a write lock just to
  read.
- Work-time totals no longer re-scan every rotated log archive each time a
  session ends — archives don't change once rotated, only the current log
  does.

None of the above is Windows/SMB-specific — it benefits any multi-machine
project, macOS and Linux included.

### Fixed

- The "Render" button (project panel header, top bar menu) could open
  pre-filled with whichever file was last submitted through "Render this
  file"/the file panel's own Render button, instead of showing the
  file list/picker it's meant to. Caused by an operator property Blender
  remembers between uses; it's now reset every time unless a caller
  explicitly passes a file.
- Farm setup/render subprocesses failing outright (`ModuleNotFoundError`)
  on a Blender Extensions install, where the addon's module is namespaced.
- A render preset's invalid key (missing intermediate path) aborting the
  whole preset instead of just being skipped.
- The always-on farm status timer redrawing the full viewport (not just the
  sidebar) and polling `monitor.lock` through the write-lock path, every
  2s, regardless of whether the farm popup was even open.

### Added

- Pre-existing links (files migrated into the pipeline from outside it,
  which never went through an import event) are now recorded in a file's
  `.wipmeta` on load and on save, instead of being invisible to "Linked
  by"/library-update checks.

---

*No changelog entries exist for 1.0.1–1.0.6 — this file starts here. See
`git log` for that history.*
