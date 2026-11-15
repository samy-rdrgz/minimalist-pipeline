# Tracking & reviews

*[← Documentation index](README.md) · [Version française](tracking-and-reviews_fr.md)*

---

Every asset/shot has a `.pipeline/` folder next to its `.blend` files:

- **`tracking.json`**: required departments + a free-text description of what the asset/shot is (set at creation — interactively or via batch CSV, see [Project structure, naming, batch creation](project-and-naming.md)) + a list of entries (`note` / `todo` / `rtk`), each with author, date, its department(s), done/not-done state. Its *Notes & tasks* title (the File panel, a file's detail) shows what's left, folded or not: open RTKs in red, open todos in grey -- notes aren't counted. *Hide done*, first of its filters, brings back the done ones: the retakes to check a render against. The sidebar and Project monitoring each keep their own filters and fold. A right-click on an entry's icons (its check box or circle, the grip on its right) offers Reply, Edit, Mark done / Reopen and Delete.
- **`{version}.wipmeta`**: one per work version — creation mode, departments worked on this session, linked libraries. Full details in [Versions: wip and stable](versions.md).
- **`{version}.stablemeta`**: one per `-stable` version — departments validated at that point. This is the reference point for computing "what's been touched since the last stable", shown throughout the UI. Individual departments can also be validated directly, without cutting a new `-stable` version — buttons next to each department in the Tracking panel/dashboard, for departments (like "render") that aren't tied to editing the file itself. This mutates the *latest* stablemeta's `departments_validated` in place; requires at least one `-stable` version to already exist.

**Prod review import** (Project panel or Pipeline menu > *Import review*): reads back the review made on a snapshot's page (the `.json` it downloads, see *Review on the page* below). Each line of a department's box becomes its own retake — several retakes on the same shot go on several lines, each one with its own checkbox. Author and date are the ones given at its download (`prod` and the import day when left empty); each note is anchored on the render the reviewer watched -- the *Last render* the snapshot showed, per shot for a block (`[sh120]` takes sh120's) -- and on the `.blend` version that render was made from (`v007-stable_001` → `..._v007-stable.blend`), not on the latest file: a tag *▶ v007-stable_001* on the note (snapshot) and *Based on: ... (render v007-stable_001)* in its tooltip say which. The review carries that render (a `render_watched` field in its `.json`); a shot never rendered keeps the file's version. Only a review of this add-on version's snapshot is read: one from an older snapshot is refused -- export the snapshot again and review it there. Importing the same file again, or a re-sent one with notes added, never duplicates: lines already imported are skipped. Descriptions edited on the page (*✎ Edit the description*) are applied too, after a dialog listing every change (was / now): all of them, or none — to leave one out, change it on the page and download the review again. Only a description the production changed counts: one changed in the project since the export is never reverted, and an empty one changes nothing. A popup lists what came in and what couldn't (e.g. a file renamed or branched since). Imported entries say so in their tooltip. Each review imported is kept as it was sent, in `snapshots/reviews/<role>/<YYYY-MM>/` (`team`, or `no-role`; the month of its review date): the same file is never copied twice, another one under the same name gets a number.

**Production snapshot** (Project panel or Pipeline menu > *Snapshot*): writes one HTML file -- `<project>_snapshot_<YYYY-MM-DD_HH-MM>.html`, in the project's `snapshots/<YYYY-MM>/` folder by default (one per month; the snapshots of before 1.2 stay at its root) -- with the state of every asset/shot per department and every note, for people outside the studio (no Blender, no access to the share needed: it opens offline in any browser, on a computer or a phone, and can be sent by mail). The scan runs in the background; Blender stays usable meanwhile. Once written, it opens in your browser (*Open when done*, next to *Thumbnails* in the file browser; untick to just save it).

- **At the top**, one line staying in view as the page scrolls: the project and the snapshot's day -- opened later, a "n days old" pill says the project may have moved since --, each section's Done and Validated (a double bar, `84 % · 3 %`; with a schedule, its pace in a pill coloured by band, as in a progress spreadsheet: 105 % and more ahead, 100 to 105 % on track, 90 to 100 % slightly behind, under 90 % behind -- the working days ahead or behind in its tip), *Go to a file…* (/), *?* and *Review* (violet). The page is dark, Blender's mood, or light (⋯ menu: System, Light, Dark); one colour for one meaning: green done, orange in progress or reworked, violet validated, red a retake, blue play and frame ranges, your review neutral.
- **The list**: a tab per section (Shots, Assets, and Libraries when there are any) then *Breakdown*, the files by sequence / prefix, each group a card with its Done and Validated -- folded when none of its files has a department to track. A file shows its thumbnail (its own size on hover with a mouse, full screen on a click or a tap), its name, then its versions (`wip v004 · stable v003`, the wip only when newer than the stable), a block's number of shots and its open notes; under them, tags: a retake on no department (*RTK · WHOLE FILE*), *render to check*, *render outdated*, and the farm (queued dashed, rendering, failed in red); a file set aside (*On hold*, *Cancelled*) is faded. Then a keyframe diamond per department: not started (outlined), in progress (half filled), reworked since (open, an arrow), done (green), validated (violet with a ✓: light by a role, deep by the top one); waiting on an earlier stage (a clock in it) or to redo since one changed (an eye in it), in its state's colour; not required, nothing. Hovering or focusing a diamond stretches it into a capsule with its words (`WIP · v005`, `DONE · stable v003`, `✓ PROD · Valerie`, and *Waiting* or *To redo* with their reason). An open retake puts a post-it under it -- red from a validation role, outlined from the team, their number in it (`2 RTK`) --, your review a *YOU* one above it. On the right, the file's Done and Validated.
- **Filters**: a department (the toggles then look at it alone), then each toggle with its icon, name and count -- *Your review* (✎, while there's one: the files it touched), *Retakes* (an open RTK -- on that department or on none), *Open notes*, *Render outdated*, *To validate* (a done department its stable isn't validated at), *In the farm* (while a file is: rendering, queued or failed), *Not finished*. *Go to a file…* in the header (/ from anywhere) narrows the list and lists the matching files of every section -- Enter or a click opens one. A filter finding nothing in this section but some in another says so. *?* gives the legend, the keys and how Done counts.
- **A file's panel** (a click on its row): beside the list on a computer -- the list moves aside and stays live, a click on another row shows that one; drag the panel's left edge to make it wider or narrower -- past its widest, it fills the page (an iPad upright), dragged back from its left edge it's beside the list again (kept by the browser, a double click for the default); a narrow list turns compact: 58 px rows, a small picture, the name and one line, each department's diamond in a 30 px column named by its initials (L, A, Li, R) --, the whole screen on a phone (swiped down to close, *Previous* / *Next* at the bottom) and on a tablet. With a finger, a first tap on a diamond shows its words, a second opens the file. At its top **the player**: the file's video (its shots one after the other), its timeline carrying the notes at their frames -- a retake's red diamond, a range's blue bar (`f12-30`), yours outlined; a click goes there --, ◂ ▶ ▸ (`,` `.` a frame back / on, Space to play), the frame as numbered in the .blend (`f12 / f96 · 30 fps`) and **⤢ Watch large**: the video the whole window, the departments with ✓ / ✕ and the notes at their frames in a column beside it, the timeline and ⏮ ◂ ▶ ▸ ⏭ under it, the sequence's files along the bottom (a click plays one; past a file's last video, the next file's) -- Esc back to the panel. A sequence's ▶ in the list opens Watch large on it. No video to play: why, and *Choose the videos folder…*, in its place. Then its description and its departments, each with its diamond, its state and what's open on it (`done · 1 retake · 1 thread`), its validation, ✓ / ✕ while reviewing, and **its threads under it** -- each note in one place, under its first department (none: under *Whole file*): its author's initial, who, as what, when, its kind (RTK red, TODO orange, NOTE neutral), its frames (a click goes there), its replies indented; the closed ones folded (*1 closed todo · show*). At the bottom, its last render per shot (the version rendered, ⚠ when older than the stable, *to check*, the farm's state, ▶ plays it above) and its Blender file. *Previous* / *Next* or ← / → go through the list as filtered (on a phone ‹ › in its header, or a swipe sideways), Esc or the tab on its left edge closes it (at the window's edge then, the tab brings it back); the link button copies a link that opens this file (`…_snapshot_….html#sq060_sh070`).
- **Done**: each required department counts for an equal share: not started 0 %, work in progress 33 %, done but reworked since 67 %, done with an open RTK -- on it or on none -- 67 %, done 100 % (the three middle values are set per project: Project settings > *Snapshot done*). A file averages its departments, a group its files. The *Breakdown* tab shows, in place of the list, the schedule (the day, the progress expected) and each section's Done by sequence / prefix and by department -- the expected progress a line across each bar -- and a sequence (or prefix) × department grid, each cell shaded by its %.
- **Videos**: the page plays each render's video. *Videos*, in the export's file browser, picks where from -- remembered from one export to the next, with the sequences ticked: *Don't copy* (the default) copies nothing: on a machine that reaches the project, the page plays them from `renders/` itself, relative to it (the browser loads one video on ▶, it never reads a folder through); *Folder* copies them into `snapshots/videos/`, shared by every month's snapshots (the page finds it at `../videos`; a snapshot saved elsewhere, in a `videos/` beside it) -- only the videos new or changed since the last export: take the whole `snapshots/` folder --, *Zip* into a zip next to the snapshot, with its name (`..._snapshot_<date>.zip`): both to take the snapshot elsewhere, a folder to send as is, a zip to send in one piece. A copy missing (a *Folder* snapshot opened at the studio without its folder), the page falls back on `renders/`. The sequences are listed, none ticked the first time: the video of each last render the page shows, for every shot of the ticked ones, is copied (*Folder*, *Zip*) under its path in `renders/` (`sq100/sh030/v002-stable_001/sq100_sh030_v002-stable_001.mp4`) -- the same tree, so one name works from the copy or from `renders/`. *Assets & libraries*, under the sequences, adds every asset/library's the same way (`assets/ch/ch_bob/v003_002/...`). **Too wide or unplayable**: a video wider than 8192 px (a panoramic render -- past that, browsers on a PC or an iPad refuse it) or in a codec browsers don't play (ProRes, DNxHR...) has a light copy beside it, in its render folder's `ld/` (H.265, at most 8192 px wide), made by the farm's compilation: that's what the page plays and the snapshot carries, the full one kept for the edit. A render compiled before gets its light copy from Export snapshot, once, for the ticked sequences (needs ffmpeg; the log says which). Copied after the HTML, in the background too; a sequence with nothing rendered is skipped (a warning says which), and so are the assets/libraries with no video. The blue ▶ in a file's panel header plays its render -- for a block whose shots were rendered apart, each shot's video after the other in the block's order (⏮ ⏭ or ← → skip) --, a small ▶ after each sequence's name for all its files' in a row, and *▶ Play* on each line of *Last render*: one line per video, a shot rendered apart its own line. While reviewing, *Last render* folds away: a ▶ per shot stays under the picture. Thin controls under the picture (▶/❚❚, position, time, full screen; Space plays/pauses), and the frame shown -- `f1042`, numbered as in the .blend (the render's first frame, from its farm history or its images' names, plus its rank in the video at the project's fps): a block rendered whole counts on its own timeline, as Blender and the `[f12-40]` retakes do; ◂ ▸ (or , and .) go one frame back / on, paused. A render whose first frame isn't known counts from its video's start (`#1`). Moved, renamed, or on another machine: *Choose the videos folder…* (the folder button next to *?* until one is chosen, the page's ⋯ menu, or under a render with nothing to play) picks the folder holding them, whatever its name -- the project's `renders/` folder works too: in Chrome or Edge the page opens only the videos it needs, by their paths, never reading the folder through (Firefox and Safari read every file of the folder chosen first: pick `videos/` there, not `renders/`, full of frames); on a phone, the videos themselves.
- Its ⋯ menu also picks the page's theme: *System* (the device's), *Light* or *Dark*, kept by the browser.
- The review is made right on the page and sent back as a `.json` (*Review on the page*, below).

<img src="images/tracking-snapshot-progress.png" alt="The production snapshot: progress">

<img src="images/tracking-snapshot-details.png" alt="The production snapshot: assets and shots">

Project monitoring (Project panel or Pipeline menu), a window of its own: the list of every file with its status per department, and a file's detail (notes/todos, with a click to validate an `rtk`, and its total logged work time — see [Design choices](design.md#work-duration-is-logged-never-surfaced-per-person) for what that total is and isn't). Described in [Interface](interface.md#overview-windows).

Multishot blocks can tag a note/todo with which shot in the block it's about — see [Shot blocks (multishot)](multishot.md).

**Renders to check**: when a farm job finishes (frames checked, video compiled), its render waits for a check. Project monitoring shows it in its "Farm" column as a button (click to play it), next to the Farm popup's icon for each job of the file still in the farm (submitted, queued, waiting between steps, in progress, failed) — one per shot, side by side for a block; hover an icon for its shot, version and step (rendering 45/120, compiling...). The check mark button after them marks the renders to check checked; a filter icon (camera) lists only the files with an icon there. A legend of these icons sits at the bottom of the table, next to the file count (behind a *Legend* button when there's no room). The file's detail lists them in their own box (date, video, the render before it -- to play the previous version of the shot and compare --, folder, "Checked"), with an "In the farm" box below for its jobs still in the farm (shot, version, step), next to the last render of each shot, checked or not. Marking a render checked also archives its farm job, and shows all the file's departments, ticked as they're validated now ("render" ticked too): untick one the render shows isn't right, and it's unvalidated (needs a stable version, like any department validated by hand). A block keeps one per shot; a newer render of a shot replaces the older one.

<img src="images/ui-file-details.png" alt="A file's detail: departments, last render, renders to check, notes">

---

## Stages: Waiting and To redo

**Stages** (Edit project, in the departments field itself): `layout > animation > fx, lighting > render` -- `>` the next stage, a comma for departments in parallel. Commas only (`layout, animation, lighting, render`, as before): no stages, nothing changes. Nothing is ever blocked: it's information.

- **Waiting**: an earlier stage has an open RTK, or isn't started -- *Waiting: layout RTK*, *Waiting: layout not started*. Shown instead of the department's state in Project monitoring; its own state stays in the tooltip.
- **To redo**: a department already started whose earlier stage changed after its last update -- an RTK on that stage closed, or a stable made with it reworked -- *To redo: layout changed on 12/11*. Its last update: a save in a session where it was ticked as worked, or **Still done**.
- **Where**: Project monitoring's cells (a legend in its footer once the project has stages), File details' departments, the sidebar's *Working on* toggles.
- **Still done** (File details, or the ✓ beside a toggle in the sidebar, on a department to redo, open to everyone): the work done holds after the change -- recorded with who and when, and an optional why; not a validation.

## On hold and Cancelled

**Set a file aside** without archiving it (File details, the pause button): *On hold* (paused, waiting for a decision) or *Cancelled* (cut at the edit, dropped), with a why. It stays in every list, greyed with its mark, and leaves the shares done (the snapshot's figures, the schedule's pace), the Retakes and To validate filters, and the stages (no Waiting, no To redo). The same button makes it *Active* again. A block's mark covers all its shots.

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
  latest stable, and a new stable keeps it while that department wasn't
  worked since (1.1.9: "validated on v012, not worked since"); worked
  since, the new stable starts without -- the role hasn't seen it -- and
  shows the last one given ("prod: v012, to review again").
  Withdrawing or giving it writes a note under your role, for the record
  -- in *Notes & tasks*, those in a row make one box, a line per role and
  stable ("★ prod: fixanim, render-ld · v003-stable", each note in its
  tooltip).
- **Notes under a role**: a note, todo or RTK written by someone with a
  role carries it (violet mark), and so do the notes imported from a
  review. An RTK from a role is red in the snapshot, the team's own orange; in Blender its mark is the role's violet, like its notes, the team's orange.
  The *New entry* dialog shows your role in an *As sup* box, on by
  default: untick it to write as the team (a technical note, say).
- **A review as the team**: *team* in a review's Role (the snapshot
  page's -- unless a validation role has that name): its retakes and notes are the team's own -- no role, orange, no
  "prod review" tag (imported from a team review) -- and it validates
  nothing: the page's ✓ are off, a ✓ or `ok` written before is left out.
- **Project monitoring**: a department under RTK (red) opens, on a
  click, a small popup with its open retakes -- and those on no
  department --, closed as the mouse leaves. A retake on no department:
  the button by the file's name (red) shows those.
  A done department reads "Done · prod" once validated (the star in full
  for the top role, the grid otherwise grey); a filter (the star) lists the files with a done department
  still to validate -- for your role, or by any role if you have none.
- **Snapshot**: "✓ prod" under a department's mark (each role in its
  tooltip), struck through for one given to an earlier stable and worked
  since (the
  file's panel says which: "✓ sup on v012, to review again").
  A *Validated* figure sits apart from Done -- per section, group and
  file, in violet: the share of the required
  departments validated by the top role (or one of its level) at the
  stable shown. Done stays the fabrication: 100 % done with nothing
  validated reads 100 % / 0 %.
- **Review on the page**: *✎ Review* (violet, in the header) opens a
  window first: *Continue your review* when this browser keeps one; your
  name, the review date and your role (buttons, a line saying what each
  does: the team writes retakes and notes, no validation); what to *go
  through* -- *To validate*, *Open retakes and notes*, *Everything, in
  order*, *What the filters show* (the filters set for it, its first
  file opened); *Load a review file…*. While reviewing, the header shows
  who, as what and how many files (a click: the same window, to change
  them) and *Send…*; the ⋯ menu *Clear this review…* and *Leave the
  review*. In a file's panel, a ✓ by each department (validate it as your
  role -- a done one only) and a ✗ (a box for the retakes, one per line:
  `[sh020]` at its start for one shot of a block, `[f12-40]` for its
  frames, `note:` for a remark instead of a retake (nothing but
  remarks: grey ✎ you, the validation left as it is) -- for a block, a box
  for all its shots and one per shot, opened by its button, each line of
  it written back with its `[sh020]` tag;
  left empty, it withdraws a validation); an *All done* row above the
  departments (its ✓ validates every done one) and a *Whole file* row
  under them (its ✕ opens a retake on no department), with the same
  buttons; *✎ Edit the description* under it. The
  list shows what you did under each department (✓ you, ✕ you); the
  panel's *Last render* and *Blender file* step aside while reviewing.
  An open RTK -- the prod's or the team's -- has *✓ Fixed* beside it while
  reviewing (an open todo, *✓ Done*): marked, it's done once the review is imported, as its
  author (one done since, or gone, is left as it is; importing again
  changes nothing). *↩ Reply*, beside it and under an open note, writes
  a reply, in that note's thread at import, under your role -- read as a
  department's box: a retake ("still to redo"), red, unless every line
  is `note:`, a remark, grey. A retake reply sends the note's department
  back as ✕ would (✕ you, its validation withdrawn at import; no
  department: the whole file's ✕ you) and is imported as an RTK on it;
  the RTK answered stays open (*✓ Fixed* says it's done).
  To go over it: *Your review*, among the filters (or *See them* in *Send your review*),
  shows only the files the review touched.
  Keys: ← → (files), Esc (close), V (all done), X (general retake), Esc
  or Ctrl+Enter in a box (leave it). *Send…* opens *Send your review*: your
  name, your role (required as soon as it holds a retake or a
  validation) and the review date; then file by file what it holds, with
  the list's symbols (✓ a department validated, ✕ a retake and its
  text, a description, fixed, replies); the `.json`'s name -- the page
  sends nothing itself: download it and send it to the studio (mail,
  SwissTransfer). *Clear this review…*, *Keep reviewing*, *Download*:
  **Import review** takes the file -- several at once too (one per
  reviewer: the file is named after its time, role and author). On a
  tablet or a phone, the button is *Save or send…*, the system's share
  sheet: *Save to Files* picks
  the folder (a download lands wherever the browser -- or the app showing
  the page -- keeps its own), or AirDrop, Mail.... The page keeps what you write in
  your browser as you go (a reload brings it back, in the same browser
  -- not in a private window or on another machine); the bar's ⋯ menu
  has *Load a review…* (reopens a downloaded one), *Clear this review*
  and *Leave the review*. The import asks first, naming the role and
  listing the validation changes, then refuses any validation of a
  department worked since the stable the review saw (a newer stable
  without it worked keeps it).

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
      "departments": ["rigging"],
      "done": false
    }
  ]
}
```

`type` is `note` (`done: null`, never checkable), `todo`, or `rtk` (fix requested — `done: true/false`, with `done_by`/`done_at` once validated).

**New entry**: one entry per line, whatever its type (RTK by default) -- each line its own departments, frames and, in a block, shot. Departments always show in the project's order (Edit project), wherever they're listed.

<img src="images/tracking-new-entry.png" alt="The New entry dialog" width="560">

**Several departments**: an entry can be for several departments at once -- tick them in the department menu of the New entry / Edit dialogs. It's one entry with one done state, shown under each of its departments' filter; an open RTK turns each of its departments red (Project monitoring, snapshot); one on no department (a general retake) turns the file's name red instead in Project monitoring; in the snapshot it red-outlines the "n RTK" by the file's name and counts in the file's Done as an RTK on one done department (each department's own Done untouched). Stored as `"departments": ["animation", "lighting"]` (one department: a list of one).

A finished farm render adds a `to_check` key, until it's marked checked: `{"<shot>": {"render", "video", "at", "job_id"}}` — the shot is `""` for an asset or a single shot, one key per shot for a block.

---

**See also**: [Versions: wip and stable](versions.md) for `.wipmeta`/`.stablemeta` · [Interface](interface.md) for the Tracking panel and the monitoring windows.
