# Changelog

All notable changes to this addon. Dates are release dates.

## 1.1.5 — not released yet

- **Review on the snapshot page itself.** *✎ Review on this page*, in
  the review box at the top next to the `.xlsx` (or *✎ Review* in the
  bar), puts a ✓ and a ✗ beside each department's pill on every row: ✓
  validates it as your role (only a done one, in violet), ✗ opens a box
  for the retakes -- one per line; a shot's button of a block starts a
  new line `[sh020] `, so one shot after the other --, or withdraws a
  validation when left empty. Each row also gets *all done*, a *general
  retake* and a *description* to edit; a row gone through gets a violet
  line on its left. While reviewing, *Blender file*, *Last render*,
  *Done* and *Validated* are hidden (the Columns menu shows them again). The box asks for the
  author, the role and the date, counts the changes and downloads
  the review as a `.json` that **Import review** reads like the
  spreadsheet: same confirm dialog, same refusals. What you write is
  kept in this browser as you go -- a reload or reopening the file in
  the same browser brings it back -- and *Load a review…* opens a
  downloaded one again to go on with it. The `.xlsx` template is still
  there, for several reviewers or a shared drive.
- **One file at a time** while reviewing: *One file* (in the review
  box, or a click on a row's name) shows a single file as a card in place of the
  tables -- its thumbnail large, a block's shots under it (a click shows
  that one), its Done and Validated, versions, description and notes,
  each department with its ✓ / ✗, and for a block **a retake field per
  shot** (a button per shot opens its own) plus one for all of them,
  written back as `[sh040]` lines. *Previous* / *Next*, or
  ← / →, go through the files the filters keep; Esc goes back to the
  table. Same review, same file: the table and the card show the same
  work. Built on demand from the page itself -- nothing added to the
  HTML's weight.
- The review box sums up the work: files reviewed, validated, retakes,
  withdrawn.
- The review box: the in-page review first, the `.xlsx` aside, smaller.
- **Schedule**: each band shows its Validated over its Done, in violet.
- **Phones**: a compact bar that stays at the top, its filters behind
  *Filters*, hidden while scrolling down and back on the way up; Review
  starts on *One file*.
- A table wider than the screen keeps its horizontal scrollbar at the
  bottom of the screen, not only under its last row.

## 1.1.4 — 2026-10-27

A block rendered whole shows its render, the farm's rows say who compiles
what, snapshot thumbnails without letterbox bands.

- **A block rendered whole shows its render.** A multishot rendered in
  one piece (not split per shot: `renders/sq060/sh030-040/v004-stable_001`)
  had no "Last render" in File details, and no thumbnail: only each
  shot's own render was looked for. Its render now shows (with its video,
  folder and frame lookup), in the snapshot's "Last render" too, and its
  thumbnail stands for the block.
- **Snapshot, "Last render" of a block**: shots sharing a render are one
  line, named as a block ("sh020-030-040-050-060 v004-stable_002"), and
  each shot shows its newest render, its own or the whole block's (a
  whole-block render is said on hover) -- no more one line per shot plus
  a puzzling "all shots" one. File details groups the shots sharing a
  render folder the same way.
- **Snapshot, "Blender file"**: the wip version only when it's newer than
  the last stable.
- **Snapshot: the sequence / prefix bands stand out** (bigger, darker).
- **Snapshot notes**: smaller tags, and the author and date at the
  table's right edge -- they stopped at two thirds of it, where the notes'
  box was capped (the text keeps a reading width).
- **Snapshot: a clearer filter bar** -- three named groups, *Go to*,
  *Filter* and *Show*; the toggles (Open RTK, Open notes, Farm, All
  notes, Closed notes) are chips that light up once on, a filter in use
  is highlighted, and *Clear* shows only while filtering. The counts keep
  their width (the bar no longer shifts as they change), and the
  *Columns* menu is wide enough for a box and its name on one line.
- **Farm: a preview compiling on a worker** is listed under that worker
  only -- it showed under the farm host too, as if the host ran it.
- **Farm: the host's machine as a worker** shows on its worker row what
  the farm host runs there (a setup, a compile, a frame check), under
  "worker idle" -- it read plain idle, while the machine was busy.
- **Snapshot: thumbnails in their own shape.** A thumbnail sat in a fixed
  16:9 box: a panoramic render (600x54) became a thin line between two
  bands of the page's background, black in dark mode. The width stays
  fixed and the height now follows the image (up to 63 px; only too tall
  a render gets room on its sides), centred in its row; on hover, its own
  size, with the same small rounded corners as a shot's preview.

## 1.1.3 — 2026-10-25

**Tracking**

- **A tick shows at once**: a department ticked done or worked, a task
  checked, a note added, edited or deleted, a validation given -- the
  sidebar and the monitoring windows show it right away, and it no
  longer flips back a moment later (a project scan running meanwhile put
  the state from before the click back). Clicking twice quickly no longer
  undoes the first click either.
- **Project monitoring** no longer shows, now and then, only the open
  version's work for its file: a folder's status is the same whatever
  reads it.
- **Validate** (the star) says so when there was nothing to change --
  someone else's click already shown -- rather than "validation given".

**Review import**

- A reversed frame range (`[f40-12]`) stays in the retake's text instead
  of being recorded backwards.
- The project's folders touched by an import are read again in the
  background: Project monitoring shows the new notes and validations
  without a manual refresh.

## 1.1.2 — 2026-10-23

Validation roles: a department finished by the team can be validated by a
supervisor, the production...

**Tracking**

- **"Validated" is now "Done"**: what the team ticks when a department's
  work is finished. Same data, nothing to migrate.
- **Validation roles** (Edit project > *Validation roles*, `sup:1,prod:2`
  by default): a higher role covers the lower ones, the same level is
  equivalent. Set yours in the Preferences (*Validation role*).
- **Validate a done department** for your role from a file's detail (the
  star next to it). It's tied to the stable version you saw: a new stable
  starts unvalidated and shows the last validation ("prod: v012, to
  review again"). Each one writes a note for the record.
- **Notes under a role**: marked violet; an RTK from a role is red, the
  team's own orange -- in Blender and in the snapshot. The *New entry*
  dialog has an *As sup* box (on) to post a team note instead.
- **Project monitoring**: "Done · prod" once validated, and a filter (the
  star) for the files with a done department still to validate.
- **Snapshot**: each department's validation next to it, and a
  *Validated* figure apart from Done (violet tile, column, groups, totals): the
  share of the required departments the top role validated.
- **Review template, rethought.** A first sheet for the Author, Review
  date and *Role* (required as soon as the file holds a retake or a
  validation), how to fill it and the colour legend; then a **Shots** and
  an **Assets** sheet, each with its own departments. **A cell per
  department**: `ok` (or yes, oui, v, ✓...) validates it for the role,
  `no` withdraws that, any other text withdraws it too and makes a retake
  of each line -- `[sh020]` and `[f12-40]` at its start for one shot of a
  block and its frames, `note:` for a remark instead of a retake. A
  *global* column: `ok` validates every department done so far, a text
  is a retake for no department. Each cell is coloured by the
  department's state at the snapshot (white not started, amber WIP,
  green done, violet already validated, red border: an open retake; grey
  "–" not required). The import asks first, naming the role, and refuses
  a validation when a newer stable was made since the snapshot. A
  template exported before still imports.
- The snapshot's notes show their frames.
- **Snapshot: every shot of a block.** Under a multishot's thumbnail, a
  small button per shot (010, 020...), in the block's order, shows that
  shot's thumbnail on hover -- to find one's way in an edit; greyed for a
  shot not rendered yet. The export makes the missing ones like the
  others.

## 1.1.1 — 2026-10-23

Previews compile on a free worker, a crash opening Project monitoring
fixed.

**Fixes**

- **Blender could crash opening Project monitoring** (seen on Windows):
  the project scan, running in the background, is now held still while a
  window opens or closes.

**Render farm**

- **A worker says whether it has ffmpeg**: checked when the machine
  becomes a worker (not needed to render), shown in Worker details -- a
  first step towards compiling previews on another machine than the farm
  host's.
- **Previews compile on a free worker**: a preview goes to an idle worker
  that has ffmpeg rather than the farm host's machine, which keeps its
  slot for the setups, frame checks and compilations. None free: on the
  host, as before. A worker stopped or switched off mid-compile: the
  preview is sent out again.
- **A preview's priority**: asked when it's submitted (*Preview block* /
  *Preview sequence* open a small dialog, the Render dialog's *Preview*
  has the field too), shown in Job details for every job.

## 1.1.0 — 2026-10-22

A new render farm: frames handed out in small chunks instead of every
machine racing over the whole shot -- no more frames written twice or
renders stuck at the end, machines added or taken off at any time. Notes
for several departments, and a round of interface fixes.

**Render farm**

- **Renders are cut into chunks of frames** (5 by default, Edit project
  > *Chunk size*). Each free machine takes the next chunk, one at a time;
  a machine added mid-render takes the chunks still free, and a machine
  stopped or switched off simply leaves its chunk to the others. A frame
  is only ever written whole: two machines never write the same frame
  again.
- **A failing chunk no longer takes the job down**: the machine it failed
  on gets no more of that job, its chunk goes to another. The same frames
  failing on three machines fail the job, saying which frames and on
  which machines.
- **A frame stuck far longer than usual is caught**: the render is
  stopped and its chunk goes to another machine (Edit project > *Stuck
  frame*).
- **Cancel one machine to free it for another job**: it leaves that job
  for the others, and only comes back to it if nothing else needs it. A
  job's Cancel stops every machine on it, even with none on it yet.
- **Render dialog**: two modes, *All machines* and *Single*; the
  pre-render script menu opens on the project's own (Edit project >
  *Pre-render*), "No pre-render script" by default. *Workers per job* is
  gone: the priority orders the jobs.
- **Farm monitoring**: Job details shows the chunks in progress (which
  machine, which frame), the failed ones and why a job stopped; a worker's
  own detail page (its versions, its last render, its chunk); machines
  that stopped answering are shown, greyed, instead of disappearing; a
  button opens the farm's folder.
- **"Who rendered frame X"** stays within the render's range and answers
  with the machine, the frames it rendered around it and its speed.
- **A machine on an older version of the addon gets no render** (it
  would write frames twice): flagged in its detail. Update every machine
  of the farm.
- **The compositor's File Output nodes are numbered again** frame by
  frame.
- The farm host sets up new jobs alongside its own render when machines
  sit idle, instead of waiting for its render to end.

**Notes and tasks**

- **An entry can be for several departments**: an RTK turns each of them
  red. A review spreadsheet's department cell takes several too.
- **New entry: one entry per line for every type** (notes included),
  each line with its own departments, frames and -- in a shot block --
  shot. RTK selected by default, empty lines left out.
- **Departments always in the project's order**, wherever they're listed.
- **A note turned into a todo or an RTK shows its checkbox** -- older
  notes kept none.

**Interface**

- **Edit project in two columns**: it ran past the screen.
- **Clicking Monitoring again brings its window to the front.**
- **The Pipeline log opens in a window of its own**, like Project and
  Farm monitoring: paged to its height, arrow keys for its pages.
- **F5 refreshes a monitoring window.**
- **Shortcuts, in the preferences** (a section folded by default), each
  named for what it does: the monitoring windows' keys, and new ones to
  open the monitoring windows and the log, add an entry, increment, mark
  as stable or render the open file -- off until you switch them on and
  pick their keys.
- **Renders to check: play the render before it**, to compare.
- File menus show each asset's or shot's description as a tooltip.
- Addon settings (Advanced mode, worker on open, FFmpeg path...) survive
  an addon update.
- Monitoring windows: one row less, the pages no longer overflow.

## 1.0.18 — 2026-10-21

Project and Farm monitoring in windows of their own, paged to the
window's height, with keys to turn pages, switch views and go back; the
sidebar's File and Farm panels and the Pipeline menu tidied up.

- **Project monitoring opens in a window of its own**: the Monitoring
  button opens a Blender window holding a single Properties editor -- it
  stays open while you work, resizable, on a second screen if you like.
  Its list is paged by as many rows as the window holds -- resize it and
  the pages follow, the footer (refresh, file count, legend) stays at its
  bottom. Files opened through the
  pipeline keep it open (they open without their own interface layout
  while it is); its filters stay as they were for the session.
- **Farm monitoring too**: its own window, its Jobs list paged the same
  way, refreshed every 2 s while open. Both show their content first,
  Blender's Active Tool hidden, its Options and Workspace pushed out of
  sight below; Project monitoring's list always has at least 6 rows,
  whatever the filters.
- **A monitoring window no longer goes blank when the main window
  switches workspace.**
- **File details, last render: the machine that rendered a frame is no
  longer cut** ("rendered by WOR...02"): the answer has its own line
  under the Frame field (Farm monitoring's job detail too) -- and names
  the machine by its user, "Alice (a1b2c3d4)", not by its id alone (also
  the job detail's machines). The name is recorded with the job and its
  render history when the render ends (`machine_names`), so it's still
  known once the worker is gone or its id has changed; renders made
  before this version only recorded the id.
- **The snapshot opens in the browser once written** (*Open when done*,
  on by default, next to *Thumbnails* in the file browser).
- **"Checked" lists all the file's departments**, ticked as they're
  validated now ("render" too): untick one the render shows isn't right
  and it's unvalidated -- it only offered to validate the ones not
  validated yet.
- **Increment version / Mark as stable: the dialog widens with the
  file's departments**, so their names are never cut off (it was a fixed
  350 px, too narrow past three or four).
- **Ctrl+click on Project monitoring opens the open file's detail** --
  or says it isn't one of the project's tracked files, with a Back button.
- **Farm monitoring, Workers: blank rows to the window's height**, like
  the Jobs list (was always 4 rows), with room under the last one.
- **The Farm panel's header status opens Farm monitoring** on click
  (left-aligned, like the label it was).
- **"All" choices say what they list**: All prefixes, All sequences, All
  states (Farm monitoring), All levels (Pipeline log).
- **File panel: Increment (was "Increment version") / Mark as stable
  side by side, Render / Preview block / Preview sequence too**,
  when the sidebar is wide enough. **Details**, above Open folder, opens
  Project monitoring on the file's detail -- in place of the panel's
  "Finished" departments box. **Edit block structure moves to the
  Pipeline menu** (greyed, a shot file open).
- **Shot list (New shot, Edit block structure): a delete button at the
  end of each row** -- only the last row could be removed, so dropping
  the first meant retyping every row.
- **New entry opens with a line to type in** (it opened empty, "Add text
  line" first).
- **Monitoring pages: arrows and keys** -- "< Page 2 / 5 >" at the
  footer's right end instead of a number field, Ctrl+click to the first /
  last page; Left / Right turn the page too (Ctrl: first / last), Tab
  switches assets / shots (jobs / workers in Farm monitoring), Esc goes
  back from a detail to the list. The addon preferences list these
  shortcuts (and Ctrl+S), editable.
- **Project monitoring sorts by oldest open RTK, or oldest work** (the
  sort icon by the filters), besides by name.
- **Pipeline menu: recent files in a submenu**, 5 of them (was 3, inline).
- **Labels**: no space before a colon ("Farm: Running", "Working on:"),
  "Add end frame", "File is locked by another user".

## 1.0.17 — 2026-10-21

The farm made for workstations that come and go as workers all day:
a render no longer waits forever on a machine that moved on, a machine
that left can join it again, stopping a worker leaves no empty frame,
joining is decided in time, the time left follows the machines on the
render, and who rendered each frame is kept. Then the monitoring popups
and the save guards. Update every machine of the farm: the farm host and
the workers.

### Farm: renders

- **A render no longer stays at "rendering" for good once one of its
  machines has moved on**: a worker keeps the outcome of its last render
  only, so a machine that ended this render, then another job, had
  overwritten it -- the job waited for it forever, even at 100 %, and
  Cancel did nothing. A render is now over as soon as none of its machines
  is on it any more (rendering it, or about to take it up), whatever they
  published; then the frames on disk decide, as before (all there: frame
  check; empty ones: rendered again). Cancel is noted on the job itself.
  A job already stuck moves on by itself within a minute of the farm host
  being updated.
- **A machine that left a render can join it again**: a workstation
  stopped as a worker (or Blender quit) mid-render stayed in the job's
  machines until the end -- shut out of the render it left, and still
  counted under *Workers per job*. Idle again, it now rejoins like any
  other worker, and only the machines on the render count for the limit.
- **Stopping a worker: "After this frame" or "Stop now"**: "Let it
  finish" finished the whole render -- every frame still free, hours on a
  long shot -- before a workstation was given back. Now the render stops
  as soon as the frame it's on is written. "Stop now" (also quitting
  Blender, a machine's Cancel) deletes the empty file of the frame it was
  on: another machine -- one joining -- can render it, instead of it
  waiting for the end of the render.
- **Workers join a render when it's worth it, in time**: rather than
  "more than 10 free frames each", a worker joins while the free frames
  would keep the render's machines busy longer than it takes it to open
  the file and render one -- measured on that render -- and for a frame
  freed by a *Stop now* that every machine is already past.
- **Time left follows the machines rendering**: each worker notes when it
  writes each frame; the time left is the frames left over the pace of
  the machines on the job *now* (each one's last 10 frames) -- a machine
  joining or leaving halfway no longer skews it, nor the frames already
  there after a frames-missing round. The job's detail shows the average
  time per frame and each machine's, the Workers tab each machine's pace,
  the render history the average. Needs the workers updated; until then
  (or before a first frame is timed), the previous estimate.
- **Which machine rendered a frame**: the job's detail and File details'
  last render have a *Frame* field naming the machine that wrote it (and
  its pace), and each machine's frame count -- kept in the render history
  (one letter per frame, about 1.5 KB for a 1500-frame shot), there once
  the job is archived.

### Monitoring, save guards

- **Monitoring popups reopen where you left them -- with OK**: Project
  monitoring sometimes fell back to its list on its own -- opening a file
  already shown (a "Links to" / "Linked by" row) toggled its detail off,
  and the Back button carried the last file clicked; Farm monitoring
  always reopened on its list. Now OK keeps the detail open for next
  time, Cancel goes back to the list, and a click only ever shows what
  it names.
- **Read-Only Origin: "Save" when nobody saved the file since you opened
  it**: overwriting then loses nothing. Saved by someone else meanwhile:
  still only "Save & Increment", and the popup says why.
- **Popups: one Cancel**: the save guards ("You're on a stable file",
  "Read-Only Origin"), the stop-worker and FFmpeg warnings had a Cancel of
  their own on top of the dialog's Cancel and Close -- three buttons doing
  the same. Theirs is gone.

## 1.0.16 — 2026-10-20

The production snapshot's progress charts and schedule, and what came
with them.

### Production snapshot

- **Progress block** at the top, for the whole project (filters aside):
  Done of the shots and of the assets & libraries, the open RTKs, then a
  card per section -- its department tasks by state in one bar
  (validated, reworked, open RTK whatever the state, WIP, not started, in
  the pills' colours), its Done by sequence / prefix and by department,
  and a sequence (or prefix) x department grid, each cell shaded by its
  %. One panel per chart; the bars and the grid side by side when they
  fit.
- **Project schedule** (Project settings > Schedule: start and end
  dates, days off, days of the week worked -- Monday to Friday by
  default): where the project should be on the export day at an even
  pace, in working days; each Done tile says how far ahead or behind it
  is, with its pace (done / expected) in a pill coloured as a progress
  spreadsheet's: 105 % and more ahead, 100 to 105 % on track, 90 to 100 %
  slightly behind, under 90 % behind. A Schedule card puts each section
  on one band of planned progress: the expected progress a line, its
  Done the fill, the gap between them light green ahead, amber or red
  behind.
- **Notes under their row** instead of at the bottom of the page: an
  "n notes" button unfolds them right under the asset/shot, *Notes* in
  the bar at the top unfolds (or folds) them all. Printing prints every
  open note.
- **Foldable sections**: Progress, Assets and Shots fold on a click on
  their title; all open at load, a link into a folded one opens it.
- **Column headers stay on screen** under the filters while the Assets /
  Shots tables scroll by.
- **Red outline on any department with an open RTK**, whatever its state
  -- was only on validated ones.

### Department states

- **Validated at an earlier stable, or worked on before the latest one,
  but not validated at it: WIP**, no longer *Not started* -- in the
  snapshot and in Project monitoring (tooltip: "Validated or worked on
  before it: in progress"). A department reopened, unvalidated from its
  toggle, or worked on and not finished at the stable read as never
  started. New stables record the departments started so far; for older
  ones, the earlier stables and versions are read, only for the
  departments that would otherwise be *Not started*.

### Project monitoring

- **RTK filter** next to the Farm one: only the files with an open RTK.
- An open *todo* tagged with a department no longer turns that
  department's icon red -- only an open RTK does.

### Farm monitoring

- **Workers tab**: a worker rendering shows the job's name, as in the
  Jobs tab (its file, plus the shot of a block's child), and a click
  opens the job's detail -- it showed its render request's full path
  (clipped by Blender, so some rows looked like a name and others like a
  path). The farm host's step in progress, the same (was its job id).

### Project settings

- No maximum on the resolution (was 8192).
- Schedule: start, end, days off and worked days (see Production
  snapshot).

### Pipeline log

- Times read day/month/year (20/10/2026 15:20:11), the copied line too --
  was month-day with no year.

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

### Upgrading

- Update every machine at once (monitor and workers), ideally with the
  farm stopped: an older worker still renders without its preset when it
  loses the lock race, and records no frames for the duplicate check.
- The frame check needs ffmpeg 4.3 or later on the monitor's machine.
- Set Edit project > Workers per job (3, for instance, on a 6-machine
  farm): how many machines one Auto/Placeholder render uses at once,
  joining workers included.
- On the monitor's first tick its housekeeping runs once: finished jobs
  older than 24 h go to the archives, kept logs are trimmed, archived logs
  older than 14 days deleted.
- A shot re-submitted while its pre-update job is still in the farm isn't
  caught as a duplicate (the job ids changed) -- once only.

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
- The always-on farm status timer redrawing the full viewport (not just the
  sidebar) and polling `monitor.lock` through the write-lock path, every
  2s, regardless of whether the farm popup was even open.

## 1.0.6 — 2026-10-10

### Fixed

- Farm setup/render subprocesses failing outright (`ModuleNotFoundError`)
  on a Blender Extensions install, where the addon's module is namespaced
  (same fix as the CSV batch in 1.0.4).
- A render preset's invalid key (missing intermediate path) aborting the
  whole preset instead of just being skipped.

### Added

- Pre-existing links (files migrated into the pipeline from outside it,
  which never went through an import event) are now recorded in a file's
  `.wipmeta` on load and on save, instead of being invisible to "Linked
  by"/library-update checks. A library with no root datablock records only
  its top-level ones.
- Render preset formats (.py and .json) documented in the Farm page,
  including the EEVEE identifier change in Blender 5.0.

## 1.0.5 — 2026-10-08

### Fixed

- Install failing on Blender 4.2 to 5.0 (Python 3.11): a Python 3.12-only
  f-string, handlers and `BlendImportContextItem` that only exist in later
  versions (`exit_pre` 5.1+, `blend_import_post` 4.3+), `UILayout.textbox`
  (5.1+) and newer icons, each now behind a fallback.

## 1.0.4 — 2026-09-13

### Added

- CSV batch: multi-shot rows -- `shot` takes `"030-035-040"` for one block,
  its shots spread evenly between `frame_start` and `frame_end`, or set
  exactly with an optional `timeline` column (`"1001-1021-1051-1076"`).

### Fixed

- CSV batch: the headless subprocess couldn't import the addon on an
  Extensions install (namespaced module).
- The user name could be lost on an addon reload: it's now kept with the
  projects list backup.
- Edit entry crashing when its stored department is no longer one of the
  project's.
- Multishot row list: the last row could be removed, and a clean-scene
  reset during creation invalidated the list.
- The timeline warnings in the shot dialogs showed as a 1-tuple.

## 1.0.3 — 2026-09-11

### Added

- Preferences > FFmpeg path: an explicit ffmpeg binary, for a Blender that
  doesn't see it on its PATH (a sandboxed launch such as Steam's). Without
  it, well-known install folders are tried after the PATH; a path that's
  set but wrong is reported, never silently replaced.

### Changed

- Increment / mark stable and entry dialogs: labelled rows, aligned.
- Long warnings and popup messages wrap to the dialog's width.
- Open folder buttons say which folder they open in their tooltip.

### Fixed

- Shot dialogs opened from Project monitoring's file details (a folder,
  not a .blend) not finding the block's shots.

## 1.0.2 — 2026-09-07

Changes asked by the Blender Extensions review, plus a week of UI work.

### Changed

- The user name is seeded with a locally generated placeholder name, no
  longer read from the OS login; sessions no longer record the hostname,
  IP or OS name.
- No `sys.path` edits in the headless entry scripts, and no custom
  submodule reload in `__init__.py`.
- Operators renamed `m_pipeline.*` (was `pipeline.*`).
- Sidebar: one File panel for assets and shots (was Asset / Shot /
  Tracking), collapsible panels, Farm panel header with the monitor's
  status (not running / running / stale / dead).
- Opening a read-only file no longer shows a popup: the top bar's red
  READ-ONLY label says it, its menu gives the reason on demand.
- "Branch block" is now "Edit block structure", pre-filled from the
  file's own timeline.
- Version metadata files are named after the version only
  (`.pipeline/v004.wipmeta`), shorter paths for long shot blocks.
- FFmpeg documented as the one optional dependency (farm videos only).

### Fixed

- Stored link paths kept an uncollapsed `../`.
- A lock was considered stale after one missed heartbeat (now three).
- A second popup opened from a popup could fail to show (now opened one
  timer tick later).
- Pasting from a clipboard file outside Blender's temp folder.

## 1.0.1 — 2026-09-02

First public release: projects, assets and shots with versioned files
and naming, stable versions and read-only protection, per-department
tracking with notes/todos/RTKs, shot blocks (multishot), link tracking,
and a file-based render farm (monitor + workers) with ffmpeg checks and
videos.
