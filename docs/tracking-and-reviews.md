# Tracking & reviews

*[← Documentation index](README.md) · [Version française](tracking-and-reviews_fr.md)*

---

Every asset/shot has a `.pipeline/` folder next to its `.blend` files:

- **`tracking.json`**: required departments + a free-text description of what the asset/shot is (set at creation — interactively or via batch CSV, see [Project structure, naming, batch creation](project-and-naming.md)) + a list of entries (`note` / `todo` / `rtk`), each with author, date, department, done/not-done state.
- **`{version}.wipmeta`**: one per work version — creation mode, departments worked on this session, linked libraries. Full details in [Versions: wip and stable](versions.md).
- **`{version}.stablemeta`**: one per `-stable` version — departments validated at that point. This is the reference point for computing "what's been touched since the last stable", shown throughout the UI. Individual departments can also be validated directly, without cutting a new `-stable` version — buttons next to each department in the Tracking panel/dashboard, for departments (like "render") that aren't tied to editing the file itself. This mutates the *latest* stablemeta's `departments_validated` in place; requires at least one `-stable` version to already exist.

**Prod review import** (Project panel or Pipeline menu > *Import prod review*): reads back the review spreadsheet from a snapshot, as is. Each line of a *text* cell becomes its own entry — several retakes on the same shot go on several lines (Alt+Enter), each one with its own checkbox. Author and date come from the top of the sheet (`prod` and the import day when left empty); each note is anchored on the version the snapshot showed. Importing the same file again, or a re-sent one with notes added, never duplicates: lines already imported are skipped. Descriptions edited in the *description* column (editable for that) are applied too, after a dialog listing every change (was / now): all of them, or none — to leave one out, fix the spreadsheet and import it again. Only a cell the production changed counts: a description changed in the project since the export is never reverted, and an empty cell changes nothing. A spreadsheet exported before 1.0.12 has its descriptions ignored. A popup lists what came in and what couldn't (e.g. a file renamed or branched since). Imported entries say so in their tooltip.

**Production snapshot** (Project panel > *Export prod snapshot*): writes one HTML file — `<project>_snapshot_<YYYY-MM-DD>.html` — showing every asset/shot's status per department and every note (closed todos/RTKs included, hidden until "Show closed" is ticked), for people outside the studio (no Blender, no access to the share needed: it opens offline in any browser, and can be sent by mail). Each department reads *Not started*, *Work in progress*, *Validated*, or *Validated, reworked since* (validated at the last stable, but worked on again after it). A "Done" column shows how far along each asset/shot is — each required department counts for an equal share: in thirds: work in progress 1/3, validated but reworked since or with an open RTK 2/3, validated 3/3; a validated department with an open RTK is outlined in red — with the % of each sequence / asset prefix on its group row, an "All" row per table (section total and % per department) and two totals at the top (assets & libraries, shots). Exports go to the project's `snapshots/` folder by default, named with the date and time. A "Last render" column gives the output folder of each asset/shot's last render (vXXX_YYY: the .blend version rendered, then the render increment), in red when it was rendered from a version older than the last stable. Each asset/shot shows a thumbnail from its latest render (the farm makes it when a render ends; the export makes any that are missing or out of date, from the frames already on disk). It can be filtered by name, group (prefix/sequence), department and state, open RTKs or open notes; each row with notes links straight to them. The page carries a review spreadsheet (.xlsx) to download, one row per asset/shot, for production to fill in and send back. The scan runs in the background; Blender stays usable meanwhile.

Two project-wide monitoring popups (Project menu): the list of every file with its status per department, and a file's detail (notes/todos, with a click to validate an `rtk`, and its total logged work time — see [Design choices](design.md#work-duration-is-logged-never-surfaced-per-person) for what that total is and isn't). Both are described in [Interface](interface.md#overview-popups).

Multishot blocks can tag a note/todo with which shot in the block it's about — see [Shot blocks (multishot)](multishot.md).

**Renders to check**: when a farm job finishes (frames checked, video compiled), its render waits for a check. Project monitoring shows it in its "To check" column — a video button plays it, the checkbox marks it checked — and an eye icon in its filters lists only the files with one waiting. The file's detail lists them in their own box (date, video, folder, "Checked"), next to the last render of each shot, checked or not. Marking a render checked also archives its farm job, and offers to validate the file's departments not validated yet ("render" ticked by default; needs a stable version, like any department validated by hand). A block keeps one per shot; a newer render of a shot replaces the older one.

---

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

A finished farm render adds a `to_check` key, until it's marked checked: `{"<shot>": {"render", "video", "at", "job_id"}}` — the shot is `""` for an asset or a single shot, one key per shot for a block.

---

**See also**: [Versions: wip and stable](versions.md) for `.wipmeta`/`.stablemeta` · [Interface](interface.md) for the Tracking panel and the two monitoring popups.
