# Dev notes

Docstrings and comments in the code stay short and functional (what a
function does, tooltip-length); anything longer than that about rationale,
history, or a rejected alternative lives here instead, one section per
feature. `CODE.md` is the *what's built* reference; this file is the
*why/how it got built this way* for anything that needed more room than a
comment.

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
  shared state, not owned by `PIPELINE_OT_create_shot` — `PIPELINE_OT_branch_shot`
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

### Block size — no upper bound, deliberately

No enforced maximum on how many shots a block can cover. Raised while writing the spec: what stops someone folding an entire sequence into one block "because it's simpler" — the exact monolith the naming convention would dress up as *structured* (`sq040_sh010-...-200_v001.blend` reads clean even at 20 shots) while being the same one-file-does-everything failure mode the addon exists to prevent. Split-at-render makes a huge block technically painless (isolated per-shot failure, per-shot output), which removes the one purely technical brake that might otherwise have discouraged it.

Two levers were on the table, and the wrong one was almost shipped. Friction at creation — hand-picking every shot, no typed range (see "Naming" above) — costs the person building the block a few extra clicks, but that person is rarely who pays for a block being too big. The real cost is concurrency: Blender allows exactly one session per open `.blend`, so a block's size *is* its unit of concurrency — a 12-shot block means anim, lighting, and fx all serialize behind the same lock no matter how the actual work is split. The warning shown at creation (`_draw_block_warning()`, `operators/shot_ops.py`) names that directly — "This locks all N shots together as a single unit" — instead of just surfacing a shot count, because the count alone doesn't explain *why* it matters. It's shown to whoever is choosing the shots, on purpose: the person deciding a block's scope should see its cost, since a lighter or fx artist discovering later that their shot is locked inside someone else's file isn't an edge case — it's the default outcome of an unbounded block with no upfront warning.

No hard cap was added regardless — a warning, not a block, consistent with the addon's own "warning, not blocking" principle. Whether a warning is enough in practice is still an open question, not a closed one.

### Camera/marker scaffolding (§1.4)

- `build_shot_scene()` creates one camera + one marker per shot, all sharing
  a single CAM/SET/ASSETS collection set (a block is one decor/lighting
  setup, never one per shot) — a mono-shot is `shot_numbers=[n]` through the
  exact same loop, not a separate branch.
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
3. **Efficiency fix**: a child's `overrided_frame_range` is resolved to
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
`render_history.json` (`construct_split_history()`).

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

The alternative to flagging a branched-out composition `archived` was moving its files to an `/old/` folder instead. `/old` is more honest on disk — a dead block is visibly dead, no JSON to open to find out — and it sidesteps a real race: the farm is a ~10s-latency pull model, so a guard that checks "is a job active on this block right now" right before moving files can still lose to a worker that pulled the request 8 seconds earlier, or a request still sitting unpulled in `queue/requests/`. Moving nothing means an in-flight job's path never goes stale underneath it, race or no race.

The flag won anyway, for one reason: it turns branch into a metadata-only operation — no move, no lock spanning several stages, none of the race above — instead of a filesystem transaction that would need to be written as one. The price is real and recurring, not one-time: two blocks now physically coexist in `shots/<sq>/`, and *every* enumeration — monitoring, submit farm's cascade picker, casting, the save-guard — must filter `archived: true` or a dead block resurrects. `list_active_blocks()` exists specifically to be the one place that filter lives (below), so the discipline only has to hold at one call site instead of every one that lists blocks. Missing it anywhere new fails silently — a branched-off block just reappears — not loudly.

- `create_shot_file()` for the new composition runs *before* the old block
  gets flagged archived, not after: if creation fails (naming collision,
  permissions...), the old block must never end up archived with no
  successor. The reverse failure mode (new block created, old one somehow
  fails to archive) is left as an acceptable, safe-by-default outcome —
  both are just "active", not a broken state.
- `archive_block()` started as its own `lib/tracking.py` function and was
  deliberately inlined into `PIPELINE_OT_branch_shot.execute()` instead: it's
  a 5-line `locked_json` write with exactly one caller — the abstraction
  wasn't paying for itself. `copy_entries()` / `list_active_blocks()` stayed
  as real functions because they have (or are meant to have) more than one
  caller.
- `list_active_blocks()` is meant to be the *only* place that filters
  archived blocks out of an enumeration — the spec's own words are "one
  point of truth, not a filter copied everywhere". Already wired into
  `shot_items()` (submit farm's cascade picker) and `TrackingStatusCache.get_all()`
  (monitoring). Not yet wired into the preview providers (`lib/preview.py`)
  — they scan `renders/` directly, which isn't keyed by block identity at
  all (a shot folder doesn't know which block last rendered into it), so
  there was no clean way to apply the filter there without a larger change;
  left as a known gap, not silently "handled".

### §6 — MAX_PATH (deferred, not implemented)

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
the base is already implied by the parent folder) — has **not** been
implemented. Decision explicitly left pending a real UNC-path test rather
than acted on from the theoretical numbers alone.

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

The one real gap `context.region.width` has: it's the *panel's* width, not any nested sub-layout's — Blender doesn't expose a sub-layout's resolved width from inside `draw()` (it doesn't exist yet at that point, only after the C-side layout pass runs). `region_char_budget()` accepts an explicit `width_px` for exactly one such case, a popup/dialog's own `invoke_popup(width=...)`/`invoke_props_dialog(width=...)` value — scaled by `POPUP_WIDTH_SCALE` to correct for a popup's content area rendering narrower than its declared width. A label inside an ordinary panel's own `split()`/nested `column()` isn't covered by this — the caller would need to pass its own fraction of the budget by hand; nothing does that automatically today.

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

A rotated file moves to `config/logs/archives/<stem>_<timestamp>.jsonl` (a path that already existed in `ConfigCache`'s table, unused, before this) — never trimmed, never deleted. Same reasoning as picking the `archived` flag over physically moving a branched-out multishot block (see "Branch" above): the data stays honestly on disk, readable without the addon, rather than a decision about what's safe to throw away getting made silently by a rotation policy. The cost lands on `WorkTimeCache`, which has to know rotation happened at all.

### Rotating `sessions_log.jsonl` can't quietly shrink a total

The one thing rotation isn't allowed to do to `sessions_log.jsonl` specifically: make "total work time" go down because old lines aged out of the file `WorkTimeCache` happens to be looking at. So `WorkTimeCache.get()` sums the live file *and* every `sessions_log_*.jsonl` under `archives/` (glob, re-read whenever the live file's mtime changes — cache invalidation still keys off one file, since a fresh archive only ever appears in the same `log()` call that also bumps the live file's mtime). `pipeline_log.jsonl` has no reader anywhere in the addon, so its own archived chunks are never touched again — the asymmetry is deliberate, not an oversight: one log became data, the other stayed a diagnostic trail, and they're rotated the same way but read back completely differently.

At realistic scale this barely matters yet: `sessions_log.jsonl` grows slowly enough (only `session_end` lines now, roughly one per file-open) that a single project would take on the order of a decade to produce even one rotation — `pipeline_log.jsonl`, logging far more per session, gets there in months. Scanning "the live file plus a handful of archives" is cheap for exactly as long as that stays true. If it stops being true, the fix isn't a smarter re-scan — it's baking old chunks down to one summed line per folder before they'd otherwise need re-reading, so detail can be dropped without the total losing accuracy. Not built pre-emptively; see `CODE.md`'s tech debt list.

---

## Top bar read-only indicator: why it sits before the Blender icon

`read_only_indicator()` (`menus/top_bar.py`) is `.prepend()`-ed to `TOPBAR_MT_editor_menus`, which lands it before that class's entire native `draw()` — including the Blender icon, not just "File". That wasn't the goal (icon, *then* the warning, *then* File was) but it's what's buildable: Blender draws the icon and the File menu back to back, in the same hardcoded `draw()`, with no hook between them for an addon to land content into. `.append()`/`.prepend()` only ever add before or after that whole native block, never inside it.

Landing exactly between the two was considered — monkey-patch `TOPBAR_MT_editor_menus.draw` itself, redraw the icon, insert the warning, then call through to the rest — and turned down: it means owning a copy of Blender's own menu-drawing logic, which silently drifts the moment a future Blender version changes that native `draw()`. Paying that fragility for one slot of cosmetic ordering wasn't worth it. Before-the-icon was picked over after-everything (the `.append()` alternative, tried first) for the reason the whole feature exists: it has to be the first thing visible, not buried after every native menu and the addon's own "Pipeline" one.

---

## Recent files: derived from the log, not a stored list

The top bar's "Recent" entries (`RecentFilesCache`, `lib/tracking.py`) don't store anything of their own — they're computed from `sessions_log.jsonl`'s own `session_end` lines, the same file `WorkTimeCache` already reads, on the same mtime-cached full-scan pattern.

A plain stored list (e.g. in addon prefs) was the first idea, and the problem with it surfaced immediately: it would need active upkeep (append on open, cap its length, and — the real trap — get cleared or re-scoped on every project switch, or it'd offer to open a file from whatever project was active last). Deriving from the log sidesteps all of that structurally rather than adding code to handle it: `sessions_log.jsonl` already lives inside the *active* project's own `config/logs/`, so reading it can't produce a file from a different project — there's no cross-project list to accidentally leak from, because there's no list.

**Filtered to `get_user()`, not the whole team** — an animator who only ever opens shot files should never see a modeler's asset file in their own "recent" list. This didn't need department metadata or any new field: filtering `session_end` entries to `entry["user"] == get_user().lower()` already produces exactly that, because a person's own session history naturally only contains what they themselves opened. The department-correct result falls out of filtering by identity; no department-aware logic was written.

**Full forward scan, not a backward tail-read** — raised directly: since JSONL is append-only, the most recent entries sit at the end of the file, so reading backward from EOF and stopping once `limit` distinct folders are found is more the shape of "give me the last 3" than a full forward pass is. Turned down anyway: the scan is mtime-cached (not run per redraw), `sessions_log.jsonl` grows slowly enough that it's realistically small for a project's entire lifetime, and it's hard-capped at `LOG_ROTATE_MAX_BYTES` regardless. A backward chunked reader (handling lines split across block boundaries, encoding-safe) is real code for a saving that doesn't show up at this scale. Consistency with `WorkTimeCache`'s own scan shape won over an optimization nothing currently needs.

<!-- Next feature with rationale worth keeping gets its own "## " section
     here, same shape as the ones above: what was tried, what was
     rejected and why, anything a docstring is too short to hold. -->
