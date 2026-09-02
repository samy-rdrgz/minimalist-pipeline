# Interface

*[← Documentation index](README.md) · [Version française](interface_fr.md)*

---

All the panels live in the 3D viewport sidebar (`N` > **Pipeline** tab), plus a few popups for overview views.

| Panel | Always visible? | Content |
|---|---|---|
| **Project** | Yes | Active project (name, folder, config), New asset / New shot / Batch create from CSV / Open file / Render / Open folder buttons, Monitoring button (see below). Collapsible list of other known projects (activate / edit / remove each), New project / Find existing project. |
| **Asset** | If the open file is an asset/library | Worked-this-session department toggles (if the file has required departments), Increment version, Mark as stable, Render, Open folder. |
| **Shot** | If the open file is a shot | Same actions as the Asset panel, plus Preview block / Preview sequence, and Branch block (see [Shot blocks (multishot)](multishot.md)). |
| **Tracking** | If the open file belongs to the active project | Per-department status of the current file, its notes/todos/rtk list right there, with direct editing/validation. The "always visible" version of the detail popup described below. See [Tracking & reviews](tracking-and-reviews.md). |
| **Farm** | If a project is active | Header: monitor status (stopped / running / stale) with a Launch/Kill button. Body: a button opening the farm dashboard (see below). See [Rendering (farm)](farm.md). |

<br>

## Overview popups

Reached from the buttons above, not permanent panels:

- **Project monitoring** (the "Monitoring" button on the Project panel): every file in the project with its status per department, filterable by prefix (assets) or sequence (shots). Clicking a file opens its detail — description, total logged work time (all versions, everyone summed — see [Design choices](design.md#work-duration-is-logged-never-surfaced-per-person)), full notes/todos, entry creation, CSV import.
- **Farm dashboard** (the Farm panel's button): two views, *Jobs* (each active job with its current stage and progress, an "X" button to cancel an in-progress render, a "✓" button to archive a finished/failed job once it's no longer useful in the list) and *Workers* (every known machine, idle or what it's currently rendering, with the same cancel button targeted at that machine), plus the button to add/remove this machine as a worker.

<br>

## Top bar menu

A "Pipeline" menu appears in the top bar (next to File/Edit/Render...), so you don't have to open the sidebar for common actions — same content as the panels above (create, open, render, save/increment/mark-stable on the current file, farm roles), condensed into a single menu.

Under "Open file", up to 3 recently opened files — your own, not a teammate's, and never the file already open. Not a separate list: derived from `sessions_log.jsonl` each time, so it's automatically scoped to the active project and can't drift from it. One click reopens, no dialog.

Same row, leftmost — before the Blender icon, before File/Edit/Render, before "Pipeline" too: a red "READ-ONLY" label appears whenever the current file is read-only for this session (`-stable`, locked by someone else, or `always_read_only`) — always visible regardless of which sidebar tab is open, right where the File menu's Save button and the top bar's save icon sit, the two ways of saving that don't go through the Ctrl+S guard (see [Known current limitations](limitations.md)).

---

**See also**: [Project structure, naming, batch creation](project-and-naming.md) · [Versions: wip and stable](versions.md) for what Increment/Mark as stable actually do.
