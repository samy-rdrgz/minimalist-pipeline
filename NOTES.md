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

## File details' `file_details_selected` is a folder, not a versioned file

`M_PIPELINE_OT_tracking_monitor`'s file-details view (`draw_file_details()`,
`panels/tracking_panel.py`) reads `context.window_manager.file_details_selected`
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
`file_details_selected` should assume folder, not file.

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

**User identity uses `getpass`, not `os.getlogin()`** — the latter needs a
controlling terminal (an `ioctl` on the tty) and reliably raises when
Blender is launched without one, which is the common case (desktop icon,
Steam, the VS Code extension...), not the exception. `getpass.getuser()`
checks `LOGNAME`/`USER`/`USERNAME` env vars first, no tty required. Used in
two places for the same reason: `get_user()` (`lib/session.py`) as the
`prefs.user_name` > OS login > `"unknown"` fallback read at log time, and
`_seed_user_name()` to write that OS login into the pref itself once, on
first register, so the Preferences panel never shows nothing configured
and a shared-machine login gets a chance to be corrected to the real
person.

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
`context.window_manager.file_details_selected`, which used to fall through
the old two-tier fallback (`self.filepath or bpy.data.filepath`) straight
to `bpy.data.filepath` -- whatever's open in the viewport, unrelated to the
file actually shown in the popup -- so the department dropdown only ever
offered "All departments" there. The sidebar's own entries panel has
neither: `bpy.data.filepath` (the open file) really is the right answer
for it. Fixed by trying all three in that order: `self.filepath` ->
`file_details_selected` -> `bpy.data.filepath`.

A first attempt gave `M_PIPELINE_OT_tracking_monitor` its own `filepath`
`@property` returning `file_details_selected`, reasoning `getattr(self,
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

<!-- Next feature with rationale worth keeping gets its own "## " section
     here, same shape as the ones above: what was tried, what was
     rejected and why, anything a docstring is too short to hold. -->
