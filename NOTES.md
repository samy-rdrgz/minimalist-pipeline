# Dev notes

Docstrings and comments in the code stay short and functional (what a
function does, tooltip-length); anything longer than that about rationale,
history, or a rejected alternative lives here instead, one section per
feature. `CODE.md` is the *what's built* reference; this file is the
*why/how it got built this way* for anything that needed more room than a
comment.

---

## Index

By theme; the sections below stay in the order they were written.

- **Render farm**: [Farm 1.1.0: chunks replace placeholders](#farm-110-chunks-replace-placeholders) · [Stuck frame](#stuck-frame) · [Stopping a worker: after this frame, or now](#stopping-a-worker-after-this-frame-or-now) · [Which machine rendered which frame](#which-machine-rendered-which-frame) · [Time left: per machine, from each frame's time](#time-left-per-machine-from-each-frames-time) · [Crash recovery: resume, don't orphan](#crash-recovery-resume-dont-orphan) · [Re-rendering a file: match the render, not the job](#re-rendering-a-file-match-the-render-not-the-job) · [Farm subprocess output: files, never pipes](#farm-subprocess-output-files-never-pipes) · [Farm popup: worker state, open-folder button, refresh cost](#farm-popup-worker-state-open-folder-button-refresh-cost) · [Farm status: two redraw timers, split by cost](#farm-status-two-redraw-timers-split-by-cost) · [One farm snapshot reader, sync or threaded](#one-farm-snapshot-reader-sync-or-threaded) · [FFmpeg detection: PATH lookup isn't enough, and an override can't silently fall back](#ffmpeg-detection-path-lookup-isnt-enough-and-an-override-cant-silently-fall-back) · [What a real project's export showed (6 machines, a week of production)](#what-a-real-projects-export-showed-6-machines-a-week-of-production)
- **Notes, tracking, snapshot**: [Tracking entries](#tracking-entries) · [Entries for several departments](#entries-for-several-departments) · [Validation roles](#validation-roles) · [Entries: two fields only ever guaranteed together, never accessed bare](#entries-two-fields-only-ever-guaranteed-together-never-accessed-bare) · [Edit entry: a note turned task kept no checkbox](#edit-entry-a-note-turned-task-kept-no-checkbox) · [Edit-entry dialog: a stored department can outlive its own enum](#edit-entry-dialog-a-stored-department-can-outlive-its-own-enum) · [Department filter: three different callers, three different "current file"s](#department-filter-three-different-callers-three-different-current-files) · [tracking.json: one path, never created by a write](#trackingjson-one-path-never-created-by-a-write) · [Renders to check: the one before, to compare](#renders-to-check-the-one-before-to-compare) · [Project monitoring's Farm column: the monitor cache, not the project scan](#project-monitorings-farm-column-the-monitor-cache-not-the-project-scan) · [Production snapshot: one HTML file, a spreadsheet inside it](#production-snapshot-one-html-file-a-spreadsheet-inside-it) · [Snapshot width: short state labels, hideable columns](#snapshot-width-short-state-labels-hideable-columns) · [Work time tracking & log rotation](#work-time-tracking--log-rotation)
- **Shot blocks (multishot), batch**: [Multishot blocks](#multishot-blocks) · [Multishot row list: disabling a button isn't a guard](#multishot-row-list-disabling-a-button-isnt-a-guard) · [Multishot row list, take two: a clean-scene reset invalidates it](#multishot-row-list-take-two-a-clean-scene-reset-invalidates-it) · [_draw_timeline_warnings: a trailing comma turned a string into a 1-tuple](#_draw_timeline_warnings-a-trailing-comma-turned-a-string-into-a-1-tuple) · [CSV batch: the subprocess couldn't import itself](#csv-batch-the-subprocess-couldnt-import-itself)
- **Versions, saving, files**: [Read-only reason: from a popup on every open to an on-demand menu](#read-only-reason-from-a-popup-on-every-open-to-an-on-demand-menu) · [Top bar read-only indicator: why it sits before the Blender icon](#top-bar-read-only-indicator-why-it-sits-before-the-blender-icon) · [.wipmeta writes tolerate a missing sidecar; the panel doesn't trust the flag alone](#wipmeta-writes-tolerate-a-missing-sidecar-the-panel-doesnt-trust-the-flag-alone) · [Next version number: never from a cached listing](#next-version-number-never-from-a-cached-listing) · [Recent files: derived from the log, not a stored list](#recent-files-derived-from-the-log-not-a-stored-list) · [resolve_bpy_path() left "../" uncollapsed in every stored link path](#resolve_bpy_path-left--uncollapsed-in-every-stored-link-path) · [Copy/paste isn't always under bpy.app.tempdir](#copypaste-isnt-always-under-bpyapptempdir) · [Project walk: a stray .pipeline/ hid every asset below it; popup regions must not outlive their popup](#project-walk-a-stray-pipeline-hid-every-asset-below-it-popup-regions-must-not-outlive-their-popup)
- **Monitoring windows, popups, panels**: [Monitoring: windows, not popups](#monitoring-windows-not-popups) · [Monitoring crash: a thread during window_new()](#monitoring-crash-a-thread-during-window_new) · [Monitoring windows: to the front](#monitoring-windows-to-the-front) · [Monitoring windows: pages sized on the window](#monitoring-windows-pages-sized-on-the-window) · [Monitoring popups: reopening on the detail, or not](#monitoring-popups-reopening-on-the-detail-or-not) · [File details' monitoring_detail("file") is a folder, not a versioned file](#file-details-monitoring_detailfile-is-a-folder-not-a-versioned-file) · [Popup-chaining: a second modal popup always waits one timer tick](#popup-chaining-a-second-modal-popup-always-waits-one-timer-tick) · [Action popups: dialogs](#action-popups-dialogs) · ["Render" button opening pre-filled: an operator property's own redo memory](#render-button-opening-pre-filled-an-operator-propertys-own-redo-memory) · [Text wrapping in panels](#text-wrapping-in-panels) · [Pipeline log: backup noise, viewer](#pipeline-log-backup-noise-viewer) · [Shortcuts](#shortcuts)
- **Shared drive, network cost**: [Network-share redraw cost: caching disk reads off draw()/poll()/enum callbacks](#network-share-redraw-cost-caching-disk-reads-off-drawpollenum-callbacks) · [Popups on a network share: nothing on disk in draw(), heavy reads off the UI thread](#popups-on-a-network-share-nothing-on-disk-in-draw-heavy-reads-off-the-ui-thread) · [Sidebar redraw: 341 ms of network calls, 0 notes on screen](#sidebar-redraw-341-ms-of-network-calls-0-notes-on-screen) · [A tick shows at once](#a-tick-shows-at-once) · [Windows: replace/delete refused while a reader has the file open](#windows-replacedelete-refused-while-a-reader-has-the-file-open) · [Lock staleness: 3x the heartbeat, not 1x](#lock-staleness-3x-the-heartbeat-not-1x)
- **Addon lifecycle**: [Addon register()/unregister(): four lifecycle gotchas](#addon-registerunregister-four-lifecycle-gotchas) · [Addon register()](#addon-register) · [Addon settings lost on update](#addon-settings-lost-on-update) · [Screenshots in the docs](#screenshots-in-the-docs)

---

## Multishot blocks

The spec is `multishot_spec_v2.md` (§ references below point there).

### Naming (§1.1)

- `format_shot_segment()` / `shots_in_segment()` are exact inverses (build /
  parse), both pure string logic, no `bpy` — deliberately, so the same pair
  works at submission time on a file that may not be open (see "Split", below).
- Segment is always sorted + deduped + zero-padded regardless of the order
  shots were added in the creation UI — the artist's click order was never
  meant to be meaningful.
- Mono-sequence is enforced by the creation UI only offering shots from the
  current sequence — never a code-level check, because the name template has
  exactly one `sq` slot; a cross-sequence block isn't just discouraged, it
  literally can't be named.

### Creation (`operators/shot_ops.py`)

- `window_manager.shots_list_creation` (a `PipelineShotItem` collection) is
  shared state, not owned by `M_PIPELINE_OT_create_shot` — `M_PIPELINE_OT_edit_block_structure`
  reuses it as-is, along with the same add/remove operators and the four
  shared `_draw_*` helper functions. This is why those helpers take the
  operator instance as a plain parameter instead of being methods.
- `default_frame_start` (config, 1001 if unset) replaced a hardcoded 0
  everywhere a shot's start frame needed a default — the first shot added,
  the block's own `end_frame`, and the CSV batch path (`resolve_timeline()`)
  all read the same key, so there's one place to change the studio's
  convention.
- The §3 pedagogical warning shows for 2+ shots only (never for a mono-shot)
  and repeats the actual rule (shared decor/lighting, one person, one lock)
  instead of just flagging a shot count — the "homogeneous" precondition
  isn't checkable by the tool, so the warning is the only real barrier
  against a block being used to over-scope work.

### CSV batch: multi-shot rows

The CSV batch importer (`lib/batch.py`, `operators/batch_ops.py`,
`templates/batch_create_entry.py`) originally only ever built mono-shot
files: `shot` went through a bare `int()` in three places (the operator's
own duplicate/exists check, the folder-name preview, and the headless entry
script's `create_shot_file()` call), so there was no way to produce an
actual multi-shot block from a CSV at all — three separate rows for
"030"/"035"/"040" just made three separate mono-shot files, never one
`sh030-035-040` block.

Fixed by accepting the exact same dash-joined convention the naming layer
already uses (`shots_in_segment()` / `format_shot_segment()` — see
"Naming" above): `shot` can be `"045"` or `"030-035-040"`, parsed with
`shots_in_segment()` everywhere `int(row["shot"])` used to be, and the
folder-name/exists-check path now builds its label through
`format_shot_segment()` too instead of its own separate zero-padding
one-liner — one formatting path for both cases instead of two that could
drift apart.

The one real design question was **per-shot timing**: the interactive
dialog gets an explicit start frame per row, but a flat CSV row only ever
had one `frame_start`/`frame_end`/`frame_duration` for the whole line.
Passing a 2-element `[start, end]` timeline through unchanged for an N-shot
block would hit `build_shot_scene()`'s own defensive clamp (`timeline[i] if
i < len(timeline) else timeline[-1]`) — harmless (no crash), but every shot
past the first would land its marker on the *end* frame instead of getting
its own cut point, silently wrong rather than merely incomplete. Rejected:
a new per-shot column (a second dash-joined list the row author would have
to keep in sync, by hand, with the `shot` column's own count) — real power
for a case (CSV-authored blocks) that's already the coarser, less hands-on
path by choice. Instead `resolve_timeline()` takes a `shot_count` and, for
`shot_count > 1`, spreads shots evenly across `[frame_start, end]`.

First pass got this half right and shipped with a real bug, caught by a
"does it respect frame_end?" question before it went further: it spread
shots at the fixed `DEFAULT_MULTISHOT_STEP` unconditionally, so an
explicit, tight `frame_end` (e.g. 3 shots asked to fit inside 30 frames)
got silently overshot -- the step never looked at what `end` actually was.
Fixed by deriving the step from the resolved span instead of the constant:
`step = max(1, (end - start) // shot_count)`, and only when *nothing*
constrains `end` (no `frame_end`/`frame_duration` given) does `end` itself
default to `start + DEFAULT_MULTISHOT_STEP * shot_count` -- which is also
why the formula still reduces to exactly `DEFAULT_MULTISHOT_STEP` spacing
in that case (the constant now only ever decides the *default span*, never
the step directly), the same spacing `M_PIPELINE_OT_add_multishot_item`'s
own "add row" default already uses in the interactive dialog, so a block
built by hand and one built from a CSV with no frame columns still land on
the same convention. A span too tight to fit `shot_count` shots at all
(hand-authored CSV only) still can't avoid some overshoot with a minimum
1-frame step -- accepted as a degenerate-input edge case, not something
worth a headless script raising over. `shot_count=1` (the default) keeps
every existing call and every existing single-shot CSV row byte-for-byte
unchanged.

`shot` itself has no format beyond "dash-joined, each part `int()`-able" --
`"40"`, `"0040"`, and `"3-10-020"` all parse the same as `[40]`/`[40]`/
`[3, 10, 20]` (`shots_in_segment()` is a bare `int()` per part, Python
doesn't treat a leading zero as octal). No sorting, no zero-padding, no
fixed order required from whoever writes the CSV -- `format_shot_segment()`
normalizes all of that afterward, for the file/folder name only. The order
given in `shot` is kept as the block's own shot order for marker/timing
purposes (first listed gets the earliest start frame), independent of
whatever order the name ends up sorted into.

**`timeline`** (optional column, e.g. `"1001-1021-1051-1076"`) is the escape
hatch for exact per-shot timing: the block's whole timeline spelled out by
hand, same `[start_0, ..., end]` shape `create_shot_file()` already takes,
parsed by `parse_timeline()` and overriding `frame_start`/`frame_end`/
`frame_duration` entirely when given. Considered a duration list instead
(`"20-30-25"` next to a single `frame_start`) — rejected: it still needs
the reader (and `resolve_timeline`) to do the cumulative-sum arithmetic to
get absolute frames, where this column already *is* the answer, one
column, no new interpretation step. The auto-spread path above stays as
the no-typing default; this one is only for a row that actually needs its
own numbers. Named `timeline`, not `frame_range` as first written --
`operators/farm_ops.py`/`farm/dispatch.py` already use `frame_range` for
an unrelated concept (a farm job's own frame override), and grepping one
term for two different things is exactly the kind of mixup worth a rename
to avoid, not just a comment.

### Block size — no upper bound, deliberately

No enforced maximum on how many shots a block can cover. Raised while writing the spec: what stops someone folding an entire sequence into one block "because it's simpler" — the exact monolith the naming convention would dress up as *structured* (`sq040_sh010-...-200_v001.blend` reads clean even at 20 shots) while being the same one-file-does-everything failure mode the addon exists to prevent. Split-at-render makes a huge block technically painless (isolated per-shot failure, per-shot output), which removes the one purely technical brake that might otherwise have discouraged it.

Two levers were on the table, and the wrong one was almost shipped. Friction at creation — hand-picking every shot, no typed range (see "Naming" above) — costs the person building the block a few extra clicks, but that person is rarely who pays for a block being too big. The real cost is concurrency: Blender allows exactly one session per open `.blend`, so a block's size *is* its unit of concurrency — a 12-shot block means anim, lighting, and fx all serialize behind the same lock no matter how the actual work is split. The warning shown at creation (`_draw_block_warning()`, `operators/shot_ops.py`) names that directly — "This locks all N shots together as a single unit" — instead of just surfacing a shot count, because the count alone doesn't explain *why* it matters. It's shown to whoever is choosing the shots, on purpose: the person deciding a block's scope should see its cost, since a lighter or fx artist discovering later that their shot is locked inside someone else's file isn't an edge case — it's the default outcome of an unbounded block with no upfront warning.

No hard cap was added regardless — a warning, not a block, consistent with the addon's own "warning, not blocking" principle. Whether a warning is enough in practice is still an open question, not a closed one.

### Camera/marker scaffolding (§1.4)

- `build_shot_scene()` creates one camera + one marker per shot, all sharing
  a single CAM/SET/ASSETS collection set (a block is one decor/lighting
  setup, never one per shot) — a mono-shot is `shot_numbers=[n]` through the
  exact same loop, not a separate branch.
- Made idempotent (bug fix): it used to `.new()` the CAM/SET/ASSETS
  collections and every camera unconditionally, fine for a genuinely fresh
  scene but not for `M_PIPELINE_OT_edit_block_structure` — unless "Start with
  a new clean scene" is ticked, editing structure runs this against the
  very scene the *previous* enumeration already scaffolded (it's a Save
  As, not a fresh file), so every existing camera got a Blender-renamed
  duplicate (`cam_..._v001.001`) alongside the real one. Now looks each
  camera/collection up by name (marker by its bound camera, not by name)
  before creating one, so re-running it against an already-scaffolded
  scene is a no-op past the diff — only a genuinely new shot number gets
  new datablocks.
- The camera's own trailing version suffix (`_v001`) is a *different axis*
  from the shot file's own version: it lets an artist keep alternate test
  cameras in the same file (`_v002`, `_v003`...), only one bound to a marker
  at a time. `parse_camera_name()` ignores it entirely when recovering the
  shot number — that's the whole point of it existing.
- `derive_shot_subranges()` only ever runs against a genuinely *open* scene —
  it's the read-back half of the pair above, and reading `scene.timeline_markers`
  from any other file's data would be silently wrong, not an error Blender
  would surface.

### Split at render (§1.2) — the actual architecture history

Three iterations happened before landing on the current shape; kept here so
the reasoning doesn't get rediscovered by accident:

1. **First attempt**: split into N `job_request()` calls at *submission*
   time, guessing the shot list from the filename. Rejected — submission
   doesn't always have the file open (cascade selector, batch render list),
   so the guess couldn't be verified, and a wrong guess would silently
   under- or over-render.
2. **Landed on**: submission always writes exactly *one* job, regardless of
   block size. The real split happens in `run_render_setup_entry()`
   (`farm/setup.py`) — the one moment the file is guaranteed genuinely open,
   because the headless setup subprocess just loaded it. `_split_into_shot_jobs()`
   checks the *live* markers there and, only if there's really more than one,
   fans out into ordinary per-shot jobs (`shot_override` set, routed to their
   own `shots/<sequence>/<shot_override>/` output folder via `resolve_job_context()`).
   A job with `shot_override` already set never re-splits (that's the guard
   against infinite recursion — only a bare submission attempts it).
3. **Bug fix, found against a real render**: `compute_output_path()`
   (`farm/setup.py`) built its output folder relative to `project_root`
   instead of `project_root / "shots"` — since `shot_root` is always
   `.../shots/<sq>/<sh>`, that landed every render (mono or split) at
   `renders/shots/<sq>/<sh>/...` instead of `renders/<sq>/<sh>/...`. Every
   reader (`lib/preview.py`'s `resolve_sequence_sources()`/
   `latest_shot_mp4()`, the `/old` archiving in
   `M_PIPELINE_OT_edit_block_structure`, "Open folder") only ever looked at
   the latter, so a genuinely rendered shot silently never showed up in a
   preview compile ("No rendered shot found..." despite real renders on
   disk) — this is exactly the kind of thing "unverified until run for
   real" (see CODE.md's closing note) was flagging. Fixed by making the
   relative base `project_root / "shots"`. Doesn't retroactively move
   anything already rendered under the wrong path — an existing project
   needs `renders/shots/<sq>/` moved up to `renders/<sq>/` by hand once.
4. **Efficiency fix**: a child's `overrided_frame_range` is resolved to
   *absolute* frame numbers right there in `_split_into_shot_jobs()`, using
   the same already-open scene — so the child's own later setup never has to
   reopen the file just to re-derive a range the split already computed. This
   is also why `run_render_setup_entry()` doesn't call `resolve_override_range()`
   twice on the same data (that bug existed briefly: a relative override like
   `"s10"` would have applied twice, once at split time and again at the
   child's own setup, producing `+20` instead of `+10`).

- **Stage machine, not a `kind` field**: a preview-compile job and a render
  job are told apart purely by *stage name* (`preview_queued` vs `queued`),
  not a `data["kind"]` marker. `scan_requests()` reads an `initial_stage` key
  off the incoming request (defaulting to `"queued"`) and consumes it —
  never persisted onto the active job. This was a deliberate simplification
  over an earlier version that carried `"kind": "preview"` through the whole
  job's life: nothing ever actually needed to ask "what kind is this job",
  only "what stage is it at", and the panel already worked that way.
- **Dedup keys** (`_file_key()` in `farm/monitor.py`): `shot_override` is
  folded into the hash *only when non-empty*, so an ordinary job's key is
  byte-identical to what it was before blocks existed — no risk of an
  in-flight job silently losing its dedup match across this change.
- **`only_shots`** (the submission-time checklist) and **`promised`** (the
  file's own name enumeration, read fresh at split time) are deliberately
  two different sets, not one collapsed into the other: `promised` decides
  which markers are real boundaries at all (see divergence, below);
  `only_shots` — always a subset of `promised` — decides which of those the
  artist actually wants rendered *this submission*. Restricting to `promised`
  by construction (the checklist is always built from the name) is also what
  keeps an extra, unpromised marker from ever being rendered by accident.

### Divergence — name vs. markers (§2)

Two ways a block's name and its live markers can disagree, both handled
*only* inside the split (`_split_into_shot_jobs()`), never a separate check:

- **`skipped_shots`** — the name promises a shot, no marker delivers it.
- **`absorbed_shots`** — a marker exists that isn't in the name's own
  enumeration; its frames merge into the *preceding promised* shot's range
  instead of getting a range of their own (this is also just what Blender
  already does natively for a camera cut with no marker of its own — the
  previous camera keeps running).

Both are written onto the split's own parent job (`skipped_shots`/
`absorbed_shots` keys), shown in the farm dashboard for its brief
`split_finished → archived` window, and kept for good in the block's
`.pipeline/render_history.json` (`construct_split_history()`).

**Explicitly rejected**: a submit-time or save-time warning popup for either
case. Two reasons, both the user's call: the win is marginal (saves at most
the time between submitting and checking the farm dashboard) against the
cost of a second mechanism partially duplicating what the split already has
to compute; and a submit-time check would need the file open to read
markers, which isn't always true (see the split's own history, above) — so
it would have had inconsistent availability depending on how the file was
submitted. The split *always* runs with the file open, so it's the only
place that can answer this honestly every time.

### Preview compile (§1.6)

- Always a farm request (`request_preview_compile()` → `run_preview_compile()`),
  never ffmpeg run synchronously in the interactive session — explicit ask,
  so a slow concat never blocks the artist's own Blender.
- Concat always uses ffmpeg's concat **filter** (decode + re-encode every
  source to the project's own resolution/fps from config), never the concat
  demuxer's `-c copy`. This was a direct question raised while building it:
  a block's own per-shot mp4s can come from different render sessions
  (different fps override, different codec preset chosen at submission...)
  and are never assumed to already match — `-c copy` silently produces
  garbage or fails outright on mismatched inputs, the filter path always
  works regardless, at the cost of re-encode time (acceptable: a preview is
  explicitly disposable, not performance-critical).
- **Manual only, never auto-triggered** when a block's split-off renders all
  finish. This was floated (track the split's child job ids, wait for all
  terminal, auto-compile) and explicitly turned down: `multishot_spec_v2.md`
  §7 already walked back a v1 "continuous review" design specifically to
  land on a disposable, manual preview — an auto-trigger would quietly
  reintroduce the same mechanism. It would also risk compiling a preview
  against a partial submission (only some shots checked) or a manually
  overridden frame range mid-flight, showing something that was never meant
  to be a finished pass.
- The two providers (`resolve_block_sources()` / `resolve_sequence_sources()`
  in `lib/preview.py`) are filesystem-only, no `bpy` — same reasoning as the
  naming pair above, works for any file regardless of whether it's open.
  "Most recent per shot" is read from the render increment folder's own name
  (`vNNN_MMM`), never mtime — mtime lies after a copy across machines/NAS.
- **Path: `_preview/` + a dated filename, not one or the other.** Two
  different jobs, layered: the `_preview/` folder marks "disposable" on disk
  (nobody mistakes it for a deliverable), and the `{scope}_{date}.mp4`
  filename does the rest — no collision between re-runs, readable without
  the tool, and a dated file can't lie about freshness the way an
  overwritten one could. That removes the need for any staleness check or
  regeneration policy: there's nothing to compute, the date on the filename
  already answers "is this current" — regenerate on demand, the old one
  just sits there with its old date. `renders/sq040/_preview/sq040_sh030-
  040-045-050_20260830-1430.mp4`; a block and a full-sequence compile share
  the same folder, told apart only by what's in the name.
- **Filtering by render stage (lighting-only, anim-only...) was scoped
  out.** The providers resolve "most recent output per shot" without regard
  to which department produced it — there's no stage tag on a render's
  output today, so a compile can't select "just the lighting pass" even if
  asked to. Wiring that in needs a real decision (does the output path
  carry the stage, or does something read it from a naming convention) and
  was deferred rather than half-built, not silently dropped.

### Branch (§5)

The alternative to flagging a branched-out composition `archived` was moving it to an `/old/` folder instead: more honest on disk (a dead block is visibly dead), but riskier against the farm's ~10s-latency pull model — a guard checking "is a job active on this block" can still lose to a worker that already pulled the request. The flag shipped first for that reason: metadata-only, no move, no race.

**Revisited, `/old` shipped instead.** The flag never reached a dropped shot's *renders* — only the composition had an `archived` key. A shot pulled from a block's enumeration left its old output in `renders/<sq>/<sh>/` with nothing marking it dead, so "Preview sequence" (`resolve_sequence_sources()`, filesystem-only by design) kept splicing a dead cut into the compiled preview. `/old` fixes both at once: `archive_folder()` (`lib/tracking.py`) moves a folder into an `old/` sibling, used on the branched-out composition and, per dropped shot, its render folder — skipped if that shot number is still covered by some other active block/shot in the sequence, via `active_shot_owners()` (see below). `resolve_sequence_sources()` needed no change: it only sees `renders/<sq>/`'s direct children, and an archived shot no longer lives there.

The race above doesn't apply on this path: the move only runs after `create_shot_file()` has already switched the live session to the new file, so the old path is never the one still open. A job already pulled and mid-render against it stays exposed — same as a hand-deleted folder would be, not new risk. Breaking a Blender link still pointing at the moved file is accepted, not a bug: a dead block should fail loudly, not keep resolving as if it were current.

- `create_shot_file()` for the new composition still runs *before* the old
  block gets archived, not after: a creation failure must never leave it
  gone with no successor.
- The `archived` flag write stayed even after the move landed:
  `TrackingStatusCache.get_all()` finds tracking.json via `rglob()` from
  the project root, so a block moved under `old/` is still nested under it
  and would still surface in monitoring without the flag.
- `list_active_blocks()` now also skips `ARCHIVE_DIRNAME` (`old`) by name,
  so the archive folder sitting next to a sequence's real shot folders
  never gets listed as one. The preview providers (`lib/preview.py`) still
  aren't keyed by block identity — not needed anymore, since a dropped
  shot's render folder is just gone.

**Shot-number conflicts, and a rename.** `M_PIPELINE_OT_branch_shot` became
`M_PIPELINE_OT_edit_block_structure` — "branch" read as a one-way archive
action; the operator is really the general "change which shots this file
covers" tool (mono → block, block → mono, or just a different selection),
and the old name gave no hint of that at the button.

- Its dialog used to seed every shot's start frame with the same
  `default_frame_start`, regardless of where that shot actually sits. It
  now reads the real thing off the currently open file's own markers —
  `derive_shot_subranges()` (`lib/presets.py`, already built for the
  farm's split, see "Split at render" above) against the *promised* set
  parsed from the filename — and falls back to `default_frame_start` only
  for a shot whose marker is missing, or when `self.filepath` isn't
  actually the open file (an explicit, non-default caller — the one real
  call site, `file_panel.py`, always passes the open file).
- New check, `active_shot_owners()` (`lib/tracking.py`): `{shot_number:
  owning folder}` across every active file in a sequence. Two other call
  sites reuse it besides the conflict check below — `list_active_blocks()`
  used to be walked by hand for the dropped-shot-renders skip above; now
  that's `active_shot_owners()` too, one less duplicate of the same loop.
- The dialog (create *and* edit) now flags a shot number already claimed
  by another active file. Landed as a warning + a `confirm_overlap`
  checkbox that must be ticked before executing (`_classify_shot_conflicts()`,
  `operators/shot_ops.py`) — consistent with the addon's "warning, not
  blocking" stance everywhere else. One case is hard-blocked instead, no
  checkbox can override it: ending up with a lone shot whose number is
  *already* another active file's own lone shot. Two files each claiming
  a whole shot to themselves, under the same number, has no legitimate
  reading (unlike a block absorbing a number, which might be a deliberate
  re-branch) — and it's the case that would actually corrupt output: both
  would render into the exact same `renders/<sq>/<sh>/` folder.
- A true second confirmation popup (`invoke_confirm` chained off `execute()`)
  was considered and dropped — its exact re-entry behavior when called
  with `operator=self` and no `event` couldn't be verified without a live
  Blender (this environment has none, see CODE.md's own closing note). The
  checkbox gives the same "must explicitly acknowledge" guarantee without
  betting on unverified modal-chaining behavior.

### §6 — MAX_PATH (`.meta` mitigation implemented, `.blend` still deferred)

A block's `.blend`/`.pipeline/*.meta` filenames grow with the number of
shots (every number is in the name). Theoretical worst case, mirroring the
real path construction exactly (`shots/<sq>/<sh>/.pipeline/<stem>.wipmeta.tmp`,
the `.tmp` being `locked_json`'s own atomic-write suffix):

| n_shots | relative path length |
|---|---|
| 2 | 64 |
| 4 | 80 |
| 8 | 112 |
| 12 | 144 |
| 20 | 208 |

Against Windows' 260-char MAX_PATH, the break-even point (relative path +
UNC server prefix) lands around 8-9 shots once the UNC prefix passes ~140
characters (a deep studio NAS path); the dominant 1-2 shot case has a large
margin at any realistic prefix length. Render output paths are unaffected —
they route through the individual shot's own short label (`sh045`), never
the block's full segment.

The designed mitigation — drop the redundant base filename from `.meta`
files (`v004.wipmeta` instead of `sq040_sh030-...-080_v004.wipmeta`, since
the base is already implied by the parent folder) — **is now implemented**
(`_meta_stem()` in `lib/tracking.py`), ahead of the real UNC-path test this
was originally left pending on: it turned out to matter on its own, for
readability of the `.pipeline/` folder, independent of MAX_PATH risk. The
`.blend` filename itself is untouched — every shot number a block covers
still lives in the `.blend` name — so the table above still holds for that
half of the concern.

A live version of this check was added to the creation/branch popup
(`_draw_naming_preview()`, `operators/shot_ops.py`): past 2 shots and 60%
of 260 chars, it shows the worst-case `.stablemeta.tmp` path length as a
progress bar. Built against `get_active_project_root()` — accurate for
*this* machine's own mount, not a guarantee for whichever artist has the
longest UNC prefix, which is exactly the part this doc can't compute.

---

## Tracking entries

Extending the flat note/todo/rtk model in `lib/tracking.py` for review-heavy use: batching several retakes in one pass, telling entries from different sessions/versions apart, and optionally pinning one to a frame.

### Batched review input, still one entry each

A review pass often produces several retakes at once — several toggles, not one. The tempting fix, one entry holding a list of tasks, was rejected: it makes `done` ambiguous (the entry has no single state, only its sub-tasks do), breaks `response`-based threading (reply to the entry, or to a task?), and department filtering falls over the moment two tasks in the same batch target different departments. Storage stays one entry per task, flat, independent — never `1 entry = N tasks`.

The batching stays at the UI layer only: `review_id` (a uuid generated once per batch) is stamped on every entry created together and used purely for **display grouping** — one shared header (author/date) drawn once, the N tasks listed under it — never as a parent/child relationship. Entries sharing a `review_id` are otherwise fully independent: `response`-based threading still works, per-entry filtering still works, and an entry created outside a batch simply has no `review_id` — it isn't grouped with anything just because it's also missing one (see the schema note at `lib/tracking.py`'s review-box builder).

### `frame_start`/`frame_end`, not a timeline marker

A frame-specific retake ("the hand pops on frame 34") needs a frame reference on the entry — two nullable ints, `frame_end` empty meaning a single frame. Not a string to parse (`"24-48"`, a self-inflicted source of bugs) and not a list (over-engineering for a range that's always contiguous). Highlighting reads it reactively — `frame_start <= scene.frame_current <= (frame_end or frame_start)` — and nothing is ever written back into the `.blend` as a timeline marker.

The reasoning is the same one that keeps a block's own markers out of `tracking.json` (see "Divergence" above, mirrored): a retake lives in the JSON, portable and readable without the addon; a marker lives in the file. Mirroring one into the other would hand the addon a second source of truth that drifts on every save/load and needs its own cleanup once the retake is resolved — exactly the hidden state "readable without the tool" rules out elsewhere. Jumping to a tagged frame is a plain operator that sets `scene.frame_current` — reactive, no persistence. (A manual "create/remove an actual marker from this entry" button was floated for later — deliberately not the default.)

### A version field is provenance, not lifecycle

Filtering entries by version needed a `version` field, and the trap was making it mean "resolved at" instead of "created at". A retake outlives the version it was filed against — `tracking.json` is keyed by asset/shot name, not by file, so retakes travel across versions as the file gets incremented. The field records which version was open *when the entry was written*, parsed from `bpy.data.filepath` via the existing naming regex at creation time; no open or non-conforming file (a batch CSV import, background creation) leaves it `null` rather than guessing. A missing version is honest; a guessed one poisons every future filter silently.

### `type` isn't one axis

`type` (`note` / `todo` / `rtk`) quietly encodes two independent questions — actionable? (`note` vs. the other two) and severe? (`rtk`'s alert vs. `todo`'s not) — collapsed into one enum because today they never need to vary independently. Noted here so nothing gets built assuming `type == "rtk"` means "blocking": that's true by accident of the current two-value severity axis, not by what the field actually means, and batched retakes are exactly the kind of feature that tempts writing that shortcut.

### Status is derived, not a dropdown

There's no manual "wip / review / blocked / approved" status field anywhere in `tracking.json`, and that's a decision, not an omission. A dropdown a person has to remember to update drifts from reality within weeks — not from laziness, but because updating a tracker never carries the same urgency as finishing the actual shot; it's the same mechanism that turns a heavyweight production tracker into a system nobody trusts. The fix isn't a better dropdown, it's not having one: status is computed instead, from what the addon already knows without being told — no file yet, a wip version newer than the last `-stable`, a `-stable` with nothing newer, or a linked dependency whose own `-stable` has since moved on (`TrackingStatusCache`, `department_status_tooltip()` — see [Versions: wip and stable](docs/versions.md) for what feeds this). It can't lie, because there's nothing typed into it that could disagree with the files themselves.

The free-text note stays exactly that — words for a human to read, never a field anything computes from. Keeping the two separate is what lets the derived half stay trustworthy: the moment "status" becomes something an entry's text could also assert, there are two sources of truth for the same question, and the whole point of deriving it evaporates.

---

## Text wrapping in panels

`region_char_budget()` / `text_to_lines()` (`lib/core.py`) split into two deliberately separate layers: producing a character budget from the current drawing context, and wrapping text to that budget. Keeping them separate means the context-dependent half (what can change per call site) never leaks into the pure, testable half (splitting a string at N characters).

**Producing the budget.** `context.region.width` gives the panel's pixel width, divided by an average px/char (`7.0`) scaled by `context.preferences.system.ui_scale`. The `ui_scale` multiplication isn't optional: skip it and the wrap looks right on one machine and overflows on any other display's DPI setting — a real risk on an addon whose whole premise is multiple machines sharing a project. The `7.0` is a calibrated average, not a measurement — Blender's UI font isn't monospace, an `i` and a `W` don't take the same width, so per-character precision would need `blf.dimensions()`, exactly the kind of effort the project's own "over-engineering is the main risk" rule argues against. If wrapping is ever visibly too tight or too loose, that single constant is what gets tuned, never the mechanism around it. A `floor` argument keeps a squeezed-flat panel from computing a budget of 2-3 characters and drawing a wall of one-word lines.

The one real gap `context.region.width` has: it's the *panel's* width, not any nested sub-layout's — Blender doesn't expose a sub-layout's resolved width from inside `draw()` (it doesn't exist yet at that point, only after the C-side layout pass runs). `region_char_budget()` accepts an explicit `width_px` for exactly one such case, a popup/dialog's own `invoke_popup(width=...)`/`invoke_props_dialog(width=...)` value — scaled by `POPUP_WIDTH_SCALE` to correct for a popup's content area rendering narrower than its declared width — Blender doesn't expose the popup's actual rendered pixel width back to Python (`context.region` during that `draw()` isn't the popup's own region, and there's no public API that is), so the raw `width=` argument doesn't map 1:1 to the px/char formula above; `POPUP_WIDTH_SCALE = 3.0` is the single place that gap gets corrected, calibrated from an observed popup where text filled roughly 1/3 of the box at scale 1.0 — recalibrate that one constant if popup text still looks off, never the per-call-site formula. A label inside an ordinary panel's own `split()`/nested `column()` isn't covered by this — the caller would need to pass its own fraction of the budget by hand; nothing does that automatically today.

**Wrapping at the budget.** `text_to_lines()` splits on spaces and packs words up to the budget, using `_effective_len()` rather than a raw character count — capital letters are weighted heavier (`cap_weight`), since they render visibly wider and a caps-heavy string (an acronym, a `.upper()`'d label) would otherwise wrap later than it visually should. `max_lines` (typically supplied by `lines_budget()` — more source text earns a few more lines before truncating, capped) truncates with a trailing `...`, budgeted at `max_width - 3` and floored at 1 character — plain string slicing, which can't raise the way a `textwrap`-based truncation could on a pathologically narrow budget.

---

## Work time tracking & log rotation

Total work time per asset/shot (`WorkTimeCache`, `lib/tracking.py`) and size-based log rotation (`lib/logs.py`) landed together — the second exists because the first turned `sessions_log.jsonl` from a diagnostic trail into something a real feature reads back, which changed what "safe to rotate" means for that one file.

### `session_start` was dropped, not left out

Only `session_end` is logged now. `session_start` used to log unconditionally on every file open (`session_update()`, `lib/session.py`), but everything it recorded — who, which file, when — turned out to already be recoverable from the matching `session_end` line alone (`ts` minus `duration_seconds` gives the start time), including the crash case: `scan_sessions()` closes an orphaned session and logs its `session_end` (flagged `(crash)`) the next time anyone's Blender runs the check, so a session without a clean close still ends up with exactly one line, eventually. Two log lines were recording one fact. Cut to one.

### `filepath` is its own field, not parsed out of `message`

`_log_session_end()` used to fold the filepath into the human-readable `message` string only (`f"{filepath} ({duration}s){closing}"`) — fine when nothing read it back. `WorkTimeCache` needs it per line to know which asset/shot a duration belongs to, and regexing it back out of a string built for a human to read, with an optional `(crash)` suffix to strip, is exactly the kind of parsing that breaks the day someone tweaks the message format for readability. It's logged as its own `filepath` key now; `message` still carries the same text for anyone reading the file directly.

### Rotation trigger: file size, not a line count

`log()` checks `log_file.stat().st_size` before every write and rotates past `LOG_ROTATE_MAX_BYTES` (5 MB). A line-count trigger was the first instinct (matches "roll over every N entries" thinking) and was dropped fast: knowing the line count of a growing file means reading the whole thing, on every single log call, to decide whether *this* call is the one that tips it over — paying the exact cost rotation exists to avoid. `stat()` is one syscall regardless of file size.

### Archived, never deleted — same call as the branch flag

A rotated file moves to `config/logs/archives/<stem>_<timestamp>.jsonl` (a path that already existed in `ConfigCache`'s table, unused, before this) — never trimmed, never deleted. Same reasoning as archiving a branched-out multishot block into `old/` instead of deleting it (see "Branch" above): the data stays honestly on disk, readable without the addon, rather than a decision about what's safe to throw away getting made silently by a rotation policy. The cost lands on `WorkTimeCache`, which has to know rotation happened at all.

### Rotating `sessions_log.jsonl` can't quietly shrink a total

The one thing rotation isn't allowed to do to `sessions_log.jsonl` specifically: make "total work time" go down because old lines aged out of the file `WorkTimeCache` happens to be looking at. So `WorkTimeCache.get()` sums the live file *and* every `sessions_log_*.jsonl` under `archives/` (glob, re-read whenever the live file's mtime changes — cache invalidation still keys off one file, since a fresh archive only ever appears in the same `log()` call that also bumps the live file's mtime). `pipeline_log.jsonl` has no reader anywhere in the addon, so its own archived chunks are never touched again — the asymmetry is deliberate, not an oversight: one log became data, the other stayed a diagnostic trail, and they're rotated the same way but read back completely differently.

At realistic scale this barely matters yet: `sessions_log.jsonl` grows slowly enough (only `session_end` lines now, roughly one per file-open) that a single project would take on the order of a decade to produce even one rotation — `pipeline_log.jsonl`, logging far more per session, gets there in months. Scanning "the live file plus a handful of archives" is cheap for exactly as long as that stays true. If it stops being true, the fix isn't a smarter re-scan — it's baking old chunks down to one summed line per folder before they'd otherwise need re-reading, so detail can be dropped without the total losing accuracy. Not built pre-emptively; see `CODE.md`'s tech debt list.

---

## Top bar read-only indicator: why it sits before the Blender icon

`read_only_indicator()` (`menus/top_bar.py`) is `.prepend()`-ed to `TOPBAR_MT_editor_menus`, which lands it before that class's entire native `draw()` — including the Blender icon, not just "File". That wasn't the goal (icon, *then* the warning, *then* File was) but it's what's buildable: Blender draws the icon and the File menu back to back, in the same hardcoded `draw()`, with no hook between them for an addon to land content into. `.append()`/`.prepend()` only ever add before or after that whole native block, never inside it.

Landing exactly between the two was considered — monkey-patch `TOPBAR_MT_editor_menus.draw` itself, redraw the icon, insert the warning, then call through to the rest — and turned down: it means owning a copy of Blender's own menu-drawing logic, which silently drifts the moment a future Blender version changes that native `draw()`. Paying that fragility for one slot of cosmetic ordering wasn't worth it. Before-the-icon was picked over after-everything (the `.append()` alternative, tried first) for the reason the whole feature exists: it has to be the first thing visible, not buried after every native menu and the addon's own "Pipeline" one.

---

## Pipeline log: backup noise, viewer

`save_project_data()`/`load_project_data()` (the per-machine backup of the
projects list, `pipeline_backup.json` in the extension's user folder)
logged every success into the project's shared log: every Blender start
and quit, and every farm subprocess (they register the addon too -- user
"cmd"). On a test project that was 87 % of the lines, each one a lock on
the share. Successes aren't logged anymore; failures still raise.

The viewer (`m_pipeline.pipeline_logs`) reads only the file's last 1 MB
(`read_log_tail()`): it can be several MB on a share before rotation, and
the recent lines are what's looked for -- on a thread, its timer
redrawing the window. Action and user filters list what was read rather
than a fixed list -- any `log()` call adds its own action.

A popup at first; since 1.1.0 a monitoring window like the two others
(kind "log"): a popup keeps every key to itself -- no arrows for its
pages, no Esc --, closes when the mouse leaves it, and needed a registry
of its floating region for a timer to redraw it (`register_popup_region()`
/ `redraw_popups()`, gone with it: a region freed with its popup must
never be redrawn). The window pages to its height (a log line is a bare
label, about 1 widget unit: `_LINE_UNITS`), its filters in memory, F5
reads it again.

**Redraw cost.** A window redraws on every mouse move. The first version
re-filtered every line and rebuilt the action/user enum items on each
redraw; now both are built once per read (`_filtered`, keyed on the read
and the filters, so a page change is a slice; `_items_cache`, keyed on the
read). Messages are drawn as their first line, cut at `_SHORT`: some farm
errors carry 1000+ chars of subprocess output, and Blender re-clips a
button's whole text on each redraw. The full line is the tooltip, and a
click copies it.

## Recent files: derived from the log, not a stored list

The top bar's "Recent" entries (`RecentFilesCache`, `lib/tracking.py`) don't store anything of their own — they're computed from `sessions_log.jsonl`'s own `session_end` lines, the same file `WorkTimeCache` already reads, on the same mtime-cached full-scan pattern.

A plain stored list (e.g. in addon prefs) was the first idea, and the problem with it surfaced immediately: it would need active upkeep (append on open, cap its length, and — the real trap — get cleared or re-scoped on every project switch, or it'd offer to open a file from whatever project was active last). Deriving from the log sidesteps all of that structurally rather than adding code to handle it: `sessions_log.jsonl` already lives inside the *active* project's own `config/logs/`, so reading it can't produce a file from a different project — there's no cross-project list to accidentally leak from, because there's no list.

**Filtered to `get_user()`, not the whole team** — an animator who only ever opens shot files should never see a modeler's asset file in their own "recent" list. This didn't need department metadata or any new field: filtering `session_end` entries to `entry["user"] == get_user().lower()` already produces exactly that, because a person's own session history naturally only contains what they themselves opened. The department-correct result falls out of filtering by identity; no department-aware logic was written.

**Full forward scan, not a backward tail-read** — raised directly: since JSONL is append-only, the most recent entries sit at the end of the file, so reading backward from EOF and stopping once `limit` distinct folders are found is more the shape of "give me the last 3" than a full forward pass is. Turned down anyway: the scan is mtime-cached (not run per redraw), `sessions_log.jsonl` grows slowly enough that it's realistically small for a project's entire lifetime, and it's hard-capped at `LOG_ROTATE_MAX_BYTES` regardless. A backward chunked reader (handling lines split across block boundaries, encoding-safe) is real code for a saving that doesn't show up at this scale. Consistency with `WorkTimeCache`'s own scan shape won over an optimization nothing currently needs.

## Read-only reason: from a popup on every open to an on-demand menu

`post_load_handler` used to fire a `PipelineAction` popup every time a file
opened `-stable`, `always_read_only`, or already-flagged-this-session read-
only — "Continue read-only" / "Increment outside stable". Once the top
bar's red READ-ONLY label existed as a permanent, un-missable indicator for
the whole time the file stays open, the popup started duplicating it: the
same information, shown once as an interruption instead of always available
on demand. Dropped for those three reasons — `set_opened_as_read_only()`
just records why, silently, and `M_PIPELINE_MT_read_only_menu` (a click away
off the label) shows it plus an Increment button whenever the artist
actually wants it. The lock case (another machine has the file open right
now) kept its popup: it's live information, not a static property of the
file, and worth surfacing the moment it's discovered rather than only on
demand.

**Why the indicator is `label() + menu()`, not one clickable menu.** First
attempt: the whole "READ-ONLY" text as a `row.menu(...)` pulldown. Broke
three ways at once — a pulldown button doesn't pick up `row.alert`'s red
styling (only "solid" button types do), a menu-bar pulldown gets its label
squeezed/truncated by the top bar's own width algorithm the way an ordinary
button isn't, and reusing `draw_box_tip()` inside the menu's `draw()` broke
its layout (its `box().column()` wrapper doesn't play well inside a `Menu`
the way it does inside a `Panel`/popover). Second attempt swapped the
pulldown for a `wm.call_menu` operator button (`text="READ-ONLY"`) — fixed
red + truncation (it's a real button, not a pulldown), but `wm.call_menu`
invoked from a button pops the menu up through the same path as a
right-click context menu: a floating, draggable popup that also redraws the
menu's own `bl_label` as a first row inside itself, both wrong for
something meant to look anchored in the header like `top_bar_menu`'s own
"Pipeline" pulldown. Landed on splitting the two: a plain `row.label()`
carries the always-visible red text (labels do respect `alert`, and never
truncate), and a separate icon-only `row.menu()` right after it opens the
actual dropdown — `layout.menu()` used directly in a header row is exactly
the mechanism `top_bar_menu` already relies on for an anchored,
non-draggable pulldown with no duplicate title; it just isn't stylable red,
which no longer matters once the red text lives in the label next to it.
`draw_box_tip()`'s BEGINNER-only gate got reimplemented by hand in the
menu's `draw()`, calling `text_to_lines()` flat on `layout` instead of
through the box-wrapped helper, to dodge the same layout break.

---

## `.wipmeta` writes tolerate a missing sidecar; the panel doesn't trust the flag alone

`wipmeta_add_work()`, `wipmeta_add_link()` and `wipmeta_update_libraries()`
(`lib/tracking.py`) used to raise `PipelineError("Error meta file not
exists.")` when the target `.wipmeta` was missing — which a `-stable` file
always is, by design (only a `.stablemeta`). That read like a defensive
check, but it was reachable through an entirely ordinary flow, not just a
hypothetically-broken flag: `check_library_update()` runs on *any* open
file, `-stable` included, and its "Update libraries" choice calls
`library_updates()`, which repoints/reloads the linked libraries first —
that part succeeds — then calls `wipmeta_update_libraries()` to log it,
which raised. The user saw a confusing `PipelineError` popup after an
action that had actually mostly worked. `wipmeta_add_link()` had the same
shape (linking into an open `-stable` file is legal in Blender — only Save
is guarded, not in-memory edits). Fixed by mirroring `wipmeta_touch()`'s
existing convention one door down in the same file: a missing `.wipmeta`
on a `-stable` file isn't an error condition, there's simply nothing to
track, so all three now no-op silently instead of raising.

Separately, `M_PIPELINE_PT_file_panel.draw()` (`panels/file_panel.py`) used
to gate "Working on" and "Mark as stable" purely on
`get_opened_as_read_only()` — a session-level flag set once at file-load
time (`post_load_handler`) or at addon `register()`
(`refresh_read_only_flag()`), never re-derived on each draw. The write-side
fix above makes a stale flag harmless if clicked, but the button still
shouldn't be there to click. Added a second, independent signal —
`parse_filename(filepath)["tag"] == "stable"`, read straight from the open
file's own name — and hide on either signal being true, not just the
cached one.

**`wipmeta_add_link()` also used to append unconditionally**, found once a
file-details "linked libraries" view (`draw_file_details()`,
`panels/tracking_panel.py`) surfaced a `.wipmeta` with the same batch of
~26 datablocks recorded twice back to back. Blender's import-post handler
firing more than once for what reads as one link action is real —
`clean_append_and_relink()` (`lib/libraries.py`) re-imports the "Clean &
reLink" choice item by item via `bpy.ops.wm.link()` in a loop, each call
its own import event — and since `create_wipmeta()` inherits the previous
version's `linked` list wholesale, one duplicated write compounds into
every later version too, silently. Fixed by deduping on `(file, type,
name)` at write time (existing + incoming, order preserved). Doesn't
un-corrupt a `.wipmeta` already written before the fix — `draw_file_details()`
dedupes the same way at read time so an old file still displays correctly,
but the JSON on disk stays as-is until that asset gets a new version.

---

## Farm status: two redraw timers, split by cost

The N-panel's farm section used to show its status only inside its
expandable body, refreshed opportunistically whenever Blender happened to
redraw that region — in practice, close to never on an idle session, since
nothing was tagging that region for redraw on its own. `_refresh_tick`
(`farm/loop.py`) does call `area.tag_redraw()` on every VIEW_3D area every
~2s, but it was (and still is) only registered while the farm monitor popup
is open — `register_refresh_timer()`/`unregister_refresh_timer()` live in
that popup's own `invoke()`/`execute()`/`cancel()`. So even the "loading"
dots once drawn from `cache['counter']` were only ever animating while that
popup happened to be open too; elsewhere they just sat on whatever value
the cache last held. That coupling was invisible as long as the status text
lived buried in a body most people left collapsed; once it moved into the
panel's `draw_header()` (visible whether collapsed or not, so the
N-panel-declutter pass in progress at the same time wouldn't hide it) the
staleness became obvious.

The fix isn't "just always run `_refresh_tick`": that recomputes the *full*
snapshot, including a jobs-directory scan (`farm_actives`/`farm_incomings`,
mtime-guarded but still real `stat()` calls, potentially over a NAS mount)
that only the farm monitor popup's dashboard actually needs. Running that
continuously in the background for a label nobody's looking at most of the
time isn't worth the cost. So `_compute_snapshot()`'s monitor.lock read got
split out into its own `_read_monitor_status()` — one `locked_json` read,
no jobs scan — reused by both: `_compute_snapshot()` still calls it as its
first step for the full snapshot, and a new `refresh_monitor_status()` /
`_status_tick()` pair calls it alone. `_status_tick`, registered
unconditionally from addon `register()` (mirroring `heartbeat_30s`, not
gated behind any popup), keeps the N-panel header's status live at the
cheap end; `_refresh_tick` stays popup-gated for the expensive end (jobs).
`counter` (the field the old loading-dots animation read) was dropped from
`_monitor_cache` entirely once nothing displayed it anymore — dead state,
not worth carrying just in case.

## FFmpeg detection: PATH lookup isn't enough, and an override can't silently fall back

`shutil.which("ffmpeg")` (the whole check, pre-`resolve_ffmpeg()`) assumes a
missing result means "not installed". Found in practice: Blender launched
through Steam's Linux Runtime (a `pressure-vessel`/bubblewrap container)
reports a `PATH` that still lists `/usr/bin`, yet
`os.path.exists("/usr/bin/ffmpeg")` is `False` from inside that process —
the container's mount namespace gives it its own minimal `/usr/bin`, not the
host's. A real ffmpeg install, invisible to the one process that needs it.
No amount of smarter in-process search routes around that: the sandbox is
doing exactly its job. Launching Blender's real binary directly (bypassing
Steam's launcher, e.g. from a terminal or another launcher) sidesteps the
container entirely and was the actual fix for the reporting user — but
that's a launch-method choice outside the addon's reach, not a bug in it.

What the addon *can* do: `resolve_ffmpeg()` (`lib/core.py`) adds
`prefs.ffmpeg_path`, an optional explicit override, checked before falling
back to `shutil.which()`. Useful beyond the Steam case too — any GUI
launcher or portable install that doesn't inherit a full shell `PATH`. If
the override is set but doesn't point at a real file, the function returns
`None` outright instead of quietly retrying `shutil.which()`: a user who
bothered to set an explicit path did so *because* auto-detect already
failed them once, so silently falling back to the same lookup would hide a
typo/stale path behind an apparent success, or worse, resolve to some
unrelated `ffmpeg` actually on PATH when they specifically meant a
different one.

Every call site that shells out to ffmpeg (`checks_images()`,
`compilation()`, `build_concat_command()`) takes the resolved binary as a
value now, not the bare `"ffmpeg"` string it used to pass to
`subprocess.Popen` — the gate check and the actual invocation have to agree
on which binary was found, or the override would pass the check and then
silently launch a different ffmpeg anyway via the process's own `PATH`
lookup at `exec()` time.

`resolve_ffmpeg()` also falls back to `_COMMON_FFMPEG_PATHS`, a short
per-platform list of well-known install spots, once `shutil.which()` comes
up empty and no override is set — a portable/Homebrew/Chocolatey ffmpeg
that never made it onto PATH, or a desktop launcher that doesn't source the
shell profile that would have set it. Worth having on its own merits (any
GUI-launched app can hit this, nothing sandbox-specific about it), but it's
explicitly *not* the fix for the sandboxed case above: same reasoning
applies — a hardcoded absolute path is still just a path, and a sandbox
that hides `/usr/bin/ffmpeg` from `os.path.exists()` hides it from this
list too. The "FFmpeg not found" popup message (`operators/farm_ops.py`)
spells out the sandboxed-launch possibility and points at the override
preference, since auto-detect failing silently past this point gives a
user no next step otherwise.

**Considered and deliberately not built (yet): auto-download a static
ffmpeg build on demand**, into the extension's own per-user data dir
(`bpy.utils.extension_path_user()`) — would genuinely reach inside most
sandboxes (they typically still expose the extension's own config/data
path, even Flatpak's isolated-home ones), unlike a hardcoded absolute path.
Not attempted: needs a `network` permission added to
`blender_manifest.toml` (the addon has none today — adding one after
publication likely means re-review), a trustworthy per-platform build
source to depend on, and download+checksum+extract+exec-bit machinery —
real scope and a real trust-surface increase (fetching and then running a
third-party binary automatically) for a "manage project files" tool. A
deliberate call to make, not a default to slide into.

## File details' `monitoring_detail("file")` is a folder, not a versioned file

`M_PIPELINE_OT_tracking_monitor`'s file-details view (`draw_file_details()`,
`panels/tracking_panel.py`) reads `monitoring_detail("file")` (was `context.window_manager.file_details_selected`)
— set by clicking a row in the monitor's own list (`_draw_monitor_row()`),
via `op.filepath = str(dir)` where `dir` is `TrackingStatusCache.get_all()`'s
own `asset_dir` (a folder, not a `.blend`). Code written assuming it was a
specific versioned file broke twice: `parse_filename(Path(filepath).name)`
silently returned `None` for a bare folder name like `sh045` (never raised,
so the Preview buttons just never showed, no error — the actual bug behind
an earlier "why is nothing displaying" report), and passing that same
`filepath` straight to `m_pipeline.compile_preview` failed the exact same
way inside that operator, since it also calls `parse_filename()`. Fixed at
both ends: `draw_file_details()` reads the shot/block segment straight off
the folder's own name (`shots_in_segment()`, no `parse_filename()` needed),
and `M_PIPELINE_OT_compile_preview.execute()` now resolves a folder to any
real versioned `.blend` inside it before parsing. Any new code touching
`monitoring_detail("file")` should assume folder, not file.

## `resolve_bpy_path()` left "../" uncollapsed in every stored link path

Found via "Linked by" (same feature as above) coming back empty for an
asset that plenty of shots visibly link. `bpy.path.abspath()` swaps
Blender's `//` prefix for the current file's own directory but does *not*
collapse any `../` that follows — a shot linking a sibling asset folder
(`shots/<sq>/<sh>/` down to `assets/...` always crosses back up through
`../../../`) got exactly that stored verbatim in its `.wipmeta`'s `linked`
list, e.g. `shots/sq030/sh040/../../../assets/ch/ch_ball/ch_ball_v003-
stable.blend`. `to_relative()`'s own `Path.relative_to()` doesn't collapse
`..` either, so the mess round-tripped straight into the sidecar. Fixed at
the source: `resolve_bpy_path()` now runs the result through
`os.path.normpath()` (lexical only, no symlink resolution, unlike
`.resolve()`) before returning. Existing `.wipmeta`/`.stablemeta` written
before this fix still carry the uncollapsed form — `find_linked_by()`
compares `to_absolute(...).parent` (which does resolve) on both sides
specifically so a pre-fix path still matches; anything reading a stored
`linked`/`file` path via a raw string or `Path.relative_to()`/`==` compare
instead would need the same treatment.

## Popup-chaining: a second modal popup always waits one timer tick

Found from the read-only "Save & Increment" flow reliably failing to close
either button: `wm.safe_save`'s `invoke()` returned `{"FINISHED"}` on paper,
but a click on `action_popup`'s own choices sometimes did nothing. Calling
`bpy.ops.m_pipeline.action_popup("INVOKE_DEFAULT")` (or any other
`INVOKE_DEFAULT` operator that opens its own `invoke_props_dialog`/
`invoke_popup`) synchronously from inside another operator's own
`invoke()`/`execute()` forwards *that inner popup's* `RUNNING_MODAL` back as
the outer operator's own return value — entangling the two operators'
modal state so neither one reliably owns the popup afterward. This also
bites a choice callback fired while `action_popup` itself is still in the
middle of closing (e.g. "Save & Increment" wanting to open a fresh
`increment_version` dialog), not just a plain `invoke()`.

Fixed the same way everywhere it comes up: never call the second operator
synchronously — defer it one tick with `bpy.app.timers.register(lambda:
bpy.ops.m_pipeline.xxx("INVOKE_DEFAULT"), first_interval=0.05)` instead. Every
site chaining into a second modal popup follows this: `M_PIPELINE_OT_create_project`
(into `edit_project`), `wm.safe_save`'s `_increment_and_release`/`_open_popup`
(into `increment_version`/`action_popup`), `M_PIPELINE_OT_farm_launch_monitor`'s
missing-ffmpeg and stale-lock branches (into `action_popup`/`farm_launch_monitor`
itself), and `wm.safe_save`'s own `invoke()` for a never-saved file (into
`wm.save_mainfile` itself, to reach its file-browser prompt -- see next
paragraph). Any new operator that needs to open a modal popup from inside
another one's lifecycle should use the same 0.05s-deferred-timer shape.

**A never-saved file (`bpy.data.filepath == ""`) has no read-only/lock/
stable identity to gate on.** `file_in_active_project("")` is always
`False`, which used to route straight into `_save_and_release()` ->
`bpy.ops.wm.save_mainfile("EXEC_DEFAULT")` — a plain EXEC save needs an
existing filepath, so Ctrl+S on a brand-new scene raised `RuntimeError:
Unable to save an unsaved file with an empty or unset "filepath" property`
instead of prompting for one, on every single first save. Fixed with an
early check in `wm.safe_save.invoke()`: no filepath means defer straight
to `wm.save_mainfile("INVOKE_DEFAULT")` (Blender's own Save As browser),
same as an unoverridden Ctrl+S would.

## Addon `register()`/`unregister()`: four lifecycle gotchas

**`bpy.data` is a `_RestrictData` stub for the duration of `register()`
itself** — any call in there that touches real data (`bpy.data.filepath`,
etc.) must be deferred one tick via `bpy.app.timers.register(fn,
first_interval=0.0)`, never called synchronously. Bit twice: once for
`refresh_read_only_flag()` (see next paragraph), and once for
`refresh_monitor_cache()` — called right after `load_project_data()`
because that function bypasses `set_active_project_root()` and leaves the
monitor cache blank, but calling it synchronously crashed `register()`
outright (`AttributeError` on `bpy.data.filepath`, deep inside
`get_active_project_root()`) on any install with an already-active
project. Both are now deferred the same way. Any new register()-time call
into project/file-aware code needs the same treatment.

**Hot-reload leaves the read-only flag stale.** The in-memory read-only flag
(`session.py`) is only ever set by `post_load_handler`, which fires on an
actual file *open* — a script/addon reload (VS Code dev-extension's enable
flow, a manual reload) doesn't re-fire it even though a `-stable` file
stays open throughout, so the top bar's READ-ONLY indicator and the guards
behind it would silently drop on every reload.

**Onboarding is marked "seen" before it's shown, not after.**
`invoke_popup()` gives no feedback on whether it actually rendered (behind
another window, racing another startup popup...), so `_deferred_onboarding()`
sets `onboarding_seen = True` right before calling it rather than from the
popup operator itself — "seen" really means "tried once at startup"; the
empty-state project panel and the header's Help icon stay reachable
regardless, as the permanent fallback for a missed attempt. Also why it
fires last of the deferred timers (0.5s, after `_deferred_project_check`'s
0.05s and `_deferred_auto_worker`'s 0.1s) — Blender only really wants one
`invoke_popup` fighting for the window at a time.

**`unregister()`'s farm-role cleanup must run before `Scene.is_worker` is
unregistered, not after.** Found via a headless fixture-building script
that hit `'Scene' object has no attribute 'is_worker'` on every single
exit. `is_blender_worker()`/`kill_worker()` (called from `unregister()` to
release this machine's worker role) both read/write
`bpy.context.scene.is_worker` — a property the same `unregister()` was
already removing via `_unregister_props(bpy.types.Scene, _SCENE_PROPS)`
*before* reaching that farm cleanup block. The `except Exception: print(e)`
around it swallowed the error, so it never crashed anything visibly, but a
Blender instance that really was the active worker would silently fail to
release that role on quit -- caught only later by the 15s heartbeat
staleness window, not immediately. Fixed by moving the farm cleanup block
above both `_unregister_props()` calls. Any new unregister()-time code
touching a registered WindowManager/Scene property needs to run before
that property's own unregistration, not after.

**No manual `sys.path` edit in the headless entry scripts.**
`templates/worker_render_entry.py`, `farm_entry_render_setup.py`, and
`batch_create_entry.py` each run in a fresh, separate Blender subprocess
(`bpy.app.binary_path` launched via `subprocess.Popen`, not the process
that dispatched them) and need to import `minimalist_pipeline` to reach
shared code. They used to `sys.path.insert(0, ...)` the repo's parent
directory before `addon_utils.enable("minimalist_pipeline", ...)` --
flagged by a Blender Extensions Platform review (moderation guidelines:
manually constructing `sys.path` entries to import into the global
namespace is disallowed; sub-modules/the addon system must do it instead).
Removed outright: `addon_utils.enable()` alone is sufficient, since
Blender's own extension loader already puts an installed extension's
directory on `sys.path` as part of loading the user's preferences --
`enable()` couldn't otherwise import the module either. Not yet re-verified
against a live Blender subprocess (this dev environment can't run one) --
worth an explicit smoke test (one farm render, one batch CSV row) before
relying on it.

**User identity no longer reads the OS login.** Used to seed `prefs.user_name`
via `getpass.getuser()` (`_seed_user_name()`, first register) with the same
value read back as `get_user()`'s fallback (`lib/session.py`) -- dropped
after the same review flagged reading OS-level identity (see the
`sys.path` note above for the other flagged point). Replaced by
`lib.random_display_name()` (`lib/core.py`, next to
`get_machine_id()`): two small word lists baked into the addon's own source
(an adjective/color list and an animal list, ~2350 combinations), combined
with `random.choice()` -- no OS or account info involved, same spirit as
`machine_id`'s locally-generated UUID. `_seed_user_name()` writes one into
`prefs.user_name` once, on first register, so the Preferences panel never
shows nothing configured, several unconfigured teammates don't all collide
under the same generic string (`"unknown"`, or a shared-machine OS login),
and the field stays freely editable by hand at any time. `get_user()`'s
fallback is now a plain `"unknown"`, kept only for the case prefs aren't
reachable at all -- effectively defensive-only, since `_seed_user_name()`
guarantees the pref is set otherwise.

`prefs.user_name` is also drawn directly in `M_PIPELINE_OT_onboarding_popup`
(`lib/operators.py`), not just in Preferences -- the one interactive field
in an otherwise read-only, informational popup. Works because the popup is
opened via `invoke_popup()`, not `invoke_props_dialog()`: `layout.prop()`
there is bound straight to the real `AddonPreferences` RNA, so every
keystroke writes `prefs.user_name` immediately, no OK button/`execute()`
needed to "apply" it -- same as editing any prop in the N-panel. Placed so
the random placeholder name is the first thing a first-time user can
replace, before reading the rest of the popup.

**`get_user_data()` no longer reads hostname/IP/OS name.** Same review as
the two notes above flagged `socket.gethostname()`/`gethostbyname()` and
`platform.system()` (`lib/session.py`) as OS-level info, alongside the
username. `"os"` was written but never read back anywhere -- dropped for
free. `"ip"`/`"machine"` (hostname) were genuinely used for display (the
farm workers panel, lock/kill confirmation messages) to tell apart two
machines run by the same person -- `"machine"` is now a short slice
(`machine_id[:8]`) of the same locally-generated id already used for lock/
worker ownership, `"uuid"` keeps the full id. `"ip"`'s one consumer
(`panels/farm_panel.py`, the workers list) now shows `"machine"` instead --
which, while there, turned up a second, unrelated bug: that same line read
`m.get("name", ...)`, a key nothing ever wrote (`get_user_data()` has
always used `"user"`) -- every worker row's name column silently showed
"unknown" regardless of who it was, `"ip"` was the only thing actually
telling rows apart. Fixed alongside the `"ip"` removal, since leaving it
broken would have made the panel useless once `"ip"` was gone too.

**`get_backup_filepath()` uses `extension_path_user()`, not
`script_path_user()`.** Not flagged by name in this review, but matches the
moderation guidelines' own example almost verbatim ("constructing paths to
write to... instead `bpy.utils.extension_path_user` must be used").
`script_path_user()` is the pre-Extensions, legacy-addon API (a shared
"scripts" user dir with no per-extension namespacing); `extension_path_user
(package, path=..., create=...)` is the one meant for this. `package` is
derived the same way `addon_pref()` (`lib/core.py`) already does --
`__package__.rsplit(".", 1)[0]` from within `lib/`, stripping only the
last segment so it still resolves correctly if Blender's real `__package__`
at runtime is namespaced (`bl_ext.<repo>.minimalist_pipeline.lib`), not
just the plain `minimalist_pipeline.lib` this reads during local dev.
Aside: `get_addon_version()` (`lib/core.py`) derives the same root package
name via `__package__.split(".")[0]` (first segment) instead -- correct
only for the unnamespaced 2-segment case, likely wrong under the namespaced
one. Not fixed here (out of scope for this pass), flagged for later.

**No custom submodule-reload loop in `__init__.py`.** An earlier version
force-reloaded every already-imported `minimalist_pipeline.*` submodule via
`sys.modules`, gated on `"bpy" in locals()`. Checked in the wrong place
(after `import bpy`, always true) -- a Blender Extensions Platform review
flagged it for not matching the documented reload pattern. Traced through
all three ways this file's top-level code actually re-runs (a real first
load, Blender's native "Reload Scripts", and the VS Code dev-extension's
own addon-update flow -- the latter's `dev.update_addon` operator purges
every `minimalist_pipeline*` entry from `sys.modules` before re-enabling,
confirmed by reading `blender_vscode/operators/addon_update.py`) and the
loop was a no-op in every one of them: `sys.modules` never held anything of
ours left to reload at the point it ran, gated or not. Removed outright
rather than fixed to match the doc's pattern, since it never did anything
regardless. Cost: `lib`/`operators`/`panels`/`farm`/`menus` changes no
longer show up on "Reload Scripts" during dev, only on a full Blender
restart -- accepted on purpose, not worth the loop's complexity for a
no-op.

**`prefs.user_name` doesn't reliably survive `unregister()`/`register()`.**
Blender's `AddonPreferences` storage lives on the `Addon` entry in
`bpy.context.preferences.addons[bl_idname]` -- and that entry itself, not
just the RNA class, gets torn down and rebuilt on a full disable/re-enable
(an extension update, "Reload Scripts" in some configurations, or manually
toggling it off and on) unless the values were flushed to `userpref.blend`
in between (an explicit "Save Preferences", or auto-save-on-exit). Reported
as `user_name` silently reverting to a fresh `random_display_name()` after
such a cycle even though it had already been set -- `_seed_user_name()`'s
own `if not prefs.user_name` check was working exactly as designed, it's
just that the value it was checking had already been wiped out from under
it by the time `register()` ran, same root problem `save_project_data()`/
`load_project_data()` already exist to work around for
`active_project_root`/`opened_projects` (see the JSON backup file, not
Blender's own prefs storage, note above). Fixed the same way: `user_name`
now rides along in that same backup JSON, written whenever
`save_project_data()` already runs (every project-list change, plus
`unregister()`) and restored by `load_project_data()` -- but only into an
still-empty `prefs.user_name`, so Blender's own storage stays authoritative
whenever it did survive intact, and `_seed_user_name()` only ever falls
back to a random placeholder when neither source has a name at all (a
genuine first-ever run).

## Lock staleness: 3x the heartbeat, not 1x

`LOCK_STALE_SECONDS = 90` (`lib/core.py`) is deliberately 3x the 30s
heartbeat interval (`heartbeat_30s`/`refresh_lock`), not equal to it — a
threshold equal to the heartbeat itself leaves zero margin, so one
missed/delayed beat (a slow network write, Blender busy on the main
thread) would let another machine's `acquire_lock()` steal a lock that's
still legitimately held.

## Copy/paste isn't always under `bpy.app.tempdir`

`_blender_internal_roots()` (`lib/libraries.py`) filters out Blender's own
copy/paste round-trips (any editor: 3D viewport, node editor, pose
library...) from the append/link warning, on the assumption every
`copybuffer*.blend` lands under `bpy.app.tempdir` — a per-session
subfolder (`/tmp/blender_XXXXXX/` on Linux). Found false: the node
editor's own copy/paste writes `copybuffer_nodes.blend` straight to the
bare OS temp root instead, so the directory check missed it and the
"you just appended data" popup fired on every node copy/paste. Fixed by
also matching on the filename itself (`copybuffer*.blend`) regardless of
which temp directory it's actually in, rather than widening the directory
check to the whole OS temp root — that would also swallow a genuine
append/link of a real file a user happens to have sitting in `/tmp/`.

## Department filter: three different callers, three different "current file"s

`tracked_department_items()`/`department_filter_items()` (`lib/browser.py`)
populate a department dropdown from whatever file they're asked about --
but "the file" means something different depending on who's asking.
`create_entry`/`edit_entry` have their own explicit `self.filepath` (the
file being tagged). `M_PIPELINE_OT_tracking_monitor` has no `filepath` of
its own -- its "current file" in the popup's file-details view is
`monitoring_detail("file")` (was `context.window_manager.file_details_selected`), which used to fall through
the old two-tier fallback (`self.filepath or bpy.data.filepath`) straight
to `bpy.data.filepath` -- whatever's open in the viewport, unrelated to the
file actually shown in the popup -- so the department dropdown only ever
offered "All departments" there. The sidebar's own entries panel has
neither: `bpy.data.filepath` (the open file) really is the right answer
for it. Fixed by trying all three in that order: `self.filepath` ->
`monitoring_detail("file")` -> `bpy.data.filepath`.

A first attempt gave `M_PIPELINE_OT_tracking_monitor` its own `filepath`
`@property` returning `monitoring_detail("file")`, reasoning `getattr(self,
"filepath", "")` would then pick it up like any other operator's real
`self.filepath`. Measured false: a plain Python `@property` (not a
`bpy.props` field) doesn't reliably survive attribute lookup on a live
operator instance during a dynamic `EnumProperty` items() callback --
`bpy_struct`'s own `__getattribute__` most likely resolves through RNA
first and never reaches it. Centralizing the fallback in
`tracked_department_items()` itself sidesteps the question entirely.

## Entries: two fields only ever guaranteed together, never accessed bare

`_draw_entry()`/`_get_entry_tooltip()` (`panels/tracking_panel.py`) each
had one bare `e["field"]` access sitting right next to a `.get()`-guarded
sibling on the same line -- both crashed the whole entries panel with a
`KeyError` the first time an entry didn't fit the assumption. `frame_start`
and `referenced_version` are independent optional fields (an entry can
carry a frame tag with no version picked -- routine for anything created
outside the interactive dialog, e.g. a batch/CSV import or a scripted
`create_entry()` call); `done` and `done_by`/`done_at` are only stamped
together by `toggle_entry_task()`, but nothing stops `done` being set some
other way without them. Both fixed to fall back the same way their
already-guarded sibling does: no crash, jump buttons/timestamp just read
as unavailable.

## Edit entry: a note turned task kept no checkbox

Older notes are stored with `"done": null` (a note isn't checkable).
Turned into a todo or an RTK, `edit_entry()` did `e.get("done", False)`
-- the key is there, so it kept `None`, and the checkbox only shows for
`True`/`False`: the entry read as a task with nothing to tick, a cache
reload changed nothing (the file said so). Now `None` becomes `False`;
a task that was done stays done.

## Edit-entry dialog: a stored department can outlive its own enum

`M_PIPELINE_OT_edit_entry.invoke()` (`operators/tracking_ops.py`) seeds
`self.department` straight from the stored entry (`e.get("department") or
"NONE"`) into a dynamic `EnumProperty` (`tracked_department_items`, §
"Department filter" above) whose valid choices are *this project's current*
department list. Nothing guarantees the two stay in sync: an entry tagged
`"lighting"` before that department was renamed or dropped from the
project's config -- or just hand-written/imported data that never went
through the dropdown -- makes the assignment raise `TypeError` (`bpy_struct:
item.attr = val: enum "lighting" not found in (...)`), which crashes
`invoke()` before the dialog even opens, taking down whatever operator
called it (`M_PIPELINE_OT_generic_entry_button`'s Ctrl+click, in
particular). Same failure shape as "Entries: two fields" above: stored data
drifting out of sync with a schema that can change over the file's
lifetime. Fixed the same way `shot_tag` and `referenced_version`, a few
lines further down in the same `invoke()`, already handle their own version
of this (stored value no longer among the live choices) -- wrap the
assignment and fall back to `"NONE"` instead of propagating the exception.

## Multishot row list: disabling a button isn't a guard

`_draw_shot_list()`'s Remove button (`operators/shot_ops.py`, shared by
`M_PIPELINE_OT_create_shot` and `M_PIPELINE_OT_edit_block_structure`) sets
`enabled = len(shots) > 1` so the last row can't be clicked away -- but that
only disables the button for a mouse click. Shift+R (Repeat Last) and the
F9 redo panel re-run `M_PIPELINE_OT_remove_multishot_item` directly with
its last-used `index`, and neither looks at button state, only at the
operator's own `poll()` (there wasn't one) -- so removing down to the last
row then repeating once more would empty `shots_list_creation`. Found while
chasing a reported "No shot number given" (see next section for the actual
cause that time), but a real latent gap in its own right: any caller
reaching `shot_number=[]` hits the same raw `PipelineError` from
`create_shot_file()`, since only `M_PIPELINE_OT_create_shot.execute()` (not
`edit_block_structure.execute()`) had its own friendlier "click Add" check
in front of it. Fixed at both ends: `M_PIPELINE_OT_remove_multishot_item`
gets a real `poll()` (the actual state guard, holding regardless of
invocation path), and `edit_block_structure.execute()` gets the same early
check `create_shot` already had.

## Multishot row list, take two: a clean-scene reset invalidates it

The actual cause of that "No shot number given" report: both operators
above read `shots = context.window_manager.shots_list_creation` once at
the top of `execute()`, then -- when "Start with a new clean scene" is
ticked -- call `bpy.ops.wm.read_homefile(use_empty=True)` *before* finally
consuming `shots` to build `shot_number`/`timeline` for `create_shot_file()`.
`read_homefile()` replaces `bpy.data` wholesale, including the
`WindowManager` datablock itself, so the already-fetched `shots` reference
is left bound to a datablock that no longer backs the live window
manager -- it reads back empty from then on, with no exception to flag it.
Unticking the checkbox "fixed" it, which was the tell: without
`read_homefile()`/`save_mainfile()` in between, the same reference is still
live when it's read. Fixed by snapshotting `shot_numbers`/`shot_starts`
into plain lists *before* the `create_clean`/dirty-save branch in both
`execute()`s, so the values used to build the new file no longer depend on
`shots` surviving whatever the "start clean" branch does to `bpy.data`.

## `_draw_timeline_warnings`: a trailing comma turned a string into a 1-tuple

`text = ("Inconsistent timeline ! ...",)` (`operators/shot_ops.py`) --
the trailing comma makes this a one-element tuple, not a string, so
`text_to_lines(warning.box(), text=text, ...)` crashed the whole "New
shot"/"Edit block structure" dialog's `draw()` with `AttributeError: 'tuple'
object has no attribute 'split'` the moment shot numbers or start frames
came out unordered (the exact case this warning exists to flag). The
sibling warning three lines down (`"Invalid numbers! ..."`) is a plain
string and never had the problem -- just a stray comma copy-pasted from a
one-line-per-item list elsewhere. Fixed by dropping the comma.

## CSV batch: the subprocess couldn't import itself

(The farm's two headless entries, `templates/farm_entry_render_setup.py`
and `templates/worker_render_entry.py`, had the exact same hardcoded
import -- every setup/render on an Extensions install failed the same way.
Same fix: `run_render_setup()` / `execute_render_request()` pass
`--addon-module`, the entries `importlib.import_module()` it.)

Every batch row failed with a bare "unknown error", no matter the row's
content -- `templates/batch_create_entry.py` hardcoded `addon_utils.enable
("minimalist_pipeline", ...)` and `from minimalist_pipeline.lib import
(...)`, but a real Extensions install's module name is namespaced (found
via a real headless Blender run: `bl_ext.vscode_development.
minimalist_pipeline` here, whatever the repo id is elsewhere) -- so both
calls raised `ModuleNotFoundError` before the script's own `try` even
started, its result JSON never got written, and `read_batch_result()` fell
back to reading the *request* JSON still sitting there (no `"message"`
key), which is why `batch_ops.py`'s `result.get("message", "unknown
error")` produced that exact generic string instead of a real one.

Fixed two ways: `launch_batch_create_entry()` (`lib/batch.py`) now derives
its own real module name the same way `get_backup_filepath()` already does
(`__package__.rsplit(".", 1)[0]`) and threads it through the request JSON;
the entry script does `importlib.import_module(f"{addon_module}.lib")`
instead of a static `from minimalist_pipeline.lib import ...`. Just as
important: the `addon_utils.enable()`/import step moved *inside* the
script's own `try`, which used to wrap everything except that -- so any
future failure there now writes back a real message instead of silently
leaving the stale request JSON in place. Verified for real (register the
addon, run the entry script against a throwaway project, inspect the
resulting `.blend`'s camera markers) rather than by re-reading the code --
see [[no-live-blender-verify-via-stubs]], headless Blender turned out to
be reachable from here after all.

## Network-share redraw cost: caching disk reads off draw()/poll()/enum callbacks

Reported as "the farm works fine on my machine, but lags/crashes at the
studio" -- the studio's project lives on an SMB share, read concurrently by
several Windows machines; a home setup is one machine on local NVMe. Every
`stat`/`exists`/`iterdir`/JSON read that's cheap (microseconds) locally
becomes a network round-trip on a share, and `draw()`/`poll()`/an
enum-items callback all re-run on *every redraw* -- dozens of times a
second while the mouse moves over an open popup/dropdown. Any disk access
at those call sites is multiplied accordingly; none of it is Windows- or
SMB-specific in how it was fixed (plain mtime/TTL caching, no platform
branch), it's just where the cost is large enough to notice.

Found and fixed, worst first:

- **Orphaned stale locks, the one factor unique to the studio.**
  `check_lock()` (`lib/core.py`, the read path of `locked_json`) used to
  poll blindly for up to `retries*delay` (default ~1s) as long as a
  `.xxx.json.lock` file existed, without ever checking its age --
  `_is_unlock()` (the staleness check) was read-path-blind, only the writer
  side (`acquire_lock`) called it, to steal a stale lock. A crash mid-write
  (the very freeze being reported) leaves an orphaned lock behind, which no
  reader ever cleans up (only a writer passing by, 90s later, and only if
  one does) -- so every UI-thread read of that file, on every machine,
  pays the full ~1s sleep indefinitely after. A home setup never crashes
  mid-write under normal use, so it never sees an orphaned lock, hence no
  symptom. Fixed: `check_lock()` now checks `_is_unlock()` on every poll and
  returns immediately once a lock reads as stale, instead of waiting out
  the rest of the budget. `locked_json`'s own docstring already documented
  "UI-thread readers pass `retries=0`" as the convention -- true in spirit
  (safe: writes go through `os.replace`, so a stale read only ever sees the
  previous version, never a half-written file) but not one call site
  actually did, so every UI-facing `read_only=True` call in the hot path
  (`TrackingStatusCache._scan_and_compute`, `find_linked_by`'s index
  refresh, `is_block_archived`, `scan_workers`, the farm jobs scans) now
  passes it explicitly too.
- **`find_linked_by()`'s full-project scan.** Used to `project_root.rglob(
  ".pipeline/*meta")` on every redraw of the tracking popup's file-details
  view (its own docstring called this out: "uncached, full-project scan")
  -- that walk descends into `renders/` too, by far the largest subtree
  (every rendered frame, of every version, ever). Fixed in two parts: an
  inverse index (`_linked_by_index`, target folder -> linker folders) built
  once per popup open (`refresh_linked_by_index()`, called from
  `M_PIPELINE_OT_tracking_monitor.invoke()` alongside its existing
  `TrackingStatusCache.get_all(force_reload=True)`) so `draw()` only ever
  does a dict lookup; and `_iter_pipeline_files()`, which walks `assets/`,
  `library/`, `shots/` individually instead of the whole `project_root` --
  structurally sound regardless of exact nesting depth (handles the
  branch-archive `old/` folder wherever it lives), and never touches
  `renders/` or `config/` at all. `TrackingStatusCache.get_all()` reuses the
  same helper for the same reason.
- **Browser enum callbacks re-listing folders every redraw.**
  `asset_folder_items`/`sequence_items`/`shot_items`/`version_items`
  (`lib/browser.py`) used `Path.iterdir()` + `Path.is_dir()` per entry --
  on a share, that's a second round-trip per entry beyond the directory
  read itself. `cached_scandir()` (`lib/core.py`) replaces both: it caches
  `os.scandir()`'s `DirEntry` list on the directory's own mtime (changes
  exactly when a direct child is added/removed/renamed, which is exactly
  what these listings show), and `DirEntry.is_dir()` reads the stat info
  `scandir()` already fetched instead of stat-ing again. `list_active_blocks()`
  (`lib/tracking.py`) uses it too; `is_block_archived()` got its own
  mtime-keyed cache alongside it (one `stat()` per call instead of a
  lock+read every time, every shot, every redraw).
- **`TrackingStatusCache.get()` re-validating on every call.** Even with a
  warm cache, confirming it's still warm costs `is_file()` + `exists()` +
  two `stat()`s (`_pipeline_mtime()`) -- and one redraw of the file panel
  calls `.get()` several times (`draw()`, `get_description()`,
  `get_current_departments()`, the department enum...). Added a short TTL
  (`_VALIDATE_TTL`, `time.monotonic()`, ~1.5s) that skips re-validation
  within the window: worst case, a change made on another machine takes up
  to that long to show up here, the same tradeoff every other mtime-keyed
  cache in this module already makes.
- **`WorkTimeCache` re-scanning rotated archives on every `session_end`.**
  Archives (`sessions_log_*.jsonl`) are rotated out once and never written
  to again, but the cache's only invalidation key was the *current* log's
  mtime -- so every session end (which only touches the current log)
  forced a full re-read of every archive too. Split into two caches: the
  archive set, keyed on which archive files exist (so it's built once and
  never rebuilt unless a new archive actually appears), and the current
  log, re-scanned on its own mtime as before.
- **`scan_workers()`/the farm job scans taking a write lock to read.**
  `scan_workers()` (`farm/workers.py`, called directly from
  `draw_farm_workers()`) and `_scan_active_jobs()`/`_scan_incoming_jobs()`
  (`farm/loop.py`) all called `locked_json()` without `read_only=True` --
  an exclusive O_CREAT|O_EXCL lock file created and removed per job/worker
  file, per scan, for something that never writes anything back. Now
  `read_only=True, retries=0` throughout. `scan_workers()` additionally got
  a ~1.5s TTL cache (`time.monotonic()`): `draw_farm_workers()` re-runs it
  on every redraw of the farm popup's Workers tab, far more often than a
  heartbeat (refreshed once per `farm_tick`, ~10s) can meaningfully change.
  The jobs scans were already gated on their directory's own mtime
  (`_jobs_scan_cache`, unchanged) -- only the lock mode needed fixing there.
- **`file_in_active_project()`'s double `resolve()` per poll.**
  `M_PIPELINE_PT_file_panel.poll()` calls it with the same
  `(bpy.data.filepath, project_root)` pair on every sidebar redraw
  candidate between file opens; `Path.resolve()` walks symlinks component
  by component, a round-trip per component on a mounted share. A
  single-slot memo (not a dict -- there's only ever one "current" pair
  worth remembering) keyed on the exact pair short-circuits every repeat.

Rejected: funneling `is_block_archived()` through `TrackingStatusCache.get()`
instead of its own small cache, since the cache already exposes an
`archived` key (it passes `global_data` through from `tracking.json`
mostly unmodified). Rejected because `TrackingStatusCache._scan_and_compute()`
does much more than read one flag -- it also walks every `.wipmeta` since
the last stable to compute worked/validated departments -- so the first
(uncached) check of each shot while enumerating a whole sequence would do
strictly more disk work than the direct read it replaced, just to get one
boolean. A dedicated cache, mtime-keyed the same way, avoided that without
coupling the two further.

## "Render" button opening pre-filled: an operator property's own redo memory

`M_PIPELINE_OT_farm_request_render.filepath` decides which dialog `invoke()`
shows: a specific file's render settings if set, the file list/picker if
empty (`project_panel.py`'s and the top bar's plain "Render" buttons rely
on this, neither sets `.filepath` at all). Reported as that picker opening
pre-filled with whatever file was last rendered through `file_panel.py`'s
own "Render" or the top bar's "Render this file" (both of which do set
`.filepath = bpy.data.filepath` deliberately) instead of showing the list.

Not a logic bug in `invoke()`/`draw()` -- `self.filepath` really was
non-empty. The property itself was the bug: a plain `StringProperty`
without `options={"SKIP_SAVE"}` is remembered by Blender across
invocations (the same mechanism behind an operator's redo panel/F9) --
a button that never touches that property doesn't get the field's own
`default=""`, it gets whatever the *last* call set it to, regardless of
which button fired it. `M_PIPELINE_OT_create_entry.filepath` already
carries `SKIP_SAVE` for exactly this reason (`operators/tracking_ops.py`);
this operator's own `filepath` had simply been missed. Same risk applies
to any operator property meant to mean "nothing selected" by default
while also having another call site that deliberately passes a real value
-- `SKIP_SAVE` is the fix, not resetting it by hand in `invoke()` (that
would also wipe a value a caller *did* just pass in).

## Windows: replace/delete refused while a reader has the file open

Studio-only symptom (never at home): the farm monitor logged `[WinError 5]
Accès refusé: 'monitor.lock.tmp' -> 'monitor.lock'` and `[WinError 32] ...
'.monitor.lock.lock'` every few ticks, and a job sat in `setup_start` long
after its setup subprocess had finished.

**Not a permissions problem** -- the same write succeeds a tick later.
Python maps both `ERROR_ACCESS_DENIED` (5) and `ERROR_SHARING_VIOLATION`
(32) to `PermissionError`. `os.replace()` has to open the *target* with
DELETE access (the old file goes away), and Python's `open()` never passes
`FILE_SHARE_DELETE`, so any reader holding the target open at that moment
makes the rename fail -- and Windows reports that case as 5, not 32. Over
SMB the window is wider than Python's own `open()`/`close()`: the client
may keep the handle open server-side a little after `close()` (handle
caching under SMB2 leases), so even millisecond reads every 2 s from a few
machines' farm popups collided with the monitor's every-10 s rewrite most
of the time. A local disk has none of this, hence "works at home".

**Why the job froze**: `monitor_tick()` ran the heartbeat write and then
`scan_processes()`/`scan_queue()` in one `try` -- a failed heartbeat
skipped both, and `scan_processes()` is what moves `setup_start` to
`setup_finished`. The loop kept ticking, it just did almost nothing.

What changed, cheapest to most structural:

- **Each tick step has its own `try`** (requests, heartbeat, processes,
  queue). A failed heartbeat now costs at most a "stale" label, never the
  queue.
- **Heartbeat in two layers.** The content's `update_tick` is still
  rewritten every tick -- readable by eye, and what older addons read --
  but best effort: one lock attempt, one replace attempt
  (`locked_json(..., retries=1, io_attempts=1)`), failure ignored. Right
  after, `os.utime()` bumps the file's mtime: attribute-only access,
  which Windows' share-mode check ignores, so no reader's open handle can
  refuse it. Readers take the newer of the two (`monitor_last_tick()` in
  `farm/loop.py`, status thresholds in `monitor_age_status()`). Rejected:
  mtime only, content written once -- would have made the file's own
  `update_tick` meaningless to anyone reading it, and shown a running farm
  as stale to any machine on an older version. Same clock caveat either
  way: both stamps come from the monitor machine's clock.
- **`retry_shared_io()`** (`lib/core.py`): `os.replace`/`os.remove`/lock
  `unlink` retry on `PermissionError` (5 x 0.1 s) before giving up --
  covers the other shared files with the same exposure (job files written
  by the setup subprocess while popups read them, incoming requests).
  A failed replace no longer leaves its `.tmp` behind.
- **`release_lock()` never raises** (it runs from `locked_json()`'s
  `finally`, a raise there masked the caller's own outcome) -- a lock it
  couldn't delete just goes stale.
- **`_is_unlock()`**: a lock file that raises `PermissionError` on read is
  "held", not "corrupt" -- treating it as stale let a writer steal a live
  lock mid-deletion.
- **`is_blender_monitor()`** keeps its previous answer when the read fails
  instead of returning False: `farm_tick()` deregisters the whole loop on
  False, so one refused read used to kill the monitor silently (header
  went Stale then Dead, nothing in the log).

## Farm subprocess output: files, never pipes

Studio symptom: a block's setup sat in `setup_start` for good, its
`blender -b` subprocess still alive (`poll()` → `None`) and the job JSON
never written. Reading `p.stderr` by hand from the console unblocked it and
it finished cleanly -- the process had been **blocked writing to a full
pipe**. `run_render_setup()` captured stderr with `PIPE` "for
`scan_processes()` to log on failure", but nothing reads a pipe until the
process has exited; a pipe holds ~4 KB on Windows, and a production block
with linked rigs prints a page of depsgraph/driver warnings on load
("Failed to add relation 'Copy Transforms'", "Error in PyDriver"). Over
the limit, the child's next write blocks forever. Test scenes at home
never print that much, so it never showed there. `checks_images()` had
the same exposure (ffmpeg writes one stderr line per corrupted frame).

Fix: every farm subprocess writes to a file (`popen_logged()`,
`farm/dispatch.py`); `scan_processes()` reads it back once the process has
exited (`read_process_log()`).

- **One log per job**, `requests/request_<job_id>.log`: setup,
  checks_images, compilation and preview all append to it under a
  `===== <stage> <time> =====` header (they run one at a time on the
  monitor machine). Each Popen remembers the offset its own section starts
  at, so the frame check counts only its own lines.
- **Worker renders keep one file per machine**,
  `request_<job_id>_<uuid>.log`: several machines can render one job at the
  same time, and concurrent appends from different machines to one file on
  a share interleave. The worker used to leave its handle on that file open
  for good (`stdout=open(...)` inline) -- now closed right after `Popen`.
- **Deleted when it ended well, kept otherwise**: the job log on `finished`
  (unless the frame check found corrupted frames -- that list lives only in
  the log), `split_finished` and `preview_finished`; a worker's render log
  when its render exits 0. Anything failed keeps its log, and `archive()`
  moves `request_<job_id>*.log` along with the job.
- The parent closes its handle as soon as the child has its own copy --
  otherwise Windows can't delete the file afterwards.

Found alongside, fixed in the same pass:

- `scan_processes()` appended `"<last stage minus _start>_finished"`
  whatever the last stage was -- a job hand-edited back to `queued` while
  its old setup process was still tracked became `queued_finished`, a stage
  nothing handles. It now only advances a `*_start` stage, and stops
  tracking the process otherwise.
- It popped the job from `_active_processes` *before* its job-file write
  committed; a refused write lost the process for good and froze the job.
  Now popped only after the write.
- No `try` per job: one unreadable job file raised every tick before the
  other jobs were reached, so none of their processes was ever seen to
  finish. Each job now goes through `_finish_job_processes()` in its own
  `try`; a job whose file is gone just stops being tracked.
- `run_render_setup()` called `mark_stage(job_path, "setup_failed")` from
  inside its own `locked_json(job_path)` -- waiting on its own lock, then
  raising. Now records the failure in the same transaction.

## Re-rendering a file: match the render, not the job

A job id is `_file_key()` = hash(file + preset + shot_override), on
purpose: it's the dedup key, so a double submit of a file already in
flight waits instead of rendering twice. Putting the submit time in it
would drop that protection.

The catch: re-rendering the same file later reuses the id. The worker's
`last_job_result` still said `{job_id: X, success: True}` from the
previous render, and `check_render_completion()` matched on `job_id`
alone -- so the tick after dispatching the new render saw "done", moved to
`render_finished`, and ran the frame check and compilation on frames
still being rendered.

Fix: `render_dispatch()` stamps a `dispatch_id` (random, per dispatch) on
the job; `render_request()` copies it into every request; the worker
echoes it back in `last_job_result` (and in a cancelled result).
`_is_this_render()` compares `dispatch_id`. If either side has none
(a worker or monitor on an older version), it falls back to "result
stamped after this job's `render_start`" -- two machines' clocks, same
caveat as everywhere else (`now()`).

### Setup waits for a local render; ffmpeg stages don't

`local_slot_busy()` only counts the monitor's own processes, not a render
the same Blender instance runs as a worker -- so on the machine that is
both, a setup (a whole second `.blend` loaded) could start mid-render.
`scan_queue()` now also holds `queued` → setup while
`local_render_running()`. Only setup: making the frame check/compilation
wait too would queue job A's post-render steps behind job B's entire
render (B gets dispatched to the freed worker in the same tick). Only
covers a worker in the same instance as the monitor -- a worker in a
second Blender on the same machine isn't visible from here.

Exception (`_setup_unblocks_idle()`): machines idle with nothing to take
-- the running renders single-machine or with no chunk left free, no
set-up job they may render -- while the host renders for hours. Then
the setup runs alongside: the `.blend` loaded twice for the setup's
length, against the whole farm held back for the host's render. Only if
the queued job may itself go to one of them (`assigned_machines`).
Rejected: stopping the host's worker after its frame to run the setup,
then relaunching it -- a render cut short for what a setup alongside does
without.

## Crash recovery: resume, don't orphan

When the Blender instance running the farm dies (crash, kill), its child
processes don't: on Windows, Linux and macOS alike a child outlives its
parent. Setup, ffmpeg and renders finish their work and write it to disk --
only the *tracking* is lost (`_active_processes`,
`_worker_active_processes`, both in memory). What happened at relaunch
before:

| stage at the crash | then |
|---|---|
| `setup_start`, `checks_images_start`, `compilation_start` | marked `orphaned` -- terminal, manual resubmit, even if the process had finished fine |
| `preview_start` | not in that list: stuck for good |
| `render_start`, worker in the crashed instance | nobody ever publishes its `last_job_result`: stuck for good |

Now:

- **PIDs are recorded** in the job file at launch
  (`track_local_processes()`: `local_processes = {machine, pids:
  [[pid, name]]}`) and in the worker file for a render (`current_pid`,
  `current_job_id`, `current_dispatch_id`).
- **`process_alive(pid, name_hint)`** (`lib/core.py`), stdlib only:
  Windows `OpenProcess`/`GetExitCodeProcess` via `ctypes`, POSIX
  `os.kill(pid, 0)` + `ps` (zombie = dead). The name hint ("blender",
  "ffmpeg") guards against PID reuse by an unrelated program. A PID
  recorded on another machine can't be checked -- treated as gone.
- **Monitor relaunch** (`recover_interrupted_jobs()`, replaces
  `detect_orphaned_jobs()`): a local `*_start` job whose process is still
  alive is **adopted** (`AdoptedProcess`, polled by PID) and judged when it
  ends; otherwise it's **resumed** right away
  (`resume_interrupted_stage()`): setup → `setup_finished` if it already
  wrote its result (frame range or split), else `queued`; checks →
  `render_finished`; compilation → `checks_images_finished`; preview →
  `preview_queued`. All of these are safe to redo -- ffmpeg overwrites its
  own output; setup is checked on disk first because redoing it would
  create a new output folder (increment). An adopted process's exit code
  can't be known (it isn't our child), so its end goes through the same
  resume rule, never straight to finished/failed.
- **Worker relaunch** (`_recover_previous_render()` in `launch_worker()`):
  if the previous worker of this machine was mid-render, adopt the render
  by PID while it runs, then (or right away if it's gone) publish
  `last_job_result = {lost: True, dispatch_id}`.
- **Monitor side** (`check_render_completion()`): a `lost` result for this
  dispatch, or a worker silent for `WORKER_GONE_SECONDS` (180 s -- well past
  a missed beat or a Blender restart): its claim is freed, its chunk free
  again for any machine -- the frames it finished stay, no need to know
  whether the lost render ended well (see "Farm 1.1.0: chunks replace
  placeholders"). A pending request the lost worker never picked up is
  deleted, so it can't run later for a dispatch nobody waits on.

Old jobs already marked `orphaned` stay that way (terminal).

## Sidebar redraw: 341 ms of network calls, 0 notes on screen

Studio profile (cProfile, 11 s of hovering the sidebar, 0 notes): 24
redraws of the File panel cost 8.2 s -- **341 ms each**. Every disk call on
that share took ~13-15 ms, and a redraw made dozens:

- `ConfigCache.get_path()` built every path through `to_absolute()`, i.e.
  `Path.resolve()` -- on Windows two `_getfinalpathname` calls, two network
  round-trips, just to append `"config/..."` to the project root. 175 calls,
  41 ms each.
- `ConfigCache.get()` called `get_path()` plus a `stat()` of the config,
  every call -- and it's reached from everywhere: `parse_filename()` (twice
  per redraw, through the regex getters), `_meta_stem()`, the tag enum,
  every `json_get(ConfigCache.get(), ...)`. 148 calls, 52 ms each.
- `TrackingStatusCache` revalidated with `is_file()` + `exists()` + `stat()`
  + `exists()` + `stat()`.
- The farm panel header did `monitor.lock.exists()` on every redraw.

Fixed:

- `get_path()`: plain join + `normpath`, memoized per (project root, name).
  Nothing to resolve in a fixed sub-path of the root.
- `ConfigCache.get()`: re-stat the config at most every `_VALIDATE_TTL`
  (2 s); keep serving the last good config if the stat fails (share
  hiccup) instead of raising into `draw()`. `invalidate()` resets the
  window, so an edit made from this machine shows at once.
- `TrackingStatusCache`: owner folder decided from the file name
  (`_owner_dir()`: `.blend` → parent), not `is_file()`; `_pipeline_mtime()`
  is two `stat()`s, no `exists()` first. TTL 2 s.
- Farm header/panel and the top bar menu read the status cache
  (`_status_tick()`, every 10 s) instead of `exists()`; launching the farm
  refreshes that cache immediately.

Measured on the real `draw()` (File panel + farm header) with call
counting: 6 `stat` + 6 `resolve` per redraw before, 0 after -- the only
disk calls left are ~3 `stat` every 2 s, whatever the redraw rate.

Still open, lower priority: the notes list (one `to_absolute()` per note
with a frame range, `text_to_lines()` rewrapping every note on every
redraw -- ~28 ms of pure CPU per redraw at 100 notes), and `heartbeat_30s`
(~0.5 s of locked session/lock-file writes every 30 s on that share).

## Farm popup: worker state, open-folder button, refresh cost

**"Add this machine" showed the wrong state.** Whether this Blender
instance is the worker lived in `Scene.is_worker` -- a scene property, so
it's *saved into the .blend*: a file saved while its instance was a worker
reopened showing "worker" when it wasn't. On top of that,
`is_blender_worker()` set it True as soon as the machine's worker file
existed, before even comparing its pid -- any leftover worker file (another
instance, a crash) flipped it on. Now it's runtime state in memory
(`this_instance_is_worker()`, `farm/workers.py`), set by `launch_worker()`/
`kill_worker()` and by `is_blender_worker()`'s actual pid comparison. The
property is no longer registered; old files keep a harmless stale ID
property. `is_blender_worker()` also reads read-only now (no writer lock
every tick) and keeps its last answer on a failed read, like
`is_blender_monitor()`.

**Open-folder button per job**: `_build_job_entry()` carries `output_dir`
(the folder the job renders into, a plain join on the project root -- no
`resolve()`), and each row with one gets a `wm.open_folder` button.

**Filters and pages.** The jobs list is filtered and paginated in
`draw_farm_jobs()`, like Project monitoring's table: everything is already
in the monitor cache, so filtering costs no disk call. Sorted on
`submitted_at` (first stage of `stage_history`, or the request's
`submitted_at` for a pending one), newest first: the reader thread lists
files in arbitrary order, which would shuffle jobs across pages between
two refreshes. Never `stage_at`, which moves on every stage. The search
fields are `SKIP_SAVE` -- a search remembered from last time would hide
jobs/files without saying why -- and any filter change goes back to page 1.
The job detail's JSON button reuses `wm.open_folder` on the file itself
(`os.startfile`/`open`/`xdg-open` open a file with its default app too).

**Retry.** A failed job is rewound in place (`retry_job()`,
`farm/queue.py`), the same way crash recovery resumes one: a stage entry
`{"resumed": "retry"}` back to the stage before the failure
(`_RETRY_STAGE`). Resubmitting would have gone through setup again, which
increments the output folder -- the point is the same folder, frames and
preset. Only `*_failed` stages are retryable; a job
already archived by hand is moved back to `actives/` first (checked as
failed before moving).

**To check is never lost.** `compilation_finished` used to call
`mark_render_to_check()` (never raises, logs) and move on: one locked
tracking.json on the share and the render never showed up to check. It now
only marks the job finished once the flag is written (`_flag_to_check()`),
retrying on the next ticks; after `_TO_CHECK_ATTEMPTS` (~5 min) it gives up
with an ERROR log rather than hold the job forever. A folder with no
tracking.json counts as done (nothing to flag). The thumbnail refresh moved
after it: it would otherwise launch a Blender on every retried tick. The
entry also records the compiled `video`, for the To check column's play
button; older entries fall back to the newest video in the render folder,
looked up on click, never in draw().

**"Checked" can validate departments.** Checking a render is usually the
moment its department is done, so "Checked" asks which of the file's
required, not-yet-validated departments to validate along with it
("render" preselected) -- the same `set_department_validated()` as the
file detail's toggles, so it needs a stable version; without one, or with
nothing left to validate, no dialog: it just marks the render checked.
The checklist is a WindowManager collection (like the Render dialog's
shots), not a dynamic ENUM_FLAG: that one drew as an empty box in the
dialog.

**"Checked" archives the job.** Once a render is checked in Project
monitoring, its job has nothing left to show in the Farm popup: the
operator archives it (`_archive_checked_job()`, `operators/tracking_ops.py`)
-- only if it is still in `actives/` and reached `finished`, never a job
in flight. A split block's parent job (`split_finished`) has no
`to_check` entry of its own and stays in the list.

**Refresh cost** (the popup's `_refresh_tick()`, every 2 s, UI thread):

- Frame progress listed the whole render folder with `glob()` through
  `to_absolute()` (a `resolve()`) on every refresh. Now `cached_scandir()`
  (re-lists only when the folder's mtime changed) and no resolve.
- It also counted placeholders: renders ran with `use_placeholder` (until
  1.1.0), which writes an empty file per frame when it *starts*. Only
  non-empty files count (`DirEntry.stat()` -- free on Windows, the listing already has
  the size).
- Workers are read once per refresh into the snapshot
  (`_compute_snapshot()` → `cache["workers"]`); `draw_farm_workers()` no
  longer calls `scan_workers()` -- `draw()` reruns on every hover.
- `locked_json(read_only=True, retries=0)` is now one disk call (just the
  read): it used to look at the lock file first (result unused when not
  waiting) and `exists()` before reading.

Measured with call counting (2 rendering jobs, 3 workers): per popup redraw
1-3 disk calls before → 0; per refresh 7 + 2 resolves + the workers read
from draw → 9 in total.

Also fixed in the Jobs view: 0 frames done divided by zero and broke the
whole popup's draw; and "remaining" showed the estimated *total* time
(`elapsed / pct`) -- now `elapsed / pct - elapsed`.

## Popups on a network share: nothing on disk in draw(), heavy reads off the UI thread

Studio profiles: the Open file dialog spent 32 of 43 profiled seconds in
6745 `is_block_archived()` + 2446 `cached_scandir()` calls; Project
monitoring froze Blender for minutes on open (it never even showed up). Each disk call on that share costs ~10-15 ms. Two rules came
out of it:

**1. Enum callbacks and draw() never wait on the disk.** Blender evaluates
an EnumProperty's items callback on every redraw, on every read of the
property (`self.shot` in `get_folder()`), and once per expanded item -- an
mtime-keyed cache still costs one stat per call. `cached_scandir()`,
`is_block_archived()`, `ConfigCache.get()`, `TrackingStatusCache.get()` and
the worker scan all re-check their key at most every 2 s (`SCANDIR_TTL` /
`_VALIDATE_TTL`); `exists()`/`is_dir()`/`is_file()` before a listing are
gone (`cached_scandir()` returns [] for a missing folder; a `.blend` vs
folder is decided from the name). The three identical `_resolve()` (Open
file, Open file version, Render) share `resolve_version_file()`.
Measured: Open file, 60 shots, sequence "All": 70 disk calls per redraw →
0.

**2. A scan that has to read many files runs on a reader thread.** Not
time-slicing on the main thread: one folder's status is 5-10 reads, so a
"small" step was already 100-160 ms at studio latency (tested). Instead:

- `ProjectScan` (Project monitoring): a daemon thread walks
  assets/library/shots (stopping at each folder owning a `.pipeline/` --
  `rglob` used to descend into every textures/cache subfolder), stats each
  `.pipeline/`, and reads only what changed (`_collect_folder()`,
  `_read_link_targets()`); a `bpy.app.timers` tick on the main thread
  applies the results (`_status_from_raw()`, memory only) and redraws the
  popup. The popup opens at once on what's known and fills in ("Scanning
  project... N folders"); file details shows "Linked by: scanning..." until
  the index is built. `find_linked_by()` never builds the index from a
  draw() anymore.
- Farm popup refresh (every 2 s) and the sidebar's farm status (every
  10 s): `_BackgroundRead` runs `_read_farm_raw()` / `_read_farm_snapshot()`
  on a thread; the tick only applies (`_apply_farm_snapshot()`).

The thread-side functions are **pure os/json** (`read_json_quiet()`): no
`bpy`, no `ConfigCache`/prefs (paths are resolved on the main thread and
passed in), no `locked_json()` (it calls `get_machine_id()` → prefs), no
`log()`. Reading never needs a lock -- every write is an atomic
`os.replace()`. Anything that needs `bpy` (thresholds from the config,
`log()`) happens in the tick.

Measured at 14 ms per disk call (simulated): Project monitoring scan, 60
folders: 806 reads in the background, **longest UI stall 1 ms**, 0 disk
calls on the UI thread; reopening with nothing changed: 186 calls (all in
the background). Farm popup: 0 farm-related disk calls on the UI thread
(only `ConfigCache`'s one stat per 2 s remains).

**Fewer reads per folder** (exact, not approximate): the latest stable is
found by reading stablemetas newest-first by file mtime and stopping once
the rest are older than the best `created_at` found; wipmetas whose file is
older than that stable are skipped unopened (a meta's dates can't be later
than its own file's mtime). `_CLOCK_MARGIN_SECONDS` (10 min) absorbs clock
skew between machines -- it only ever makes the scan read one file too
many. Checked against a full read of every meta: identical statuses.

Also: `read_project_config()` took the config's *writer* lock (creating and
deleting a `.lock` file on the share) just to read it; now read-only.

## A tick shows at once

A department ticked, a task checked, a note written: it showed late, or
showed then flipped back. Three causes, one per cache layer:

- **No refresh after the write.** Most operators wrote and returned:
  `TrackingStatusCache.get()` then served the old status for up to
  `_VALIDATE_TTL` (2 s) -- longer on a share whose client caches the
  mtime -- and Project monitoring's table, which only reads `known()`
  (memory), until the next scan. A second click inside that window read
  the stale state and wrote the same value again: the first click undone.
  Now every write operator calls `status_changed(filepath)`
  (`lib/monitoring.py`): that one folder computed again
  (`get(force_reload=True)`, a few reads, nothing else), then every
  `VIEW_3D` and `PROPERTIES` area tagged for redraw -- the sidebar and the
  monitoring windows, the views that show a status. Tagging a whole
  window is a flag, not a draw: Blender redraws once.
- **A scan undid the write.** `ProjectScan`'s thread reads a folder, the
  user ticks, `status_changed()` caches the new status, then the tick
  applies the thread's older read over it. `_fresher_here()` skips a
  folder whose status was computed since the scan started
  (`TrackingStatusCache._computed_at`) from a `.pipeline/` no older than
  the one the thread saw. Both conditions: a status computed here before
  someone else's write on another machine is still replaced. Reproduced
  headless (scan read, write, tick): without the check the entry count
  went 2 → 1.
- **Two statuses under one key.** `get()` on a `.blend` computed from that
  version's wipmeta only, on the folder from every wipmeta since the
  stable -- both stored under the folder's key with the same mtime, so
  whichever read last won: the sidebar's redraw could leave Project
  monitoring showing the open version's work only, until a scan put the
  full one back. `_collect_folder()` lost its `wip_stem`: one folder, one
  status. The extra wipmetas are those since the latest stable (older
  ones are skipped by mtime, unopened), read only when `.pipeline/`
  changes.

A review import touches many folders: rather than a `status_changed()`
each, it starts a `ProjectScan` -- the thread reads only the changed ones.

## Project walk: a stray .pipeline/ hid every asset below it; popup regions must not outlive their popup

**Stray `.pipeline/`.** 1.0.9's walk (`_walk_owner_dirs()`, `ProjectScan`)
stopped descending at the first folder holding a `.pipeline/` -- to stay
out of textures/caches below an asset. A real project had
`assets/ch/.pipeline/` next to `ch_ball/` and `ch_tailball/`: the walk took
`assets/ch` for an asset and never saw the assets inside it (`ch_ball`
still showed only because the File panel had cached it while open). The old
`rglob` found every `tracking.json` at any depth, so it didn't hit this.
Now (`_is_tracked_owner()`): a folder is an owner only if its `.pipeline/`
holds a `tracking.json`, *and* it's at least `_MIN_OWNER_DEPTH` (2) below
assets/library/shots -- a prefix or sequence folder is never an asset or a
shot by convention, whatever it contains. Where the stray came from: it
was *empty*, so nothing wrote a meta in it -- a lock attempt or a read on a
path computed from an asset *folder* instead of a `.blend`
(`folder.parent / ".pipeline" / ...` is the prefix folder) created the
directory: `acquire_lock()` creates the lock file's parent, and until
1.0.7's cleanup `check_lock()` did too, on plain reads. Every current
caller passes a `.blend`, so the source was likely an older version; to
make it impossible now, every meta path goes through `_meta_path()`,
which refuses anything but a `.blend` (PipelineError) -- and
`get_session_worked_departments()`, read by draw(), returns [] instead.

**Popup regions.** `ProjectScan` kept `context.region_popup` to redraw the
monitoring popup as results came in, and the farm popup did the same
(`_popup_regions`). Blender frees that region when the popup closes; a
Python reference to it doesn't know, and `tag_redraw()` on a freed region
doesn't raise -- it crashes Blender, or not, depending on whether the
memory was reused yet (reported: "scanning crashes Blender", then not). Now
`ProjectScan` keeps no region at all (the popup refreshes on the next mouse
move), and the farm popup forgets its regions after each redraw (a live
popup re-registers from its draw(), a closed one can't) and on close
(`unregister_refresh_timer()` -- it used to be cleared only with the status
timer, so reopening the popup redrew the previous, freed one).

## Next version number: never from a cached listing

`get_last_version_number()` went through `cached_scandir()` so the
increment dialog's filename preview cost nothing per redraw -- but
`save_as()` uses the same function to pick the name it *writes*. Once
`cached_scandir()` stopped re-checking the folder's mtime within
`SCANDIR_TTL` (2 s, see "Popups on a network share"), a version saved in
that window -- by another machine, or a second increment right after the
first -- was invisible, and `save_as()` would have reused its number and
overwritten it. Now `cached=True` is opt-in, passed by the dialog's
`draw()` only; every other caller lists the folder fresh. Same rule for
any future use of `cached_scandir()`: it may feed what's *shown*, never
what gets *written*.

## One farm snapshot reader, sync or threaded

When the farm popup's refresh moved to a reader thread, the original
synchronous path (`_compute_snapshot()` and its `_scan_active_jobs()`/
`_scan_incoming_jobs()`/`_read_monitor_status()`, still used on project
switch and right after a launch) stayed alongside it: two implementations
of the same snapshot, already drifting (only one counted frames from the
thread's results). `refresh_monitor_cache()`/`refresh_monitor_status()` now
run the thread's own pure functions (`_read_farm_snapshot()`,
`_read_farm_raw()`) inline and apply them the same way; worker files are
read by one function (`read_workers()`) for both `scan_workers()` and the
thread. Same cleanup in `lib/tracking.py`: `ProjectScan` had replaced
`TrackingStatusCache.get_all()` and `refresh_linked_by_index()`, which
stayed behind unused with their own copy of the project walk -- removed,
`ProjectScan` walks through `_walk_owner_dirs()`.

## tracking.json: one path, never created by a write

Follow-up to "Project walk": the scan now ignores a stray `.pipeline/`, but
what *wrote* in the wrong place was still possible. A dozen functions
rebuilt the path by hand as `filepath.parent if filepath.is_file() else
filepath`:

- `is_file()` is a disk call, and it's False for a `.blend` not saved yet
  *or* on a network hiccup -- the `.blend` path itself was then taken for
  the folder, and the write's lock created `ch_ball_v001.blend/.pipeline/`.
- `create_tracking()` always took `.parent`: given a folder, it wrote into
  the prefix folder.
- Writers did `box["data"] or {}`: a write aimed at the wrong folder
  *created* a tracking.json there, with nothing but the new entry -- a
  note that seems lost, and a fake asset for the scan.

Now `tracking_json_path()` is the only way to that path, decided from the
name like `_owner_dir()`. Writers pass `must_exist=True` (raise, checked
before the lock -- so not even an empty `.pipeline/` gets created);
`create_tracking()` is the only one allowed to start a tracking.json, and
like `_meta_path()` it only accepts a `.blend`.

## Production snapshot: one HTML file, a spreadsheet inside it

Production (outside the studio: no Blender, no NAS) needs a picture of the
project at a given moment and a way to send review notes back.
`lib/snapshot.py`, Project panel > "Snapshot".

- **One self-contained HTML file**, CSS/JS inline: sent by mail, opens
  offline. Not Markdown (browsers don't render it), not an XLSX report.
  Zero dependencies by choice -- stdlib only, even though an extension
  could bundle wheels.
- **The review template is an XLSX embedded in the HTML** (`data:` link
  with `download`) rather than an HTML form: a form under `file://` loses
  everything on close (localStorage isn't reliable there), a spreadsheet
  persists and is a tool the prod already uses. Hand-written minimal
  OOXML, cells as `t="inlineStr"` (no sharedStrings to write).
  - One row per asset/shot; `filename` is the most recent version the
    snapshot shows (wip or stable, whichever has the higher number -- a
    stable can be newer than every wip), which the import resolves with
    `find_file_by_name()` and stores as the note's `referenced_version`:
    the note stays anchored on what the prod actually saw.
  - Locked columns through sheet protection *without a password* -- it
    only stops accidental edits. Version columns hidden; `schema_version`
    in a hidden cell, since the format will grow (priority, deadline...).
  - Layout: a merged left column per prefix/sequence (only its top cell
    holds the value -- the import ignores that column), filenames without
    `.blend` (added back on import), type pre-filled `rtk` (a row only
    counts once its text is filled). One font size, weight and grey only;
    grey fill = locked, white = to fill in.
  - Department dropdown per row = that item's `departments_required`
    (inline list, 255-char Excel limit -- skipped past it); type = note/
    todo/rtk.
- **Department state: four values, not two** -- the monitor's own split:
  not started / wip / validated / validated *and worked since*. The last
  one is never shown as plain "validated".
- **Open notes** reuse `filter_review_boxes(hide_done=True)`, not a second
  filter: a done root with a pending reply stays. Notes have no `done`, so
  every note counts as open.
- **Collect / model / render kept apart**: `read_snapshot_raw()` (disk,
  pure os/json, on a thread), `build_snapshot()` (memory, main thread --
  `_status_from_raw()` reaches `ConfigCache` through
  `get_version_number()`, so it can't run on the thread), then
  `write_snapshot()` (render + write, on a thread: the target folder can be
  on the share). Blender only ever waits on the few ms of the middle step.
  Renderers take the plain dict: testable without Blender.
- **Raw source one element per line** (table row, note, section) and the
  embedded XLSX's base64 wrapped at 76 columns: a browser drops a URL's
  newlines, so the link still works, and the file stays readable in an
  editor and diffable between two snapshots.
- **Filters are client-side** (inline vanilla JS, no library): rows and
  note cards carry the same `data-*` (`_item_attrs()`), so one predicate
  filters both and the section counts follow. Department + state match on
  the same department ("animation *is* validated"), not two independent
  conditions. The sticky bar is only sticky from 700 px up -- with its
  filter row it would eat a phone screen.
- Measured on a small real project (2 assets, 18 shots): 0.75 s read on
  the thread, 3 ms on the main thread, 23 KB of HTML.

### Review import, and the CSV entry import it replaced

Project panel / Pipeline menu > "Import review" reads the template
back straight from the .xlsx (`zipfile` + `ElementTree`: sharedStrings or
inline strings, first sheet resolved through the workbook rels -- not
always `sheet1.xml` once a spreadsheet app has re-saved it). No "save as
CSV" step asked of the prod. The CSV entry import (`upload_csv`) is gone:
the template does the same job with the filename locked in. `read_csv()`
stays, for batch creation.

- **One line of a text cell = one entry**: several retakes on the same
  shot are several lines (Alt+Enter), each its own checkbox in Blender --
  same rule as "Batched review input, still one entry each" above. They
  share the import's `review_id`, so they're drawn under one review
  header. A typed bullet (`-`, `*`, `•`, `1.`) is dropped. The price: one
  retake can't span two lines, fine for a retake.
- **Re-importing never duplicates**: a line is skipped when the target
  file already has an entry from a review with the same text and author.
  Covers the same file imported twice and a re-sent file with notes added
  (only the new lines come in). Checked per line rather than by a file
  hash for exactly that second case.
- **`source: "prod_review"`** on every imported entry, absent on one typed
  in Blender: shown in the entry's tooltip and as a tag in the snapshot,
  and what the duplicate check keys on. Author defaults to "prod".
- Review date: a typed date arrives as an Excel serial number
  (`1899-12-30 + days`), or text in a common format; empty = import time.
  `create_entry(created_at=...)` stamps it.
- A row whose file can't be found (renamed, branched, archived since the
  snapshot) is skipped and listed in the end-of-import popup, never
  re-pointed at another version: the note was written about what the prod
  saw, guessing another file would misplace it silently.

### Not done, on purpose

- **Priority / deadline**: not in the review channel. Kitsu/ftrack-level
  production steering is out of scope (and "Status is derived, not a
  dropdown" above applies). `schema_version` leaves room if that changes.

### Thumbnails

`renders/<seq>/<shot>/<seq>_<shot>_thumbnail.jpg`, or
`renders/assets/<prefix>/<asset>/<asset>_thumbnail.jpg` -- named after the
file's base name (a shot folder is only `sh040`, an asset folder already
carries its prefix). Overwritten in place, made by `lib/thumbnails.py` +
`templates/make_thumbnails.py`.

- **Blender, not ffmpeg**: not every machine has ffmpeg, every one has the
  Blender it runs. The frame is loaded, shrunk and saved as JPEG in a
  disposable headless Blender (`--factory-startup`, plain bpy) -- never in
  the artist's session, where image scaling would run on the main thread.
  A float frame (EXR) goes through AgX, a byte one (PNG...) through
  Standard, so neither comes out washed out or double-transformed.
- **Multilayer EXR is the one exception**: Blender loads it as an empty
  image (no layer/pass to read). ffmpeg reads it when told the layer, which
  `exr_layer()` finds in the EXR header (pure Python, prefers a `Combined`
  layer), with `-apply_trc` for linear -> sRGB. Without ffmpeg on that
  machine, that thumbnail isn't made and the export says so: another
  machine that has ffmpeg can fill the gap with its own export.
- **Size**: longest side 240 px by default, any aspect ratio (a 9:16
  render gives 135x240); JPEG q70 -- 2-3 KB on the test project, ~10 KB
  for a busy frame. Shown whole in a fixed box in the HTML (`object-fit:
  contain`), at its own size on hover. The size is the project's
  `thumbnails.size` (Edit project, `thumbnail_size()`). A thumbnail's
  longest side is always exactly the size it was made at, so
  `thumbnail_jobs()` spots one made before the setting changed by its
  JPEG header (`jpeg_size()`, SOF segment) and remakes it at the next
  export -- no sidecar to keep in sync.
- **Which frame**: the middle one of the latest render increment (folder
  name order, same rule as `latest_shot_mp4()`, now `latest_render_dir()`);
  the first is often a hold. Empty placeholder frames are skipped.
- **When**: the farm remakes it at `compilation_finished` (detached
  process, the monitor never waits), and the snapshot export catches up on
  any missing or older than its source frame (file mtimes, nothing
  stored). A thumbnail deleted by mistake comes back at the next export
  from the frames on disk -- no re-render; only deleted frames lose it.
- **Project monitoring > file details** shows it too, through a
  `bpy.utils.previews` collection (`panels/tracking_panel.py`): loaded when
  the file is clicked (the details operator's `execute()`, one stat), keyed
  on the thumbnail's mtime so a remade one shows up -- `draw()` only reads
  the cached icon id. Freed in `unregister()`. A `template_icon` is always
  square and centers a non-square frame in it -- kept as is (the
  thumbnail's own ratio is never altered), sized on the departments list
  next to it and drawn in a box so the centering reads as intended.
- **Blocks**: a block row shows its first shot's thumbnail; every shot still
  gets its own, since the farm renders a block shot by shot.
- **Asset renders** had never worked on the farm: `compute_output_path()`
  took the file's folder relative to `shots/`, a ValueError for anything
  under `assets/` or `library/`, so the job failed at setup -- though the
  render dialog offers "Asset / Library". `render_root()` now sends them to
  `renders/assets/<prefix>/<asset>/` (mirroring the source tree, so asset
  prefixes and sequences never share a level); shots keep
  `renders/<seq>/<shot>/`, which every shot reader depends on.
- **Done %**: per asset/shot, each required department weighs 1/n;
  it counts in thirds, one step per stage: not started 0, work in
  progress 1/3, validated but reworked since -- or with an open RTK
  tagged on that department, outlined red in the table: the RTK is the
  news -- 2/3, validated 1. (Since 1.0.14 the three middle steps are
  `PROGRESS_WEIGHTS`, 33/67/67 %, overridable per project:
  `snapshot.progress`, Project settings > Snapshot done.) Groups and the
  two totals average their items, each weighing the same: a 2-department prop and a 5-department
  character are one item each. Items with no required department are
  left out rather than counted 0 or 100.
- **Closed notes exported, hidden**: the snapshot used to drop closed
  threads (`filter_review_boxes(hide_done=True)`), so the record lost them.
  It exports every thread now; `_thread_closed()` applies the same rule
  and the page hides them (`li.closed`, "Show closed"). Counts, the red
  outline and Done % keep using open threads only.
- **Default folder `snapshots/`**, time in the name: exports used to go
  to the last folder used (possibly another project's) under a name dated
  to the day, so a second export the same day overwrote the first.
- **Review descriptions**: the template's description column used to be
  ignored on import. Now a differing, non-empty cell is a change, shown
  in a confirm dialog and applied all or none -- a per-line selection was
  judged too heavy: a wrong one is fixed in the spreadsheet and the file
  re-imported (notes already imported are skipped). An empty cell never
  clears a description. The template's description column, locked while
  it was ignored, is an input cell now. The first version compared the
  cell with the *current* description: an old template re-imported (or
  one sent back late) reverted every description changed since. The
  template now carries `description_exported` (hidden, schema 2): only a
  cell differing from it is the prod's edit. A schema-1 template has no
  such column and its descriptions are ignored -- they were locked then.
- **Last render** (`read_render_state()`, also File details' "Last
  render"): from render_history.json's last finished entry with a
  `source_file` (1.0.11+), else from the latest render folder's name. An
  older entry (no `source_file`, no `shot_override`) coming *after* that
  one makes the history untrustworthy: a farm still on an older version
  may have rendered the shot again since, and its entry can't say which
  shot or which file -- the folder name is used then. Mixed histories are
  real: a dev build on part of the machines, or a farm updated mid-project.

<!-- Next feature with rationale worth keeping gets its own "## " section
     here, same shape as the ones above: what was tried, what was
     rejected and why, anything a docstring is too short to hold. -->

## Stopping a worker: after this frame, or now

"Let it finish" let the render subprocess run to its end -- and a render
walks the whole range, taking every frame still free: on a long shot,
hours before a workstation was given back. Two ways now:

- **After this frame** (`stop_worker(kill_render=False)`): the worker
  writes `request_<job>_<uuid>.stop` (`render_stop_path()`); the render
  entry checks it before each frame, releases its claim and exits 0 --
  that machine is done, not failed.
- **Stop now** (also quitting Blender, switching project, a machine's
  Cancel): killed, reported "stopped" (neutral). The frame it was on was
  never under its final name (written to a `.tmp`, then renamed): nothing
  to clean up; its claim is freed by the host.

The flag is deleted when the render ends (`_clear_render_flags()`), and by
`discard_saved_frames()` if a crash left it.

## Which machine rendered which frame

`_note_frames()` turns the `.saved` records into `frame_machines`: one
letter per frame of the range ("." unknown), and the letters' machines
(uuid, name). Frames interleave between machines (each takes the next
free one: A 923, B 924, C 925, A 926... -- before chunks), so
per-machine ranges barely collapsed -- ~7 KB for 1443 frames on 3
machines, against 1.5 KB for the letters. Unreadable by eye: the *Frame* field
(`draw_frame_lookup()`) reads it, in the job's detail and in File
details' last render (`read_render_state()` hands it over from the
history -- there once the job is archived). A frame written in several
rounds goes to this round's machine, else the latest line's. Names from
the worker files when judged, else the record before (a worker removed
since).

The field used to start at 0 and accept anything, answering "1001 -
1443" until a frame in range was typed: it's now held to the render's
range (`farm_frame_lookup`'s get/set clamp to bounds `draw_frame_lookup()`
sets, a block's shots together), so it always shows a frame and its
answer -- the machine, the frames around it that machine wrote in a row
(its chunk, or several: `_same_machine_run()`), its pace -- three greyed
lines under the field: a debugging aid, not something read every day.
Paces under a minute read in seconds (`_pace()`: "0.6 s", not "0m00s").

## Time left: per machine, from each frame's time

The popup's estimate was `elapsed / progress - elapsed`, elapsed counted
from the last `render_start`. Right while the job keeps the machines it
started with, wrong otherwise: a third machine joining halfway still
counted the first half's pace; one leaving, the same. And after a refill
(a new `render_start`) the frames already there made the progress jump,
the time left near zero.

The `.saved` record each machine keeps now
carries the time of each write, on that machine's clock:
`"<dispatch_id> <frame> <time>"`. Two lines in a row of one render are
one frame's time -- skipping frames already taken costs nothing, and the
first frame of a render (it includes opening the .blend) has no
predecessor. One clock per file: no worry about machines' clocks
disagreeing, nor about the share's file times.

Time left = frames still to render (no file, or empty) / the summed pace
of the machines rendering the job *now* (worker files: "render" on this
`job_id`), each at the mean of its last `_PACE_FRAMES` (10) frames --
every machine goes through the range in order, so its next frames look
like its last, and a heavy stretch of the shot shows up within ten
frames. A machine that just joined, nothing timed yet, counts at the
job's average. None of it (first frames, workers not updated): back to
the old formula.

Read by the popup's reader thread (`_frame_seconds_for_jobs()`), for the
jobs at `render_start` only, each record parsed again only once its mtime
or size changed: a line per frame, a few dozen KB for a long shot. When
the render is judged, the monitor stores each machine's mean
(`machine_seconds`) and the job's (`seconds_per_frame`) in the job file
(`_note_frames()`, every round's lines, every machine's file);
the render history keeps `seconds_per_frame`.

Not done: counting the frame each machine has in progress (its share of
it is done already). It needs "now" on the worker's clock -- one frame of
error at most, on the high side.

---

## Monitoring popups: reopening on the detail, or not

Symptom: Project monitoring sometimes reopened on the file detail it was
closed on, sometimes on the list -- the file staying open all along;
Farm monitoring always reset to its list on open.

The one thing that ever cleared the detail was its own operator, a
toggle: `tracking_file_details` with the file already shown went back to
the list. Two ways to hit it without meaning to:
- a "Links to" / "Linked by" row naming the folder already shown;
- the Back button, which sets no `filepath`: an operator property not
  set by its button takes its *last used* value (Blender's remembered
  operator properties, unless `SKIP_SAVE`), so Back carried whatever
  was clicked last -- the tooltip too (`custom_tooltip`).
Now never a toggle: no `filepath` (Back) = the list, a `filepath` = that
file; both properties `SKIP_SAVE`. Same for `farm_job_details` (no
`job_id` = the list).

The detail moved off the WindowManager as well, into memory
(`monitoring_detail()` / `set_monitoring_detail()`, `lib/core.py`) -- not
confirmed as a cause (the first guess, "the WindowManager is saved in
the .blend", doesn't match a reset with the file open), but nothing of
Blender's (file load, `read_homefile()`, undo) can touch it there. OK
keeps the detail for next time, re-read by `invoke()` (a file's
thumbnail and last renders, a job's file -- gone: the list); Cancel or
Escape (`cancel()`) clears it.

## Action popups: dialogs

`M_PIPELINE_OT_action_popup` used `invoke_popup()`, chosen because it adds no footer of its own (`draw()` already draws every choice as a button). But a popup closes as soon as the mouse leaves it -- the append/link warning, among others, vanished before artists even read it. It's now an `invoke_props_dialog()`: it stays open until a button, Escape, or the footer.

The footer can't be removed from a dialog, so it's made harmless: `confirm_text="Close"` plus the native Cancel, both just close it (execute with `choice_index == -1` / `cancel()`), and `cancel_default=True` so Enter never triggers anything. The first choice can't be wired to the confirm button instead: it isn't always the neutral one (the stable-file save guard's first choice is "Save"). So an action has no "Cancel" choice of its own: it showed three ways to cancel (the save guards, the stop-worker and FFmpeg warnings) -- its `on_dismiss` is what Cancel does.

Closing without choosing runs the action's `on_dismiss`, once -- `PipelineAction.resolved` is set as soon as a choice runs, so the dialog closing right after a choice doesn't also dismiss it. The "External project Link done ?" warning now has an `on_dismiss` equal to its "Ignore" (record the link in the `.wipmeta`): before, a popup lost to the mouse silently skipped that record.

---

## Addon register()

`register()` defers its UI work to timers (one tick or a fraction of a second later): `refresh_read_only_flag`, `refresh_monitor_cache`, `_deferred_keymap`, `_deferred_project_check`, `_deferred_auto_worker` and `_deferred_onboarding` (last, so its popup opens over everything else), plus two persistent ones -- the farm status timer (`register_status_timer()`, the sidebar header) and the session `heartbeat_30s` (registered by `register_handlers()`).

None of them is registered in background mode (`bpy.app.background`): the farm's setup/render subprocesses and the CSV batch rows load the addon too, and have no UI, keymap, session or lock to keep alive -- a background process's liveness is tracked by PID by whoever launched it. `blender -b ... --python` never runs timers anyway, but Blender loaded as a Python module (`bpy`) waited on the pending ones at exit: 25 s on 4.2/5.0, forever on 4.5, 3 s once they're gone.

## Project monitoring's Farm column: the monitor cache, not the project scan

The column needs to know which files have a job queued or rendering. Not
read per file: `farm_activity()` groups the farm monitor's cache (the
jobs the Farm popup lists, already in memory) by owner folder, keyed by
`owner_key()` -- the same `_owner_dir()` rule `mark_render_to_check()`
uses to find a job's tracking.json, normalised so a job's relative
`filepath` joined on the root matches a `TrackingStatusCache` key. So
`ProjectScan` costs the same as before, whatever the farm does.

That cache is only kept fresh while the Farm popup is open. Project
monitoring and the snapshot export call `request_monitor_refresh()`
instead: the same threaded read, once, applied by a timer that stops
itself. It keeps no popup region (see "Project walk"): Project monitoring
shows the result on its next redraw, like `ProjectScan`'s. The snapshot
starts it with its own scan, which takes longer, so it's in by the time
`build_snapshot()` runs; if not, the snapshot uses what the cache had.

## Snapshot width: short state labels, hideable columns

Six departments of full-label pills ("Validated, reworked since", "Work in
progress", nowrap) plus thumbnail, versions, last render and Done no longer
fit the 1200 px page: the table scrolled sideways. The page is 1600 px
(`--page`), the table 13 px, and a cell shows `SHORT_STATES` -- the full
label stays in its tooltip and in the legend. The *Columns* menu hides any
column but the name: every cell carries `data-col`, the menu's checkboxes a
matching `data-key` (not `data-col`, or hiding a column hid its own
checkbox), and the script writes one `display:none` rule per hidden key
into a `<style>` -- no per-cell work on toggle. The choice is per browser
(localStorage, try/catch: a page opened from a mail attachment may have
none), never in the file: the prod's view is their own.


## What a real project's export showed (6 machines, a week of production)

An export of a production project (config/, sidecars, logs -- no frames)
cross-checked against the code. Each item below names its evidence.

- **A block's shots**: `owner_render_dir()` stands for a block with its
  first shot; the snapshot also shows every shot's own
  (`owner_shot_render_dirs()`: sh010-020-040 -> sh010, sh020, sh040, a
  render folder each -- the farm already thumbnails each shot it
  renders), as a small button per shot under the block's thumbnail
  (`_shot_buttons()`: its number; greyed, no image, for one not rendered
  yet) -- a strip of images took a row's height for an 8-shot block. On
  hover, one shared `#sbpop` image (`_JS`), `position: fixed` beside the
  button, above it when there's no room below: inside a table's
  horizontal scroll box an absolute one was clipped. Made in the same
  headless Blender pass as the rest (`read_snapshot_data()`'s
  `shot_thumbs`); the Columns menu's Thumbnail hides the buttons too.

### Render preset: read without a lock, fail the render

Some workers rendered with the burn-in a preset turns off (and at full
resolution, the preset's 50 % skipped). `worker_render_entry.py` called
`apply_custom_preset()` without the job, which then read it under
`locked_json()` -- a write lock, 1 s of retries. All of a job's machines
start at the same tick and reach that read together, while the monitor
locked every job file every tick too: the losers got "...job_xxx.json is
locked by another process", caught and logged as a warning, and rendered
with the .blend's own settings (15 times in the log, 3 machines out of 6
on one job). `-F JPEG` on the command line kept the extension right, so
nothing downstream noticed.

Now: the job is read with `read_json_quiet()` (writes are atomic, a few
retries for a Windows mid-replace), and the render passes `strict=True`:
a preset that can't be applied raises, `--python-exit-code 1` ends
Blender before it renders, the worker reports a failure. The setup stays
lenient (it only reads what the render will produce).

### Frame check: naming the corrupted frames

- the frame check (`checks_images()`) names the frames it finds
  corrupted, not just a count of error lines: `-loglevel level+info`
  (ffmpeg 4.3+), `-threads 1`, `-vf showinfo`. Decoding single-threaded,
  every decoder error lands right before the showinfo line of its frame,
  whose `pts` is the frame's index in the sequence (not `n`, which restarts
  when the filter graph is rebuilt); a frame ffmpeg can't decode at all
  has no line -- a gap in pts -- and the errors before the frame after a
  gap count for both (one frame re-rendered for nothing beats a corrupted
  one kept). Only the decoder's and input's lines count: a format change
  mid-sequence rebuilds the graph with `swscaler` warnings that say
  nothing about a frame's data (`_NOT_INPUT`). An unreadable log tells
  nothing: no frame blamed. Checked with ffmpeg 6.1 on spliced,
  interleaved, truncated and garbage JPEGs and a truncated PNG: all named,
  a clean 60-frame sequence nothing (`corrupted_frames()`);
- when that check ends, `_send_back_bad_frames()`: the corrupted frames
  are deleted, recorded (`frames_rerendered`, job then
  render_history.json), and the job goes from the frame check back to
  `setup_finished`, then rendered, checked again, compiled -- not once
  `MAX_FRAME_CHECK_ROUNDS` is spent (kept, named in a warning).

### Quitting Blender while its worker renders

`unregister()` (called on quit) and a project switch called `kill_worker()`,
which only deletes the worker file: the render subprocess outlives its
parent on Windows. The monitor took the gone worker for lost and, once the
others were done, deleted the empty placeholder of the frame the orphan
was rendering and sent the job out again -- the same frames rendered
twice. Both now call `stop_worker(kill_render=True)`: the render is
killed and reported "stopped" (neutral), the file is kept. And in
`unregister()` the farm block now runs first: it ran after
`unregister_class()`, when the addon's preferences -- the active project,
this machine's id -- were already gone, so `is_blender_worker()` said
False and nothing was ever stopped on quit, `kill_worker()` included.

### Monitor tick: read without a lock, decide once

The log was 99.3 % "No idle machine for job X, will retry." -- one line
per waiting job per tick, 362 683 lines, a rotation every few hours, the
Pipeline log popup showing nothing else. Behind it, every tick:
`scan_queue()` locked every job file of `actives/` (archived ones
included), `render_dispatch()` locked each waiting job, then
`scan_render_requests()` locked every request -- before even knowing
whether a machine was free. Side effects: the "Could not read job file ...
locked" errors, the preset failures above, and a `.lock` created/deleted
in `actives/` every tick, which changed its mtime and defeated the UI's
`_scanned_mtimes()` cache. `scan_render_requests()` also returned `None`
for a request taken between its glob and its read ("'NoneType' object is
not subscriptable").

Now `read_active_jobs()` reads without a lock (whoever acts re-reads under
its own), skips archived/orphaned jobs without reading them again while
their file is unchanged, `idle_machines()` is computed once per tick and
handed out (`render_dispatch()` takes its machines out of it), a job with
no machine for it is noted once (`note_waiting()`), and
`check_render_completion()` takes the job's lock only once every frame is
on disk. `render_dispatch()` re-checks the stage under
its lock and fails a job whose `.blend` is gone (a block's old -stable
replaced by a newer version had been retried onto 6 machines, all failing
on "Cannot read file"); `retry_job()` refuses it.

Priority sorted ascending (comment: "descending"; docs: "highest
first"): a p50 job sat in `queued` for 20 h behind later p10 ones. Now
`-priority`.

The farm host was both monitor and worker: a setup waits for
`local_render_running()`, so it ran only in the gap between two of its own
renders -- one setup per render of hours. While a job waits for its
setup, `scan_queue()` now keeps this instance's own worker out of the idle
machines.

Job ids hashed `Path(filepath).resolve()`: `S:\...` on the file server,
`\\host\share\...` elsewhere -- a different id per machine, so a split on
the farm host and a resubmit from a workstation never deduped. Now the
project-relative path (the split passes the stored one). Previews stored
their label absolute; now relative.

A block with fewer than two markers bound to a `cam_<seq>_<shot>` camera
rendered whole into its own render folder with its `skipped_shots`
dropped -- three of them in the export. Still rendered whole (never
block), but the job now carries `skipped_shots`/`absorbed_shots`, a farm
warning names them, and `construct_history()` keeps them.

### Farm logs: kept small

`queue/archives/` held 145 MB after four days, `requests/` 45 MB: a failed
or stopped render keeps its log, up to 36 MB / 271 000 lines, 99 % Blender
progress ("Fra:... Building BVH 45%") and a rig's "Dependency cycle
detected" blocks. `compact_log()` drops the "Fra:" lines but the last 20,
then keeps the first 32 KB and the end up to 256 KB. It runs in `archive()`
and in the monitor's hourly `farm_housekeeping()` (on the farm host, local
disk) for the big logs of jobs already over -- never one a worker may
still write. The same housekeeping archives jobs that ended well more than
`farm.auto_archive_hours` (24) ago -- failed ones stay for someone to look
at -- and deletes archived logs older than `farm.archive_log_days` (14).
Job files are kept: a few KB, and `render_history.json` has the outcome.

### Linked libraries: one line per file

One shot's `.wipmeta` listed 2 042 links for 7 files (1 398 for one anim
library), 370 KB; 51 766 entries over the project's 183 metas, copied into
every new version and read by `ProjectScan`. The list held one
`{file, type, name}` per linked datablock, and the scan added the
reference of every override -- overriding a rig makes each of its objects
(every widget) an override. Yet everything that reads the list only needs
the file: "Linked by", the library update check (which reads
`bpy.data.libraries` anyway), `clean_libraries()`, the File details "Links
to" (grouped by folder). So it's now one `{"file"}` per linked file:
`scan_linked_libraries()` lists the direct project libraries
(`bpy.data.libraries`, `parent is None`) -- no more root detection -- and
`compact_linked()`, applied by every writer of the list and by
`get_linked_libraries()` on read, turns an older list into its files
(`../` collapsed, compared normcased). An existing `.wipmeta` is rewritten
on its next load/save (`wipmeta_sync_links()`, logged "compacted"); an old
`.stablemeta` is never rewritten, but reads compact. File details: a folder
with more than one entry now means several versions of that asset linked.

### Shared logs and JSON: project-relative paths

Besides the job ids and preview labels above: `worker_*.json`'s
`current_job` held the request's absolute path (now its name), and every
`session_end` line of `sessions_log.jsonl` (428 of 428) the writer's own
`S:\...`. It worked because every machine here mounts `S:`; a machine on
`\\host\share` would have had its work time and recent files keyed on
another path. `_log_session_end()` now stores `to_relative()`;
`WorkTimeCache`/`RecentFilesCache` key on `_session_folder_key()` (the
folder made project-relative -- an old absolute line under this machine's
root still counts), and the recent files open `project_path()` of it. The
`.session_<pid>.json` file itself stays absolute: it's this machine's own,
compared with `bpy.data.filepath`.

## Monitoring crash: a thread during window_new()

Reported on Windows, Blender 4.5.2: Blender closing on opening Project
monitoring, `EXCEPTION_ACCESS_VIOLATION` in `python311.dll`. The crashing
thread was ours, `ProjectScan`'s walk (`_walk_owner_dirs()`,
`sorted(os.scandir())` -- pure Python, NULL read in Python's allocator);
the main thread was inside `pyop_call`, waiting to take the GIL back
after a `bpy.ops` call from the opening operator. `bpy.ops` releases the
GIL for the operator's length (`BPY_RELEASE_GIL`), and the operator was
`wm.window_new()` -- started right after `ProjectScan.start()`. Pure
Python can't fault on its own: something in that call touched Python's
memory without the GIL while our thread allocated.

A second report pinned it: the crash on the *main* thread this time,
in `bring_monitoring_to_front()`'s `wm.window_close()` (run under
`context.temp_override(window=...)`): `pyop_call` (GIL released) ->
`wm_window_close` -> `ED_screen_exit` -> `ctx_wm_python_context_get` ->
`BPY_context_member_get` -> `PyDict_GetItemString` -> `PyUnicode_New`.
Blender reads the temp_override's context dict -- builds a Python string
-- without holding the GIL, while one of our readers was mid-file-open on
its thread. Blender's bug (a Python allocation outside the GIL), ours to
stop exposing: no reader thread runs Python while a window opens, closes
or a file loads. Every `temp_override()` + `bpy.ops` of the addon is in
`lib/monitoring.py`, all paused.

`lib/background.py`: `threads_paused()` around those `bpy.ops` calls
(`window_new`, `region_toggle` in the new window, `area_dupli`,
`window_close`, `open_mainfile`); every reader thread runs in
`background_work()` and passes `checkpoint()`s -- a folder listed
(`_walk_owner_dirs()`), an owner read, a file read (`read_json_quiet()`)
-- where it waits out a pause. The main thread waits until every one is
parked or done, `PAUSE_TIMEOUT` (2 s) at most: one listing on a slow
share; past it, the operator runs anyway rather than Blender freezing.
`checkpoint()` is a no-op on the main thread (it's the one pausing, and
draws run there during the operator) and costs one read when nothing is
paused. Threads: `ProjectScan`, the farm readers (`_BackgroundRead`), the
snapshot export, the log read. And the opening operators start their
reader *after* the window (`tracking_monitor`, `pipeline_logs`): one
started just before is still in its first listing, the pause would wait
for it.

Other `bpy.ops` calls (saving, popups) aren't paused: none crashed, and
none rebuilds windows. Checked headless: readers frozen during a pause,
resumed after, a nested pause (`bring_monitoring_to_front()` opening a
window), a reader stuck past the timeout. Not reproducible here -- the
crash needs Blender.

## Monitoring: windows, not popups

Project monitoring first, then Farm monitoring the same way: the screen's
ID property says which (`"project"` / `"farm"`; `True`, from the first
version, reads as `"project"`), each panel polls its own. Tried, then
dropped: a header ("Pipeline: ..." -- a collapsible box like Options and
Workspace): a panel with a header is placed after the Tool tab's own, and
`bl_order` can't go below 0. Headerless again, the content in a
`layout.box()`, first in the tab.

**Child windows follow the main one's workspace.** A window opened by
`window_new()` is the main window's child: when the main window switches
workspace (a tab click), Blender switches its children too (only temporary
screens are spared), each onto a new layout -- without the screen's ID
property: the monitoring window went blank. Each one's kind is kept by
window pointer (`_window_kinds`) and `monitoring_windows()` marks its
screen again. Checked: switch to Modeling, both windows keep their content.
Also learned there: `window.workspace = ...` from a timer (no window in
context) switches *every* window; setting a space's property from a timer
without a window in context crashed Blender (4.0) -- `_show_tool_tab()`
works in its window's context.

**Machines named by their user.** A machine is only ever known by its id
(a slice of the prefs' `machine_id` -- no hostname read), meaningless to
people. `_machine_name()` (render end) records "user (id)" from its
worker file, into `frame_machines` and `machine_names` (every machine of
the job, failed ones included), both kept in the job and its render
history: still readable once the worker is gone, or after the id changed
(prefs reset). `machine_label()` prefers the live worker, then the
recorded name, then the id.

**Workspaces: not added.** A "Project" / "Farm" workspace each was built
(a duplicate of the active one, its areas closed but one) and works, but a
workspace belongs to the .blend, not to Blender: every file would need it
added, and the files opened with their own UI wouldn't have it. The window
is enough.

Farm monitoring's
refresh (`_refresh_tick`, every 2 s, was the popup's) runs while its
window is open: `_monitoring_tick` starts it, and again after a file load
(`post_load_handler()` stops it), and stops it with the last window.


The popup had grown heavy: 12 rows a page, a pager, a fixed height padded
with blank rows so it didn't jump around, and it closed as soon as you
clicked outside it. `m_pipeline.tracking_monitor` now opens a window
holding one Properties editor; `M_PIPELINE_PT_monitoring` draws in it.
Checked in Blender (4.0, under Xvfb):

- **The window**: `bpy.ops.wm.window_new()` opens a normal window (95 % x
  90 % of the main one, its child) with a single area of the main window's
  biggest editor type; the area becomes `PROPERTIES`. Its header (the
  search field, which would filter the table's labels) is hidden, and so
  is the tab column (`screen.region_toggle(region_type="NAVIGATION_BAR")`).
  A window's position and size are read-only from Python, and nothing
  raises a window: clicking the button again while it's open only says so.
- **The Tool tab**: the editor's tabs only exist once it has been drawn --
  setting `space.context = "TOOL"` right away raises (`enum "TOOL" not
  found in ()`); a timer retries until it takes.
- **Getting in**: an addon can't add a Properties tab; the Tool tab draws
  the 3D View sidebar's `bl_category = "Tool"` panels. `poll()` keeps ours
  to the monitoring window (an ID property on its screen,
  `MONITORING_SCREEN_KEY` -- a screen is an ID, a window isn't), never the
  N panel or another Properties editor. `HIDE_HEADER` puts it first: a
  headerless panel goes before panels with a header (first version; now
  with a header, see above), but after Blender's own headerless active tool (`VIEW3D_PT_active_tool_duplicate`, same
  `bl_order` 0 -- `bl_order` can't go below 0; hidden in these windows
  since, see "Monitoring windows: pages sized on the window"). Blender's
  Tool panels (Options, Workspace, a mode's brushes) stay below the list,
  pushed out of sight: no API folds another panel.
- **Redraws**: a click on a button in the window rebuilds it like in the
  popup (checked); what changes in the background doesn't -- a popup
  redrew on every mouse move, a region doesn't. `_monitoring_tick` redraws
  when the scan or the Farm column changed, looking the windows up again
  every tick (see "Project walk": a kept region crashes once freed).
- **File loads**: with Load UI (Blender's default), opening a file closes
  every window the file doesn't have -- the monitoring window at every
  file opened from it. `open_mainfile()` (Open file, recent files, the
  window's open buttons) passes `load_ui=False` while it's open: checked,
  the window stays, size, place and scroll included. The price: those
  files open in the current interface layout, not their own. Blender's
  File > Open isn't ours and still closes it.
- **Saved with the .blend**: a file saved with the window open has it
  (Load UI brings it back, with its screen's ID property: the panel shows,
  and starts the scan and the tick itself). Each window also leaves a
  workspace layout behind once closed ("temp", "temp.001"...): `window_new`
  screens aren't temporary, so closing doesn't delete them, and Python
  can't delete a layout -- Blender's own Window > New Window does the same.
- **Filters**: `WindowManager.pipeline_monitoring`, each property a
  get/set on a module dict (`memory_prop()` / `memory_enum()`) -- drawable with `layout.prop()`, never stored
  in the .blend (a WindowManager property is saved with it; see "The
  detail moved off the WindowManager"). An enum's get/set deal in item values (an
  item's own number when it has one -- the departments' 1, 2, 4... --,
  else its index): kept by identifier, so prefixes or sequences changing
  keep the choice.
  The search is cleared when the window opens, as before.

## Monitoring windows: to the front

Clicking Monitoring with its window already open said so and did nothing:
the window was usually behind the main one. Blender has no way to raise a
window -- `Window` has no method for it, its `x`/`y` are read-only, the
`wm` operators are `window_new`/`window_close`/`window_fullscreen_toggle`
(checked on 5.2). `bring_monitoring_to_front()`:

- Windows: the system's own `SetForegroundWindow()` (ctypes), on the
  native window of this process whose client area is the monitoring
  window's size, its x breaking a tie (Project and Farm monitoring alike).
  This process is the foreground one -- the click came from it --, so
  Windows allows it. It stays where it is: a second screen included.
- Elsewhere (Linux, macOS -- Wayland forbids raising a window anyway), or
  if that failed: a new window opened, in front, then the old one closed
  -- the new one first, so nothing the operator runs in is closed under
  it. Same content (filters, page, detail are memory, not the window's).
  `window_new()` opens at Blender's default place and size, and nothing
  sets either afterwards: the new one is `screen.area_dupli` of the old
  one's editor ("Duplicate Area into New Window"), which opens over that
  area at its size (`_duplicate_window()`); `window_new()` only if that
  fails. Checked on Linux: back in front, same place, same size.

Not checked yet: the Windows path (needs Windows) -- if it fails there,
the duplicate takes over.

## Monitoring windows: pages sized on the window

Moving Project monitoring into a window dropped its pages for one list
the region scrolls. The scroll works, but the footer (refresh, file
count, Farm legend) went below the fold as soon as the list was longer
than the window -- and a Properties editor's region can't pin anything to
its bottom. Pages are back, sized on the window instead of a fixed 12:
`rows_that_fit()` divides `context.region.height` (draw() runs on every
resize, so pages follow it) less what the window holds besides the rows
(`_TABLE_RESERVED_UNITS` / `_JOBS_RESERVED_UNITS`: filters, header,
footer, margins) by one row's height, padded with blank rows so the
footer sits at the bottom. Never under `MIN_ROWS`: a window too small for
that scrolls, like before.

- **Row height is estimated, not read**: Python gets neither a layout's
  height nor a panel's. A row is a widget line (20 px x
  `preferences.system.ui_scale`, 0 in background) plus the box's item
  spacing and the 0.5 LINE separator under it. First guessed at 1.35
  widget units: a full-screen window overflowed by about 9 rows, a
  half-screen one by 5 -- an error growing with the height (the row) plus
  a fixed one (the active tool, below). Both points fit a row of 1.6-1.7
  units; at 1.65, with the active tool hidden, full screen still
  overflowed by 2-3 rows, still a little at 1.8: `ROW_UNITS` = 1.9, the
  reserved figures 7 / 8 (6.5 / 7.5 once the panel's outer box went),
  a small gap rather than an overflow. A row's worth (`ROW_UNITS`) was
  added to each reserved figure, then taken back: the row it saved fit
  after all, with room below even resized -- 6.5 / 7.5, 5.0 for the
  Workers view; the Pipeline log 7.4 (its lines are about 1 unit).
- **The preferences' page keys**: four share `m_pipeline.monitoring_page`;
  Previous / Next page were found by `{"step": ±1}` alone, which First /
  Last page (`to_end`) match too -- the list showed Ctrl+arrow on all
  four. Their properties now spell out `to_end: False`.
- **The pager's label**: left to Blender, "Page 2 / 5" got a width far
  over its text, left-aligned in it -- a gap before the right arrow. Its
  row is sized on the text (`ui_units_x`, 0.35 a character + 0.6) and
  centred: what an estimate gets wrong splits on both sides. Every file row is one line high (no
  wrapping in the cells), so one constant holds -- recalibrate it (or a
  reserved figure) if a page overflows the window or leaves a gap, never
  per call site.
- **Blender's active tool heads the Tool tab** ("Select Box" and its
  settings, `VIEW3D_PT_active_tool_duplicate`), above the monitoring
  panel, its height depending on the tool. `hide_active_tool_in_monitoring()`
  wraps that panel's Python `poll()` (read by name at each draw) to say no
  in a monitoring window, everywhere else as before; `restore_active_tool()`
  puts the original classmethod back on unregister. Nothing happens if a
  later Blender renames the panel or drops its poll().
- **Options and Workspace stay**, below the panel: they have no poll() to
  wrap (one Options class per mode, more panels in the paint modes) --
  hiding them means re-registering Blender's classes. Pushed out of
  sight instead: a window's height of blank under the panel's content.
- **The page lives in memory** (`_pages`, lib/monitoring.py), like the
  filters: a WindowManager property would be saved into the .blend.
  `paginate()` clamps it to the page count (a bigger window, fewer pages),
  keeps that count for `turn_page()`, and goes back to page 1 when the
  filters it was counted for change. Turned by arrows, not a number
  field: `m_pipeline.monitoring_page`, -1 / +1, Ctrl+click to the first /
  last, never past either end.
- **Keys** (`register_monitoring_keymap()`, installed with the Ctrl+S
  override once the addon keyconfig exists): Left / Right turn the page
  (Ctrl: first / last), Tab switches assets / shots or jobs / workers, Esc
  goes back from a detail -- a window, not a popup, so Esc closes nothing.
  The operators' poll() keeps them to a monitoring window's list (or
  detail): anywhere else the event falls through. First put in the
  Properties editor's keymap: Esc worked, the arrows never did -- a
  region runs its default keymaps ("Frames": Left / Right step the frame,
  Ctrl: time jump) before its editor's own. The arrows are in "Frames"
  now, where an addon's item wins over Blender's (as the Ctrl+S override
  does in "Window"); outside a monitoring list they still step the frame.
  Tab and Esc stay in "Property Editor" (nothing ahead binds them). The
  addon preferences list them, editable (`draw_addon_keys()`,
  `rna_keymap_ui` on the user keyconfig: saved like any shortcut).
- **Mouse wheel**: left to the region's own scroll (a window under
  `MIN_ROWS`), not mapped to pages.

## Stuck frame

A render hung on one frame (seen: 2 frames left, the first never ending)
held its machine and the job forever: its heartbeat went on, so nothing
looked wrong. The worker now watches its own renders
(`check_stuck_renders()`, every 30 s): when the frame in progress has
taken `farm.stuck_frame_factor` (Edit project, default 5, 0 = off) times
its usual time -- 5 min at least -- it kills the render and reports
`last_job_result.stuck`. Times from the worker's
own `.saved` record and clock (`time.time()` on both ends): never one
machine's clock against another's. The usual time: this render's frames
so far, else the machine's on this job (`machine_seconds`), else the
job's; the first frame of a render also gets the machine's usual startup
(scene sync). Unknown (a first render with nothing timed yet): no check.

On the host, a stuck machine goes to `failed_machines` but doesn't fail
the job: recorded in `stuck_frames` for Job details, its claim freed, the
chunk counted as failed on it (`chunk_failures`); a chunk that fails on
`MAX_CHUNK_ATTEMPTS` machines fails the job (see "Farm 1.1.0: chunks
replace placeholders"). The frame's name comes from the machine's claim
(`_frame_in_progress()`); its times still from the `.saved`, the same
worker's clock.

Rejected: the host killing it -- the host only sees the share's file times
and other machines' clocks, and would need a new kill channel when the
worker already has its process at hand.
## Addon settings lost on update

Same root cause as `user_name` above: Blender's storage of an addon's
preferences goes with its `Addon` entry, rebuilt on every disable/enable --
each extension update -- unless "Save Preferences" ran in between. The
projects list and `user_name` already rode in `pipeline_backup.json`; the
other settings didn't, so "Advanced" fell back to "Beginner" after every
update (and Auto-launch worker, Always read-only, FFmpeg path, Silent
auto-increment, the onboarding flag with it).

They're now in that backup too (`ADDON_SETTINGS`, `lib/session.py`),
written by their `update` callback on every change (`save_settings()`) --
so, unlike `user_name`'s fallback-only restore, the backup is the latest
and `load_project_data()` restores them over whatever Blender kept.
`_restoring` keeps those setattr()s from writing the backup while it's
read. A backup from before has no `settings`: values left as they are.

## Farm 1.1.0: chunks replace placeholders

### Why

Every worker used to get the job's whole range and let Blender arbitrate
(`use_placeholder` + `use_overwrite=False`): a frame was taken by writing
its empty output file. That token was anonymous (whose, since when?),
mistaken for a result (empty: in progress, or abandoned?), and only ever
expired by guessing. Fine on one fast server; with several workers and a
Windows share's latency, most of 1.0.x's farm fixes came from it:
placeholders to clean up, frames written twice, a render stuck at 100 %
or at render_start, `NOBODY_SECONDS`, refill rounds, joins weighed frame
by frame.

Frames written twice were the worst: Blender's placeholder is "exists?"
then "touch", not atomic, and an SMB client's caches widen the window;
Blender writes straight onto the final name, so two writes at once give a
spliced file -- valid header and markers, readable, then bands of the same
detail with shifted colours (JPEG's DC coefficients are differences from
the previous block). `ffmpeg -v error` saw nothing. 1.0.x caught them
afterwards (`.saved` records compared, then re-rendered on one machine)
and rejected claiming each frame atomically, as that meant replacing
Blender's animation loop.

That's the decision reversed: the render entry runs its own loop over
chunks of frames, each claimed with an exclusive create (`open(path,
"x")`, atomic on the share), frames written to a `.tmp` then renamed -- a
frame under its final name is whole, so the disk says what's done. The
pull model stays: a worker takes the next free chunk, so workers can join
any time; only the token changes. Design: `farm-chunks-plan.md` (outside
the repo).

### Removed, kept

Removed (`main` before 1.1.0, `57ddce6`, has them): `join_running_renders()`
with `_joiners_wanted()`, `_render_timing()`, `_on_it()`,
`JOIN_MIN_FRAMES_LEFT`; `render_mode_auto()` and
`last_render_had_collision()` (no collision left to fall back from);
`_machines_on()` and `NOBODY_SECONDS`; the refill rounds
(`MAX_REFILL_ROUNDS`, `refill_single`) and `_reassign_away_from_failed()`;
`_delete_placeholders()`; `frames_written_twice()`;
`render_frame_path()` / `_free_frame_in_progress()` and the render
entry's `render_pre` / `render_write` handlers (`note_frame`,
`stop_if_asked`: the loop calls them directly).

Kept, still true with chunks:

- a machine's file read directly (`_read_worker()`), never through
  `scan_workers()`: the heartbeat is written every 10 s *after* the
  previous tick, so a slow tick puts a live worker past
  `STALE_WORKER_SECONDS`, and its published result was ignored;
- `last_job_result` is one slot, overwritten by the machine's next
  render: matched to a render by its `dispatch_id` (`_failed_this_render()`
  -- a re-render reuses the job id, see "Re-rendering a file"), never
  taken as proof the machine is still on it;
- the job's Cancel is a flag on the job (`cancel_requested`), not read off
  the machines' results; a Retry clears it;
- a request a worker hasn't taken up yet is withdrawn under its lock
  (`_withdraw_requests()`): on Cancel, and when nothing is left to render;
  `execute_render_request()` never launches a request gone between its
  scan and its lock;
- the frame check still deletes the corrupted frames and sends the job
  back (`_send_back_bad_frames()`, now bounded by
  `MAX_FRAME_CHECK_ROUNDS` -- the refill rounds' count was shared with it).

### Claims

Claims (`farm/chunks.py`): `queue/claims/<job_id>/claim_<k>.json`, a
folder per job -- the host lists one job's claims in one `scandir` (not
the whole of `requests/`, its `.saved`, `.log`, `.stop` files) and drops
the folder with the job. Created with `open(path, "x")`, the same
`O_CREAT|O_EXCL` the JSON locks have always used on the share
(`acquire_lock()`); a `PermissionError` there is a claim pending deletion
on Windows: taken, for now. The file exists before its content is
written, so a claim the host can't read is still held (`{}`, owner
unknown), never free. `try_claim()` raises on any other error rather than
returning False: a render that can't reach the share would otherwise find
"nothing left to claim", exit 0 and be sent the job again, forever; a
claim created but not written is removed first (nobody would ever free
it). Checked headless, three Blender processes claiming the same 200
chunks at once on a local disk: 79/62/59, each chunk won once, each claim
holding its winner -- on the real share, to check on the farm.

### The render loop

The render entry (`templates/worker_render_entry.py`, `render_chunks()`)
opens the .blend once and walks the chunks from the first -- again and
again while a pass rendered something: a chunk another machine let go
behind it (stopped after a frame) is picked up in the same Blender, where
a single pass ended and the host had to start a new one for three frames
(seen on the first real test). A chunk whose
frames are all on disk (one listing of the folder) or that another
machine holds is skipped; a claimed one is checked again frame by frame
(the listing may be seconds old on SMB), then each missing frame is
rendered by Blender's own animation render over a one-frame range
(`frame_start = frame_end = f`, `render.render(animation=True)`), written
to a hidden tmp of this render's own (`render.filepath` =
`.<machine>_<pid>_#####.tmp`, `use_file_extension` off: never counted as
a frame, never another machine's) and `os.replace()`d onto its final name
-- `frame_path()` read for the whole range before the output is switched
to the tmp: what the frame check and the compilation read.

First done with `render.render()` then `Render Result`'s `save_render()`:
the same pixels, but a compositor File Output node then writes
`depth_.exr`, unnumbered, each frame over the last -- only an animation
render (`-a`, `-f`) numbers them. Checked: `depth_0001.exr`... with the
one-frame animation; a multilayer EXR with a compositor identical to
`-a`'s byte for byte but its Date stamp. A File Output file isn't written
through the tmp, but before the main output: a render killed while
writing it leaves the frame missing, rendered again, the pass rewritten. The claim is
rewritten before (frame in progress, its tmp for the host to delete if
the render dies) and after (frames done) each frame;
gone when it's about to be rewritten, the host took this machine for dead
and freed it: the render stops rather than write it back (two machines on
one chunk). `.stop` is read before each chunk and each frame. A frame that
fails ends the render (exit 1) with its claim in place, for the host to
free and count against this machine.

Checked headless, Workbench, 64x36 PNG: 23 frames by one machine -- the
same names and the same pixels as Blender's own `-a` render; 120 frames
by three at once -- each written once, none missing, no claim or .tmp
left; `.stop` -- exit 0, claim released; a render killed mid-chunk -- its
claim left (`frames_done` and the frame in progress in it), another
machine rendering everything but that chunk's frames left. Not checked
yet: memory over hundreds of frames (one Blender per job, as the
animation render always was), Cycles' persistent data.

### The farm host

The host (`check_render_completion()`, every tick of a job at
`render_start`; one listing of the claims, one of the frames):

- **Dead claims.** A claim is held while its machine's worker is alive,
  rendering this job, with the claim's pid (`_dead_claims()`): never a
  comparison of clocks, never a guess from the claim's age. Otherwise it's
  deleted, its chunk free again, the frames it finished kept, the `.tmp`
  of its frame in progress removed. Counted against the machine only when
  its render *failed* (`_failed_this_render()`: exit != 0, or killed on a
  stuck frame): `chunk_failures[k]`, `failed_machines` (no more requests
  of this job for it), `stuck_frames`. Stopped (both kinds, quitting
  Blender, a project switch), cancelled, lost or gone: neutral -- a
  workstation taken back or switched off says nothing about the frames,
  and it may come back to the job. A claim unreadable for 60 s of the
  host's own clock (a render killed between creating and writing it) is
  freed too.
- **Failed everywhere.** A chunk failed on `MAX_CHUNK_ATTEMPTS` (3)
  different machines is the frames, not the machines: a heavy frame past
  the RAM, a cache or texture missing on it, a driver erroring there. The
  render stops (`fail_reason`, then the Cancel path: requests withdrawn,
  the machines rendering sent a cancel) and ends `render_failed` with
  "frames X-Y failed on 3 machines (...)" once none is left on it. Also
  `render_failed`: chunks free, nobody on it, every live worker allowed on
  the job failed it.
- **Cancel** (`cancel_requested`): same stop, `render_failed (cancelled)`.
  With no machine on the job (its chunks waiting for one) the button
  still cancels it -- it used to refuse ("No machine currently assigned").
- **One machine's Cancel** (Workers tab) is "leave this job", to free a
  machine for another one: its render killed (neutral), the machine in
  `left_machines`, which `machines_for()` leaves out -- it goes to the
  other jobs first. Still idle once every job had its turn this tick,
  `scan_queue()`'s second pass sends it back to the render it left
  (`with_left`): an idle machine next to free chunks helps nobody. A new
  dispatch, a Retry, or the end of the render clear the list.
- **Finished**: every frame on disk and no claim left -- a claim whose
  last frame is written but not yet released is waited for. The `.tmp`
  files and the claims folder are removed.
- **Dispatch.** Free chunks (a frame missing, no claim): idle machines
  allowed on the job sent the same request (`send_render()`, same
  `dispatch_id` and `chunk_size`), in the queue's priority order -- one
  per free chunk, less the machines already starting on it (rendering, no
  claim yet) or with a request waiting; "single": one, only while nobody
  is on it. No free chunk: requests still waiting withdrawn (the old
  "Render stuck at 100 %"). `render_dispatch()` (setup_finished) sends as
  many machines as there are chunks to render (frames sent back by the
  frame check: only theirs).

A render that fails with no machine left names what failed: "frames
11-15 failed on 09d89c9c, fbd54d8e -- no other machine to try"
(`_no_machine_reason()`), not just "every machine allowed on it failed
it"; its empty claims folder goes with it (`_end_render()`).

### Workers with ffmpeg

A worker's file says whether it can compile a video: `ffmpeg` (bool) and
`ffmpeg_version` (`_worker_identity()`, on `launch_worker()`). Not a
requirement -- a worker without it renders all the same. The point: send a
compilation (the previews, long ones) to another machine than the farm
host's (see "Previews on a worker" below). Found isn't enough, the
binary is run once (`ffmpeg -version`, 10 s at most): one on disk can
still fail to start (see "FFmpeg detection"). Checked once, when the
worker starts -- not on every heartbeat; ffmpeg installed since needs a
restart of the worker. Run before the worker file's lock, not under it.
A worker file with no `ffmpeg` key (1.1.0 and before) is unknown, not
"no": Worker details says "unknown (older addon)" -- and gets no preview.

### Previews on a worker

A preview (ffmpeg concat over a sequence's videos, re-encoded: long) goes
to an idle worker with ffmpeg first, the farm host's own machine only if
there's none (`scan_queue()`, `preview_queued`: `ffmpeg_worker(idle)` --
never this machine, which compiles it itself, locally -- then
`send_preview_compile()`). From the same `idle` as the renders, in
priority order: a render of higher priority took its machines first, a
lower one waits for the compile.

Its own request, `requests/compile_<job>_<uuid>.json` -- never
`request_*.json`, which a worker takes for a render. `idle_machines()`
counts both kinds as targeting a machine. The job is the source of
truth: at `preview_start`, `compile_machine` names the machine on it. The
request first, then the job: a request whose job wasn't written (or was
taken back since) is dropped by the worker (`_still_mine()`).

On the worker (`worker_tick()`, idle: a render request first, then a
compile one): `execute_compile_request()` runs the same command as the
host (`preview_command()`), with its own ffmpeg and project root, output
in the job's own log (`popen_logged()`, `request_<job>.log`: one machine
writes it at a time). Status `compile`, `current_job_id` the job.
`scan_compile_processes()`, once ffmpeg exits: `preview_finished` /
`preview_failed` (with `machine`) written in the job first, *then* the
worker idle -- the host reads an idle worker on a job still at
`preview_start` as a lost compile. `last_compile_result`, not
`last_job_result`: that one says how its last render ended, which the
host's chunk bookkeeping reads (`_failed_this_render()`).

On the host, `check_remote_compile()` every tick of a `preview_start`
with a `compile_machine` (a local one is `scan_processes()`'s, as before):
back to `preview_queued` (`resume_interrupted_stage()`, "lost on <machine>")
when its worker is gone (`WORKER_GONE_SECONDS`) before or after taking
the request -- the request deleted -- or alive but no longer compiling it
(stopped, Blender restarted). Read in the order `_on_this_render()` does:
the request, then the worker file, which the worker holds locked while it
takes the request (unreadable: wait a tick). Re-checked under the job's
lock: a worker that ended it meanwhile wins. `recover_interrupted_jobs()`
leaves such a job alone.

Stopping that worker: "after this frame" waits for the compile
(`worker_rendering()` counts it), "now" kills ffmpeg -- the host sends
it out again. Not covered: a worker crash leaving its ffmpeg running --
not adopted by PID as a render is, so the preview can be compiled twice
at once onto the same file. Rare (a crash, on a disposable preview);
the next compile overwrites it.

Checked headless on real files and ffmpeg (two machines simulated, bpy
stubbed): sent, compiled, ended by the worker; the worker gone before
taking it; stopped mid-compile; a request whose job was taken back;
"after this frame" waiting for it; `scan_queue()` to a worker, and to the
host when none has ffmpeg.

A preview's `priority` is the artist's, as a render's: `compile_preview`
(*Preview block* / *Preview sequence*, sidebar and Project monitoring)
now opens a dialog for it -- one click more, it went out at 10 before --
and the Render dialog's Preview mode shows its `priority` field. Same
property as Render's, remembered from the last submit. Job details shows
every job's (10 when the file has none).

### Mixed versions

Mixed versions: a 1.0.x worker given a chunks job renders the whole range
with placeholders, blind to the claims -- the frames written twice back.
A worker announces `farm_protocol` (2) in its file (`_worker_identity()`);
`idle_machines()` leaves out any other, logged once, flagged in Worker
details ("too old: gets no render until updated"). A protocol number,
not the addon version: a dev build keeps its old number until the bump. The other
way round, a request with no `chunk_size` (a 1.0.x farm host) is refused
by the worker and fails its job with that reason (`_chunk_size_of()`).
The first dispatch is logged too ("rendering on A, B (12 chunks of 5
frames)"): only the machines sent to a render already started were.

### Interface

The UI: the Render dialog's modes are *All machines* and *Single* (a job
file's older `auto`/`placeholder` reads as all machines: only "single" is
tested). The claims are read with the rest of the farm snapshot, on its
reader thread, for the jobs at `render_start` only -- Job details lists
the chunks in progress (machine, frame) from there, never from `draw()`,
and the job file's `chunk_failures`, `fail_reason`, `left_machines`;
Worker details its machine's chunk. The pre-render picker's "None" reads
"No pre-render script" and needs no label; the dialog opens on the
project's `farm.default_prerender_script` (Edit project) on every
`invoke()` -- the enum's own memory kept the last pick, or fell back to
the first item. Edit project lists the presets of the project it edits,
which isn't always the active one.

A Retry clears `chunk_failures` and `fail_reason`; `failed_machines` too
when every live worker allowed on the job is in it (else it would wait
forever). `max_workers_per_job` is gone: it existed for collisions, and
the priority already orders the jobs.

Checked headless on simulated worker files, 27 cases: claims held, freed
on a failure / stuck frame / stop / cancel / loss / a gone worker / a
stale pid, three failures stopping the render then failing it with its
reason, finished and its leftovers removed, waiting on a claim, single
mode, machines sent per free chunk, a waiting request withdrawn, an
unreadable claim, no machine left, a retry, the first dispatch.

## Renders to check: the one before, to compare

File details' "Renders to check" rows have a second play button, the
render before this one (`open_render_video(previous=True)`): among the
shot's other render folders, the newest video older than this render's
(its folder's time if it has none). Times, not folder names: `v004_002`
vs `v004-stable_001` vs a custom version prefix don't sort by name, and a
render folder only gets its video once compiled. Looked up on click --
`draw()` doesn't list folders -- so the button is always there and says
so when there's no earlier render. A recompile touches an old render's
video: it then counts as newer.

## Validation roles

"Done" (the old "validated", data unchanged: `departments_validated`) says
the work is finished; graphists needed a second word, a role's sign-off
(sup, prod...) -- finished technically isn't accepted by production.

Rejected: a "valid prod" department per file (no per-department answer),
a keyword in a note's text (the text never computes anything -- "Status
is derived, not a dropdown"), a "tag" entry type and tags replacing entry
types. The last two fail on one point: entries belong to the asset/shot
and travel across versions, a validation belongs to the version the role
saw. A tag set on v012 would still read "validated" on v014, which nobody
saw.

So: `approvals` in the stablemeta, `{department: {role: {"by", "at"}}}`,
written by `set_department_approval()` on the *latest* stable only (a
review import names the one it saw: refused once a newer exists, "to
review again"). A new stable starts empty -- `create_stablemeta()` carries
the last ones into `approvals_previous` (`_carried_approvals()`, each with
its `file`), for "prod: v012" without reading older stables. Only a done
department's count (`_status_from_raw()` drops the others); undone then
done again at the same stable, they come back -- same version.

Roles are the project's (`validation_roles()`, Edit project as
`name:level`; none set: `sup:1,prod:2`, `[]`: none). A higher level covers
the lower, the same level is equivalent: `covering_role()` computes it at
display, never written -- a prod validation isn't a sup one recorded, and
withdrawing it mustn't erase what the sup did.

Each validation given or withdrawn writes a note under its role
(`source: "approval"`): the history, with its author. An entry's `role`
is set at writing (the user's `user_role` pref, `get_user_role()` -- only
if the project has it; a review import's Role cell) -- the role a person
had then, not looked up by author: one person can wear two hats. RTK
colors: a role's red, the team's orange; Blender colors no text but red,
so the team's RTK loses the red text for an orange `COLLECTION_COLOR_02`
mark, a role's note a violet one. New entry's *As <role>* box (`as_role`,
on) lets a sup post a team note -- a technical one -- without clearing
the pref.

The snapshot's *Validated* is a second figure, not a share of Done: Done
weighs the departments' fabrication (wip 33 %...), and folding a
validation into it (10 %?) would make "90 %" unreadable -- 90 % made and
nothing validated, or all validated and one department late. Validated
is the share of the required departments the top role covers
(`top_validation_role()`: the highest level, its equivalents count;
`item["validated"]`, `item["validation"]`, `meta["validation"]`,
`average_progress(items, "validation")`), at the stable shown: a new
stable drops it. Tiles next to each Done, a column, groups and totals, in
`--role` violet; a pre-1.1.2 snapshot (no `validation_role`) shows none.

Review template v4 (`SCHEMA_VERSION` 4), reworked before 1.1.2 went
out: v3 had a *department*, *type* and *text* column per row plus a
`valid <department>` column each -- ten columns to fill for one shot, and
one text cell for every department, so a retake [sh010] for layout and
another [sh020] for animation couldn't be written on one row. Now:

- A front sheet (`_review_front()`): Author, Review date, Role (a
  dropdown of the project's roles, required as soon as the file holds a
  retake or a validation), how to fill, the colour legend, the hidden
  `schema_version=4` cell.
- A sheet per section (`_review_section()`: Shots, Assets -- they don't
  share departments), a row per file: group (merged), filename (locked),
  description (editable, as before), **a cell per department**, *global*,
  then the hidden versions and `description_exported`.
- A department cell's fill is its state at the snapshot
  (`_department_style()`: `_S_STATE`, violet once the top role covers
  it, a red-bordered twin for an open RTK; "–" locked where not
  required). Its dropdown suggests `ok,no` with `showErrorMessage="0"`:
  any text still goes.
- Reading a cell (`_cell_choice()`): one of `OK_WORDS` (ok, yes, oui, v,
  x, ✓...) validates, `NO_WORDS` withdraws, any other text withdraws too
  and makes an RTK of each line -- a cell mixing "ok" and text is text:
  the retake wins. `note:` at a line's start makes it a note.
  *global*: ok / no for every department done now without a value of its
  own, a text an RTK with no department. `_row_actions()` turns a row
  into (validations, global, notes) for both the plan and the import --
  v3 and older rows through their own columns, as they were read.
- A withdrawal is only planned where the role has a validation to
  withdraw: a retake on unvalidated work isn't listed as a change.
- Every sheet is read (`read_xlsx_grids()`, `_sheet_paths()` in the
  workbook's order): labels from above any header, rows from every sheet
  with a *filename* header.

A line's leading tags (`_line_tags()`: `[sh020]` -- checked against the
file's shots, `_file_shots()` --, `[f12-40]` / `[f12]`, any order; an
unknown one ends the scan and stays in the text) give its shot and
frames; a v2/v3 template's *shot* column still applies to its lines.
`review_import_plan()` reads it without writing, for the confirm dialog
that names the role (`M_PIPELINE_OT_import_review_confirm`, a timer tick
after the file browser: popup-chaining); `import_review_xlsx()` re-checks
every validation through `set_department_approval()`.

Checked headless (bpy stubbed, a real project tree, openpyxl filling the
template): roles and covering, refused when not done / unknown role,
no-op twice, tooltips, carried to the next stable, the snapshot's marks,
the template's columns and dropdowns, an import validating two
departments with a note, refused after a newer stable, refused without a
Role.

## Entries for several departments

An entry's departments are a list now: one RTK "the ball's contact" is
animation's and lighting's at once -- written twice before, one per
department, each ticked done on its own. Kept as one entry, one `done`:
fixing it is one act. It counts in each department -- the filter, the
red RTK cell of Project monitoring (`_has_rtk()`), the snapshot's
`rtk_departments` -- and reads "animation, lighting" as a tag.

Stored next to the old field, not instead of it: `"department"` keeps
the first one, `"departments"` holds them all only when there are
several (`_set_entry_departments()`), so a one-department entry is
written exactly as before and an addon before 1.1.0 on the same project
-- a team updates machine by machine -- still reads every entry, seeing
its first department. Readers go through `entry_departments(e)`, which
takes either shape.

The dialogs pick them with an ENUM_FLAG menu (`prop_menu_enum()`, as the
Render dialog's assigned machines), labelled with the selection; its
items are bit-numbered, with no "none" item -- no flag set is none. A
department the file no longer requires is dropped on Edit rather than
failing invoke(). A review spreadsheet's department cell splits on `,`
`;` `/` `+`, each name validated against the file's departments, the
unknown ones dropped.

New entry: one entry per line for every type -- a note joined its lines
into one entry with the first line's department and frames, the others
ignored; a shot per line (`PipelineEntryItem.shot_tag`, right of its
departments, for a block), not one for the whole dialog; RTK by default;
blank lines left out (an empty line, an empty line inside a text), and
nothing written when every line is. Each line keeps its quarters
(departments, frame tag and start, end, reference); a block's shot goes
under its departments, in the same quarter -- side by side, an eighth
each, neither was readable.

Department order: `create_tracking()` stored `departments_required`
`sorted()` by name, and every list followed the file -- the file
details, the toggles, the pickers, an entry's tag. Now the project's
order (Edit project: asset departments, then shot ones; any other after
them, as given): `ordered_departments()`, applied where they're written
(`create_tracking()`, `_set_entry_departments()`) and where they're read
(`get_departments_required()`, `_status_from_raw()`) -- files written
before stay sorted by name on disk and read in the project's order.

## Shortcuts

The preferences' Shortcuts section listed `rna_keymap_ui.draw_kmi()` rows:
each named after its operator's label -- "Change page" four times. Each
key is now named for what it does (`_KEYMAP_ITEMS`' first field), drawn as
a tick, that name and its key (`draw_addon_keys()`), found in the user
keyconfig by operator *and* properties (two page keys, Increment and Mark
as stable, share an operator). The section is folded by default
(`show_shortcuts`).

Keys anywhere in Blender (Window keymap) -- Project / Farm monitoring, the
log, New entry, Increment, Mark as stable, Render this file -- are
registered off: whatever combination ships clashes with something in
someone's Blender, so each user switches on the ones they want and picks
their keys. The defaults are Shift+Alt+letter, not Ctrl: Project
monitoring's Ctrl+click opens the open file's detail, and a Ctrl
shortcut would too. "Render this file" can't carry the open file's path
in a keymap item: `farm_request_render.current_file` makes invoke() read
it. F5 refreshes a monitoring window (`m_pipeline.monitoring_refresh`).
Enter to open a file's detail was turned down: too easy to hit by
accident.

## Screenshots in the docs

`docs/images/` (one set for both languages: the interface is in English),
shown with `<img src=... width=...>` rather than `![]()`: a sidebar
panel or a small dialog at its own resolution filled the page width.
Dialogs and panels get a width, the monitoring windows and the snapshot
the page's. `docs/` is left out of the extension package
(`blender_manifest.toml`), so they never weigh on the download. Update a
capture when its screen changes: an outdated one misleads more than none.
