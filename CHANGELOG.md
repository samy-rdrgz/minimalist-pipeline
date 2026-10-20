# Changelog

All notable changes to this addon. Dates are release dates.

## 1.0.15 — 2026-10-16

From a real production project's export (6 machines, a week): see
NOTES.md, "What a real project's export showed".

### Farm: renders

- **The render preset is always applied, or the render fails**: some
  workers rendered with the .blend's own settings (burn-in, full
  resolution) -- all of a job's machines read its file at once under a
  lock, the losers skipped the preset with a warning. The job is now read
  without a lock, and a preset that can't be applied (missing, raising,
  unreadable) fails that machine's render instead.
- **Quitting Blender (or switching project) while its worker renders
  stops the render too**: it outlived Blender, was taken for lost, and its
  frames were sent out again while it still wrote them -- frames rendered
  twice.
- **Bad frames are rendered again, in one pass**: the frame check now
  names the frames ffmpeg finds corrupted (it only counted error lines),
  and each worker records the frames it writes -- Blender's placeholder
  isn't atomic on a network share, and two machines can write the same
  frame at once: readable, garbled colour blocks, not seen by ffmpeg. At
  the end of the frame check, both kinds are deleted and rendered again
  together on a single machine, then checked again; a warning names them,
  Farm monitoring's job detail ("Rendered again") and the render history
  list them. The frame check needs ffmpeg 4.3 or later.
- **Workers per job** (Edit project, 0 = no limit): the most machines one
  Auto/Placeholder render gets at once, joining workers included. Fewer
  machines on the same frames, fewer frames taken by two of them at once
  -- each one a frame to render again (above).
- **Priority**: the highest now goes first, as documented -- it was the
  lowest (a priority-50 job waited behind every priority-10 one).
- The farm host's own worker takes no new render while jobs wait for
  their setup: setups waited for its renders, one setup per render of
  hours.
- A job whose `.blend` no longer exists (a newer version replaced it)
  fails at once instead of going to every worker, and can't be retried.
- A block the split can't cut (fewer than two markers bound to a
  `cam_<seq>_<shot>` camera) still renders whole, but no longer silently:
  farm warning, the shots it couldn't find on the job and in its render
  history.
- Job ids are the same on every machine (project-relative path, not the
  machine's own mount): a resubmit of a shot already in flight is caught
  whichever machine sends it. Previews store their label relative.

### Farm: monitor cost, logs, archives

- The monitor reads job and request files without locking them, and no
  longer re-reads archived jobs every tick; idle machines are listed once
  per tick; a render in progress is only locked once a machine is done.
  Gone: the "Could not read job file ... locked", "'NoneType' object is not
  subscriptable" and "'NoneType' object has no attribute 'get'" errors, and
  the Farm popup re-reading every job at each refresh.
- **"No idle machine for job X, will retry." is gone**: it was 99 % of the
  pipeline log (one line per waiting job per tick); a job's wait is now
  logged once.
- Kept farm logs are trimmed once their job is over (Blender's per-frame
  progress lines dropped, then start + end past 256 KB -- one was 36 MB);
  archived logs are deleted after 14 days; a job that ended well leaves
  Farm monitoring on its own 24 h later (failed ones stay).
  `"farm": {"archive_log_days", "auto_archive_hours"}` in
  `project_config.json`, 0 = never.

### Linked libraries

- **One entry per linked file**: the list held one entry per linked
  datablock -- an overridden rig or anim library recorded each of its
  objects, 2 042 entries (370 KB) for 7 files in one shot's `.wipmeta`,
  copied into every new version. Nothing used more than the file. An
  existing `.wipmeta` shrinks on its next open or save; File details
  shows "asset (2)" when two versions of the same asset are linked.

### Paths

- The sessions log stores project-relative paths (it stored each
  machine's own `S:\...`): work time and recent files no longer depend on
  how a machine mounts the project. Older lines still count.

## 1.0.14 — 2026-10-15

### Project monitoring

- **"Farm" column instead of "To check"**: one icon per render, shot by
  shot (a block's sub-shots side by side) -- a render to check (an
  embossed button: plays the video), or the Farm popup's icon for its
  job's stage; shot, version and step (rendering 45/120, compiling...) in
  the tooltip. A check mark button marks the renders to check checked; a
  legend of the icons sits next to the file count.
- Its filter (camera icon) lists the files with a render to check or a
  job in the farm.
- The file's details get an "In the farm" box under "Renders to check":
  each job with its shot, version and step.
- Read from the farm monitor's cache, refreshed in the background when
  the popup opens or on its refresh button: no extra disk access per
  file.
- A job archived but still in `actives/` no longer shows (the cache entry
  showed the stage before "archived").

### Production snapshot

- **Farm status in the "Last render" column**: every render line starts
  with its status pill -- *to check*, then the farm's at export time:
  *queued* (grey, whatever it waits for), its step in blue (*rendering
  45/120*, *compiling*...), *failed* in red -- so the statuses line up
  down the table. A "Farm" filter lists only those rows.
- **"Done" weights per project** (Project settings > Snapshot done): the
  share of a department counted as done while in progress (33 % by
  default), validated then reworked (67 %), validated with an open RTK
  (67 %) -- were fixed thirds. The page's legend states the values used.
- **Wider and denser page** for six departments and more: up to 1600 px,
  table text 13 px, department cells in short (*WIP*, *Reworked*; the full
  label in the tooltip and the legend), and a **Columns** menu to hide the
  thumbnail, Blender file, last render, any department or Done --
  remembered by the browser.

### Sequence previews

- **Render dialog > Preview** (a third choice next to Asset / Shot): tick
  sequences, Submit -- one sequence preview each; a sequence with nothing
  rendered yet is skipped and named in the report. The File panel's
  block/sequence preview buttons are unchanged.

### Interface

- **Sidebar, Project panel**: New asset / New shot side by side, and
  Snapshot / Import review (renamed from "Export prod snapshot" / "Import
  prod review", in the top bar menu too), when the sidebar is wide
  enough. Project monitoring gets the top bar's icon. Batch create from
  CSV leaves the sidebar (top bar menu only).
- **Sidebar, Farm panel**: the Farm monitor button leaves the header and
  comes first in the panel, with the top bar's icon; new "Add this machine
  as worker" / "Stop this worker" button.
- **Top bar menu**: Pipeline log moves under Open project folder; Tracking
  monitor and Farm monitor get an icon, recent files lose theirs; Batch
  create, Pipeline log and Unset active project are greyed (still
  clickable).
- **Render dialog** (no file given): the render list box shows even
  empty, saying so.
- **Project settings**: wider (450 px); Thumbnails and Snapshot done in
  their own box at the bottom; every line starts its values at the same
  place (a third of the width) -- the resolution, frame rate, shot start
  and naming lines were rows, sized by their label's length.

### Code

- One `frame_paths()` for the frame files of a job's range, shared by
  `frames_not_started()` (join a render in progress) and
  `frames_complete()` (render judged on disk) -- they each had their own
  copy, one with `to_absolute()`, one with a plain join.
- `resolve_sequence_sources()` takes a sequence name instead of a file of
  that sequence; `submit_preview()` / `request_sequence_preview()` shared
  by the File panel's buttons and the Render dialog.

## 1.0.13 — 2026-10-15

### Farm — renders

- **A machine dropping out no longer fails a render.** While any machine
  still renders a job, it carries on -- whatever happened to the others
  (crashed, gone, stopped, cancelled). Once none is left, it's judged on
  the frames on disk: all there, on to the frame check; missing after a
  real render failure, failed; missing because a machine stopped early,
  the empty files of the frames it abandoned mid-render are deleted and
  the job is sent out again for what's left (up to 3 times). Before, one
  crashed PC failed a job the others had finished.
- **Idle workers join a render in progress before starting a new job**
  (auto/placeholder renders only, machines allowed on it, and only while
  more than 10 untouched frames are left per joining worker).
- **Cancel no longer misses a render that hadn't started yet**: a machine
  that hadn't picked up its share yet used to render it anyway after the
  cancel. Its share is now withdrawn; a job left with no machine stops.
- Re-rendering without increment reuses the latest `vNNN_xxx` output
  folder, as intended, instead of always `_001`.

### Farm — retry, recompile, stop

- **Recompile** button on finished jobs: compiles the video again from
  the frames on disk -- ffmpeg on the farm host only, no worker. The
  render goes back to "To check".
- **Retry skips the render when every frame is already on disk**,
  straight to the frame check and compilation.
- **A render retry avoids the machine(s) that failed it**: the job is
  reassigned to the other workers ("Assigned to" / "Failed on" in the
  job detail). A cancel never counts as a machine failing.
- **Stopping a worker** while it renders asks: stop the render too, or
  let it finish first. Any machine can be stopped from the Workers tab
  (pause button on its row), not just this one.

### Farm monitoring

- New **Waiting** filter: Running now only lists steps actually in
  progress; queued jobs and jobs between two steps are under Waiting.
- The farm host row no longer lists renders (the workers' part).
- **A re-submitted shot whose previous job is still in the farm** shows
  "waiting for this shot's job in progress (stage)" instead of "waiting
  for monitor" -- it goes out by itself once that job ends. Click it to
  open the job holding it back.
- Project and Farm monitoring show **12 rows per page** instead of 8.

### Popups and warnings

- **Pipeline popups stay open** until a choice or Close/Escape -- they
  used to vanish as soon as the mouse left them (the append warning was
  often never seen). Closing the "external link" warning now records
  the link like "Ignore" does.
- **Red warning when the project is opened with another Blender
  version** (major.minor: 5.2 for a 4.5 project), at startup and on
  project activation, plus a red line in the Project panel. Leave the
  project's Blender version empty to never warn.

### Fixes

- Archiving a re-rendered job failed on Windows (`WinError 183`): its
  previous archive was already there.
- Background processes (farm setup/render, CSV batch) no longer register
  the addon's UI timers.

## 1.0.12 — 2026-10-14

### Production snapshot

- **How far along each asset/shot is**: a "Done" column (bar and %, last
  column), the % of each sequence / asset prefix on its group row, an
  "All" row closing each table (the section's total and each
  department's own %) and two totals at the top -- assets & libraries,
  shots. Each required department counts in thirds: work in progress
  1/3, validated but reworked since or with an open RTK 2/3, validated
  3/3. A validated department with an open RTK is outlined in red.
- **Closed notes are kept in the snapshot**: done todos/RTKs (with no
  reply still pending) used to be left out of the file. They're in it
  now, hidden until "Show closed" is ticked in the filters; counts and
  progress still only look at open ones. A done todo/RTK shows a green
  tick on its type ("✓ RTK") instead of a grey "done" tag that read like
  a department.
- **Saved in the project's `snapshots/` folder by default**, named with
  the time too (`<project>_snapshot_2026-10-14_18-04.html`): several
  exports a day no longer overwrite each other.

### Review import

- **Importing a review also updates the descriptions** the production
  edited in the spreadsheet: a dialog lists every change (was / now) to
  apply all at once, or none. Only a cell the production changed counts
  -- a description changed in the project since the export is never
  reverted -- and an empty cell changes nothing. The template's
  description column is editable for that (it was locked); a template
  exported by an older version has its descriptions ignored, and an
  older version refuses to import a new template.
- Importing a file with no note and no description change says so ("Is
  it the filled-in file sent back?") instead of "0 note(s) imported".

### Monitoring popups

- Project monitoring, Farm monitoring and the Pipeline log take 80 % of
  the Blender window's width (at least 900 px), instead of a fixed 1200.

## 1.0.11 — 2026-10-14

### Fixes — farm

- **A job no longer sits at 100 % after its render ended.** The monitor
  ignored the result of a worker whose heartbeat was a few seconds late
  (frequent on a share); once that worker finished its next render, the
  result was gone for good. Results now count whatever the heartbeat.
- **A job no longer sits at 100 % waiting for a machine that had nothing
  left to render.** With several machines on a render, one could be
  handed its share while it was starting another job: the others rendered
  everything, and the job waited for that other render to end. Once one
  machine has finished, shares not yet picked up are dropped.
- **A worker no longer stays stuck in "render" when its heartbeat fails.**
  The heartbeat, cancel check and finished-render check now run
  independently: one failing (a locked file on the share) no longer skips
  the others every tick.
- **A render or setup whose script crashes is now reported as failed.**
  Blender exited with 0 even after a Python error in its entry script, so
  the render counted as a success.
- **Output format and fps come from the file plus its preset.** The setup
  applies the preset too (in memory, never saved) before reading them: a
  preset changing the format no longer breaks the frame check and the
  compilation.
- `render_history.json` now records the render's duration, the machines
  that rendered it, and which file and output folder were rendered
  (`source_file`, `output_path`, `shot_override`).

### Farm monitoring popup

- **Retry** a failed job (list and detail): it restarts from the stage
  that failed, with the same output folder, frames and preset -- no new
  version. A render keeps the frames already rendered; the empty ones the
  failed render left are deleted first so they get rendered again. Works
  on a failed job already archived too (it comes back to the list).
- **Job detail**: click a job's name for its stage history with
  timestamps, frame range, output folder, format, fps, preset, machines
  and split shots, with buttons to open its JSON file, each of its logs
  (farm host, each worker's render) and the pipeline log filtered on it.
- **Filters and pages**: a search field (file name or shot), a state
  filter (All / Running / Finished / Failed) and "Mine" (the jobs I
  submitted). 8 jobs per page, newest submit first.
- **Archive finished / Archive failed**: every job of that state in one
  click (bottom of the list).
- The popup is 1200 px wide (was 800), like Project monitoring.
- Durations read in hours past an hour ("1h06m", not "66m00s"), and a
  finished job shows its end time ("14/10 18:04").
- The "Farm host" line only shows the step it's running right now, and
  says so when the monitor is stale or dead (with when it was last seen)
  instead of "idle".
- A finished preview compilation (`preview_finished`) is shown as
  finished, with its end time and the archive button.
- No more crash when the farm is stopped while a worker file still says
  it's busy.

### Renders to check

- **Every farm render that finishes now waits for a check.** Project
  monitoring has a "To check" column: a video button per render (plays
  the compiled video with the system's player) and a checkbox to mark them
  checked. An eye icon in the filters lists only those files. A newer
  render of the same shot replaces the older one.
- **Marking a render checked also archives its farm job**, if it's still
  in the Farm monitoring list.
- **Validate departments while marking a render checked.** "Checked"
  (the To check column's checkbox, or the file detail's button) asks which
  of the file's required departments not validated yet to validate along
  with it -- "render" ticked by default. No dialog when they're all
  validated already, or when the file has no stable version yet (needed to
  validate a department).
- **File details**: the renders to check get their own box under the
  thumbnail (date, video, folder and "Checked" each), and the last render
  of each shot, checked or not, is listed next to the departments with
  its video and folder buttons.
- A job is only marked finished once its render is flagged to check: a
  failed write (locked tracking.json on the share) is retried on the next
  ticks instead of losing the flag.
- Stored in the folder's tracking.json (`to_check`, one entry per shot for
  a block).

### Project monitoring

- **Search field**, next to the other filters: file name or description.
- The popup is 1200 px wide (was 800).
- **Thumbnail size is a project setting** ("Thumbnails" in Edit project,
  240 px on the longest side by default). After a change, the next
  snapshot export remakes the existing ones at the new size; the
  snapshot's hover zoom shows them at that size.

### Pipeline log

- **Pipeline log popup** (icon in the Project panel's header, next to the
  project settings; also in the Pipeline menu): the project's log, newest
  first, filterable by level (all, warnings, errors), action, user and
  text, 20 lines per page. Click a line to copy it whole (time, level,
  user, action, message and any extra field). Read in the background:
  Blender never waits on the share.
- **Less noise in the log**: it no longer gets two lines every time a
  Blender (or a farm subprocess) starts or quits -- the per-machine
  backup of the projects list is no longer logged when it works. It was
  most of the log.

### Production snapshot

- **Last render column**, next to the Blender file's versions (now
  labelled "wip v004 · stable v003"): the render's output folder,
  vXXX_YYY (XXX the Blender file version rendered, YYY the render
  increment); one line per shot for a block whose shots differ, "not
  rendered" for a shot never rendered. In red when XXX is older than the
  last stable: the picture lags the validated work. Read from the render
  history, or from the render folder's name for renders made before this
  version.

### Fixes — batch creation

- The CSV separator is detected on the header line only: a description
  with commas could make a `;` file read as `,`.

## 1.0.10 — 2026-10-13

### Production snapshot

- **Export prod snapshot** (Project panel and Pipeline menu): one HTML file
  showing every asset and shot's status per department and all open
  notes, readable offline without Blender or the studio share — made to
  be sent to production by mail. Filters by name, group, department and
  state, open RTKs or notes; each row jumps to its notes. It carries a
  review spreadsheet to download and fill in. The scan and the file
  writing run in the background: Blender never freezes.
- **Import prod review** (Project panel and Pipeline menu): reads the
  filled-in spreadsheet back. One line of text = one note, so several
  retakes on a shot each get their own checkbox. Importing the same file
  twice, or a re-sent one with more notes, never duplicates. A popup
  sums up what was imported and what wasn't (and why). Imported notes are
  marked as coming from a prod review.
- **Thumbnails**, from the middle frame of each asset or shot's latest
  render, any aspect ratio — in the snapshot and in Project monitoring's
  file details. The farm makes one when a render is done; the export
  makes any missing or outdated one from the frames already on disk, in
  the background. Made by Blender itself — only a multilayer EXR needs
  ffmpeg; without it, the export says which thumbnails it couldn't make.
  Can be turned off in the export's options.

### Removed

- The CSV import of notes, replaced by the review spreadsheet. Batch
  creation keeps its CSV.

### Fixes

- **Rendering an asset or library file on the farm works.** The job used
  to fail at setup; its frames now go to `renders/assets/<prefix>/<asset>/`
  (or `renders/library/...`).
- Project monitoring's "Open render folder" button (file details) opened
  a folder that doesn't exist for a shot (`renders/shots/...`).
- The addon version stamped into the project config read "0.0.0" when
  the addon was installed as an extension.
- Batch creation CSV files saved by Excel with a ";" separator (French
  locale) are read correctly.

## 1.0.9 — 2026-10-13

### Performance — sidebar on a network share

- **The Pipeline sidebar no longer lags on a shared drive.** Each redraw
  of the File panel made a dozen network calls (about a third of a second
  on the studio share) just to locate and re-check the project config.
  Config paths are now built without touching the disk, and the config
  and tracking data are re-checked at most every 2 seconds, whatever the
  redraw rate.
- The farm header no longer checks the disk on every redraw; it reads the
  farm status the addon already refreshes every 10 seconds.

### Performance — popups on a network share

- **Project monitoring opens instantly.** It used to re-read every tracking
  file of every asset and shot before showing anything — minutes on the
  studio share, Blender frozen. It now opens on what's already known and
  refreshes in the background ("Scanning project…"), reading only what
  changed since the last time, without ever blocking Blender.
- **The Open file and Render windows no longer lag.** They re-checked every
  shot folder on disk many times per redraw; now nothing touches the disk
  while they redraw.
- The farm monitor and the sidebar's farm status read the disk in the
  background; Blender never waits on them.

### Fixed

- Stray, empty `.pipeline` folders could appear in a prefix folder (e.g.
  `assets/ch/.pipeline`). Version metadata and tracking data (notes,
  description) are now only ever written to the asset/shot's own folder,
  never created anywhere else, and Project monitoring ignores such
  folders — they hid the assets next to them. An existing one can simply be deleted.
- Blender could crash when Project monitoring was closed during its
  background scan, or when a file was opened while the farm monitor was
  refreshing.

### Farm monitor

- **Open-folder button on each job** in the farm monitor, to go straight
  to its render folder.
- **"Add this machine" / "Kill this worker" now shows the right state.** It
  could show a machine as a worker when it wasn't — the state was saved
  inside the .blend file, and set on just from a leftover worker file.
- Render progress counts frames actually written, not frames just started
  by a machine.
- The remaining-time estimate showed the total estimated time instead; and
  a render at 0 frames done broke the whole Jobs view.
- The farm monitor window reads the disk less: nothing at all while it
  redraws, and less on each 2-second refresh (no full re-listing of render
  folders that didn't change).

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
