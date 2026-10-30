# Tracking & reviews

*[← Documentation index](README.md) · [Version française](tracking-and-reviews_fr.md)*

---

Every asset/shot has a `.pipeline/` folder next to its `.blend` files:

- **`tracking.json`**: required departments + a free-text description of what the asset/shot is (set at creation — interactively or via batch CSV, see [Project structure, naming, batch creation](project-and-naming.md)) + a list of entries (`note` / `todo` / `rtk`), each with author, date, its department(s), done/not-done state.
- **`{version}.wipmeta`**: one per work version — creation mode, departments worked on this session, linked libraries. Full details in [Versions: wip and stable](versions.md).
- **`{version}.stablemeta`**: one per `-stable` version — departments validated at that point. This is the reference point for computing "what's been touched since the last stable", shown throughout the UI. Individual departments can also be validated directly, without cutting a new `-stable` version — buttons next to each department in the Tracking panel/dashboard, for departments (like "render") that aren't tied to editing the file itself. This mutates the *latest* stablemeta's `departments_validated` in place; requires at least one `-stable` version to already exist.

**Prod review import** (Project panel or Pipeline menu > *Import review*): reads back the review spreadsheet from a snapshot, as is. Each line of a department cell's text becomes its own retake (see *Review template* below; a *text* cell in a template from before 1.1.2) — several retakes on the same shot go on several lines (Alt+Enter), each one with its own checkbox. Author and date come from the top of the sheet (`prod` and the import day when left empty); each note is anchored on the render the reviewer watched -- the *Last render* the snapshot showed, per shot for a block (`[sh120]` takes sh120's) -- and on the `.blend` version that render was made from (`v007-stable_001` → `..._v007-stable.blend`), not on the latest file: a tag *▶ v007-stable_001* on the note (snapshot) and *Based on: ... (render v007-stable_001)* in its tooltip say which. The review carries that render (a hidden *render* column, a `render` field in the page's `.json`); one made before 1.1.6 doesn't, and the import takes the render that already existed when its snapshot was made -- a shot rendered again since, or never rendered, keeps the file's version. Importing the same file again, or a re-sent one with notes added, never duplicates: lines already imported are skipped. Descriptions edited in the *description* column (editable for that) are applied too, after a dialog listing every change (was / now): all of them, or none — to leave one out, fix the spreadsheet and import it again. Only a cell the production changed counts: a description changed in the project since the export is never reverted, and an empty cell changes nothing. A spreadsheet exported before 1.0.12 has its descriptions ignored. A popup lists what came in and what couldn't (e.g. a file renamed or branched since). Imported entries say so in their tooltip.

**Production snapshot** (Project panel or Pipeline menu > *Snapshot*): writes one HTML file -- `<project>_snapshot_<YYYY-MM-DD_HH-MM>.html`, in the project's `snapshots/` folder by default -- with the state of every asset/shot per department and every note, for people outside the studio (no Blender, no access to the share needed: it opens offline in any browser, on a computer or a phone, and can be sent by mail). The scan runs in the background; Blender stays usable meanwhile. Once written, it opens in your browser (*Open when done*, next to *Thumbnails* in the file browser; untick to just save it).

- **At the top**: the project and when the snapshot was taken -- opened later, a "n days old" pill says the project may have moved since --, then a card per section (shots, assets & libraries) with its Done and its Validated. With a schedule (Project settings > *Schedule*: start and end dates, days off, the days of the week worked -- Monday to Friday by default), each card also says how many working days ahead or behind the section is at an even pace, and its pace (done / expected) in a pill coloured by band, as in a progress spreadsheet: 105 % and more ahead, 100 to 105 % on track (green), 90 to 100 % slightly behind (amber), under 90 % behind (red); a *Schedule* card gives the day and the progress expected.
- **The list**: a tab per section (Shots, Assets, and Libraries when there are any), the files by sequence / prefix, each group with its Done and Validated -- folded when none of its files has a department to track. A file shows its thumbnail (its own size on hover with a mouse, full screen on a click or a tap), its name, then on a line under it its versions (`wip v004 · stable v003`, the wip only when newer than the stable), a block's number of shots, its open notes and its state in the farm; then a mark per department: done ●, done at the last stable but worked on again since ◉ (reworked), in progress ◐, not started ○, not required –. Under a mark, a ◆ per open entry, its colour saying whose: red an RTK from a validation role, orange the team's, grey a todo -- its tip says which; an RTK on no department puts its ◆ under every done department, which it holds back, and the file shows *◆ General RTK*; its validation (✓ prod -- each role in its tooltip --, struck through when given to an earlier stable: to review again) and, while reviewing, your own (✓ you, ✕ you). A badge only for what shows nowhere else: *⚠ Render outdated* (rendered from an older version than the last stable), *Render to check*. Departments nobody in the list requires get no column; the column names stay under the bar while scrolling.
- **Filters**: a department (the toggles then look at it alone), *Retakes* (an open RTK -- on that department or on none), *Open notes*, *Render outdated*, *To validate* (a done department its stable isn't validated at), *Not finished*, each with its count; *Find a file…* narrows the list and lists the matching files of every section -- Enter or a click opens one. A filter finding nothing in this section but some in another says so. *?* gives the legend, the keys and how Done counts.
- **A file's panel** (a click on its row): beside the list on a computer -- the list moves aside and stays live, a click on another row shows that one; drag the panel's left edge to make it wider or narrower (kept by the browser, a double click for the default); a narrow list turns compact --, the whole screen on a phone (swiped down to close): its picture large and, for a block, each shot's; its description; its departments, each with its validation and its open RTKs (who, when, its shot and frames); the RTKs on no department; the other notes, open ones first (*Show the n closed*), each with its tags -- the role it was written as (violet), its departments, shot, frames, the render it was written watching (▶ v007-stable_001); its last render per shot (the version rendered, ⚠ when older than the stable, *to check*, the farm's state) and its Blender file. *Previous* / *Next* or ← / → go through the list as filtered (on a phone ‹ › in its header, or a swipe sideways), Esc closes; 🔗 copies a link that opens this file (`…_snapshot_….html#sq060_sh070`).
- **Done**: each required department counts for an equal share: not started 0 %, work in progress 33 %, done but reworked since 67 %, done with an open RTK -- on it or on none -- 67 %, done 100 % (the three middle values are set per project: Project settings > *Snapshot done*). A file averages its departments, a group its files. *Progress details*, at the bottom, gives each section's Done by sequence / prefix and by department -- the expected progress a line across each bar -- and a sequence (or prefix) × department grid, each cell shaded by its %.
- **Videos**: *Videos*, in the export's file browser, picks where the videos the page plays go -- remembered from one export to the next, with the sequences ticked: *Folder* copies them into a `videos/` folder next to the snapshots, shared by all of them: only the videos new or changed since the last export are copied (an export where only notes changed copies nothing). *Zip* puts them in a zip next to the snapshot, with its name (`..._snapshot_<date>.zip`), to send with it. *Don't copy* copies nothing: the page still plays the videos already in `videos/`. With *Folder* or *Zip*, the sequences are listed, none ticked the first time: the video of each last render the page shows, for every shot of the ticked ones, goes in, under its path in `renders/` (`sq100/sh030/v002-stable_001/sq100_sh030.mp4`). *Assets & libraries*, under the sequences, adds every asset/library's the same way (`assets/ch/ch_bob/v003_002/...`). Copied after the HTML, in the background too; a sequence with nothing rendered is skipped (a warning says which), and so are the assets/libraries with no video. The page knows which videos it has and plays them from there: the blue ▶ in a file's panel header plays its render -- for a block whose shots were rendered apart, each shot's video after the other in the block's order (⏮ ⏭ or ← → skip) --, a small ▶ after each sequence's name for all its files' in a row, and *▶ Play* on each line of *Last render*: one line per video, a shot rendered apart its own line. While reviewing, *Last render* folds away: a ▶ per shot stays under the picture. Thin controls under the picture (▶/❚❚, position, time, full screen; Space plays/pauses). Moved, renamed, or on another machine: *Choose the videos folder…* (the folder button next to *?* until one is chosen, the page's ⋯ menu, or under a render with nothing to play) picks the folder holding them, whatever its name -- the project's `renders/` folder works too, no copy needed: in Chrome or Edge the page opens only the videos it needs, by their paths, never reading the folder through (Firefox and Safari read every file of the folder chosen first: pick `videos/` there, not `renders/`, full of frames); on a phone, the videos themselves.
- The page carries a review spreadsheet (.xlsx, in its ⋯ menu) to download, one row per asset/shot, for production to fill in and send back -- or the review is made right on the page (*Review on the page*, below).

<img src="images/tracking-snapshot-progress.png" alt="The production snapshot: progress">

<img src="images/tracking-snapshot-details.png" alt="The production snapshot: assets and shots">

Project monitoring (Project panel or Pipeline menu), a window of its own: the list of every file with its status per department, and a file's detail (notes/todos, with a click to validate an `rtk`, and its total logged work time — see [Design choices](design.md#work-duration-is-logged-never-surfaced-per-person) for what that total is and isn't). Described in [Interface](interface.md#overview-windows).

Multishot blocks can tag a note/todo with which shot in the block it's about — see [Shot blocks (multishot)](multishot.md).

**Renders to check**: when a farm job finishes (frames checked, video compiled), its render waits for a check. Project monitoring shows it in its "Farm" column as a button (click to play it), next to the Farm popup's icon for each job of the file still in the farm (submitted, queued, waiting between steps, in progress, failed) — one per shot, side by side for a block; hover an icon for its shot, version and step (rendering 45/120, compiling...). The check mark button after them marks the renders to check checked; a filter icon (camera) lists only the files with an icon there. A legend of these icons sits at the bottom of the table, next to the file count. The file's detail lists them in their own box (date, video, the render before it -- to play the previous version of the shot and compare --, folder, "Checked"), with an "In the farm" box below for its jobs still in the farm (shot, version, step), next to the last render of each shot, checked or not. Marking a render checked also archives its farm job, and shows all the file's departments, ticked as they're validated now ("render" ticked too): untick one the render shows isn't right, and it's unvalidated (needs a stable version, like any department validated by hand). A block keeps one per shot; a newer render of a shot replaces the older one.

<img src="images/ui-file-details.png" alt="A file's detail: departments, last render, renders to check, notes">

---

## Done, then validated: validation roles

A department is **done** when its work is finished (the tick next to it --
called "validated" before 1.1.2, same data). **Validation** comes on top:
a role's sign-off -- the supervisor's, the production's -- on the version
it saw.

- **Roles** are set per project (Edit project > *Validation roles*, e.g.
  `sup:1,prod:2,real:2`): a higher level covers the lower ones (validated
  by prod: good for sup too), the same level is equivalent (prod or real).
  Without any set, `sup:1,prod:2`.
- **Your role**: Preferences > *Validation role*. Empty: a team member.
- **Validating**: in a file's detail, a star next to each done department
  gives or withdraws your role's validation (its tooltip lists every
  role: validated, covered by a higher one, or not). It's kept on the
  latest stable: a new stable starts with none -- the role hasn't seen it
  -- and shows the last one given ("prod: v012, to review again").
  Withdrawing or giving it writes a note under your role, for the record.
- **Notes under a role**: a note, todo or RTK written by someone with a
  role carries it (violet mark), and so do the notes imported from a
  review template. An RTK from a role is red in the snapshot, the team's own orange; in Blender its mark is the role's violet, like its notes, the team's orange.
  The *New entry* dialog shows your role in an *As sup* box, on by
  default: untick it to write as the team (a technical note, say).
- **Project monitoring**: a done department reads "Done · prod" once
  validated; a filter (the star) lists the files with a done department
  still to validate -- for your role, or by any role if you have none.
- **Snapshot**: "✓ prod" under a department's mark (each role in its
  tooltip), struck through for one given to an earlier stable (the
  file's panel says which: "✓ sup on v012, to review again").
  A *Validated* figure sits apart from Done -- per section, group and
  file, in violet: the share of the required
  departments validated by the top role (or one of its level) at the
  stable shown. Done stays the fabrication: 100 % done with nothing
  validated reads 100 % / 0 %.
- **Review template**: a first sheet *Review* for your name, the review
  date and your *Role* (required as soon as the file holds a retake or a
  validation), how to fill it and the colour legend; then a *Shots* and
  an *Assets* sheet, a row per file and **a cell per department** (only
  that section's departments), coloured by its state at the snapshot:
  white not started, amber WIP, light green done but reworked since,
  green done -- to validate --, violet already validated by the top role;
  a red border for an open retake; grey "–" not required (locked).
  - `ok` (or `yes`, `oui`, `v`, `✓`...) validates the department for your
    role -- refused if it isn't done.
  - `no` withdraws that validation.
  - any other text withdraws it too, and **each line becomes a retake**
    (RTK) of that department -- Alt+Enter for the next line. Start a line
    with `[sh020]` for one shot of a block, `[f12-40]` (or `[f12]`) for its
    frames, in any order: `[sh020] [f12-40] camera higher`; with `note:`
    for a remark instead of a retake. A tag that isn't one -- a shot not
    in the block, a reversed range like `[f40-12]` -- stays in the text.
  - *global*: `ok` validates every department done so far (a
    department's own cell wins over it), a text is a retake for no
    department in particular.
  - empty: nothing changes.

  The import asks first, naming the role and listing the validation
  changes, then refuses any validation of a file with a newer stable
  since the snapshot. A template exported by an earlier version still
  imports, as it was read then.

- **Review on the page** (1.1.5): instead of the spreadsheet, *✎ Review*
  puts a bar at the bottom of the screen -- your name and your role; ›
  folds it into a round ✎ button, the review's count on it --
  and, in a file's panel, a ✓ by each department (validate it as your
  role -- a done one only) and a ✗ (a box for the retakes, one per line:
  `[sh020]` at its start for one shot of a block, `[f12-40]` for its
  frames, `note:` for a remark instead of a retake -- for a block, a box
  for all its shots and one per shot, opened by its button, each line of
  it written back with its `[sh020]` tag;
  left empty, it withdraws a validation); an *All done* row above the
  departments (its ✓ validates every done one) and a *Whole file* row
  under them (its ✕ opens a retake on no department), with the same
  buttons; *✎ Edit the description* under it. The
  list shows what you did under each department (✓ you, ✕ you); the
  panel's *Last render* and *Blender file* step aside while reviewing.
  Keys: ← → (files), Esc (close), V (all done), X (general retake), Esc
  or Ctrl+Enter in a box (leave it). *Download* sums up the review --
  files, validations, retakes, withdrawn -- and asks your name, your
  role (required as soon as it holds a retake or a validation) and the
  review date, then saves the `.json`: **Import review** takes it like
  an `.xlsx` -- several at once too (one per reviewer: the file is named
  after its time, role and author). The page keeps what you write in
  your browser as you go (a reload brings it back, in the same browser
  -- not in a private window or on another machine); the bar's ⋯ menu
  has *Load a review…* (reopens a downloaded one), *Clear this review*
  and *Leave the review*. The spreadsheet stays, for several reviewers
  or a shared drive.

Nothing to migrate: `departments_validated` keeps its name, validations
are a new `approvals` key in the stablemeta, a note's role a new `role`
key -- absent, the team's own.

## Data structure: `tracking.json`

**`assets/ch/ch_bob/.pipeline/tracking.json`** — one per asset/shot, created with the file:

```json
{
  "file_name": "ch_bob",
  "created_at": "2026-03-25T16:00:00",
  "departments_required": ["modeling", "rigging", "texturing"],
  "description": "Main character, the fox.",
  "entries": [
    {
      "id": "a3f1c",
      "type": "todo",
      "text": "Add face shape keys",
      "author": "samy",
      "date": "2026-03-21T09:00:00",
      "department": "rigging",
      "done": false
    }
  ]
}
```

`type` is `note` (`done: null`, never checkable), `todo`, or `rtk` (fix requested — `done: true/false`, with `done_by`/`done_at` once validated).

**New entry**: one entry per line, whatever its type (RTK by default) -- each line its own departments, frames and, in a block, shot. Departments always show in the project's order (Edit project), wherever they're listed.

<img src="images/tracking-new-entry.png" alt="The New entry dialog" width="560">

**Several departments**: an entry can be for several departments at once -- tick them in the department menu of the New entry / Edit dialogs. It's one entry with one done state, shown under each of its departments' filter; an open RTK turns each of its departments red (Project monitoring, snapshot); one on no department (a general retake) turns the file's name red instead in Project monitoring; in the snapshot it red-outlines the "n RTK" by the file's name and counts in the file's Done as an RTK on one done department (each department's own Done untouched), and in the review spreadsheet every department cell is red-bordered. Stored as `"departments": ["animation", "lighting"]` next to `"department"` (the first one, what an addon before 1.1.0 reads). A review spreadsheet's department cell takes several too: `layout, lighting` (`,` `;` `/` `+`).

A finished farm render adds a `to_check` key, until it's marked checked: `{"<shot>": {"render", "video", "at", "job_id"}}` — the shot is `""` for an asset or a single shot, one key per shot for a block.

---

**See also**: [Versions: wip and stable](versions.md) for `.wipmeta`/`.stablemeta` · [Interface](interface.md) for the Tracking panel and the monitoring windows.
